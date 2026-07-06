/**
 * Widget runtime configuration + API header injection.
 *
 * Called once from widget-entry.jsx BEFORE the React tree mounts.
 *
 * What it does:
 *   1. Reads company_id from the embed (script-tag attribute → window
 *      override → URL query param), in that priority order.
 *   2. Stashes it on window.__SEVA_CONFIG__ so any module can read it.
 *   3. Installs an axios request interceptor on the default axios instance
 *      — all `import axios from 'axios'` call sites in ChatWidget share
 *      this instance.
 *   4. Patches window.fetch to add the X-Company-Id header to requests
 *      hitting the configured API base. Non-API requests (Google Fonts,
 *      etc.) are passed through unmodified.
 *
 * If company_id is missing, both patches are still installed but inject
 * nothing — the backend falls back to its env-var COMPANY_ID, so the
 * widget keeps working in single-tenant mode during the rollout.
 *
 * The embed snippet looks like:
 *   <script src=".../seva-widget.js" data-company-id="<UUID>"></script>
 */
import axios from 'axios';

const HEADER = 'X-Company-Id';
const STATE_KEY = '__SEVA_CONFIG__';

let installed = false;

/* ────────────────────────────────────────────────────────────────────────
 * Widget design tokens
 *
 * The widget renders inside arbitrary host pages, so the admin app's CSS
 * custom properties (--foreground, --primary, etc.) aren't reliably
 * inheritable — host stylesheets may shadow them, or the host may not
 * load any of our base CSS at all. To stay isolated *and* still let
 * tenants re-skin semantic surfaces, we ship a small constant token map
 * and accept per-tenant overrides via the embed script tag:
 *
 *   <script src=".../seva-widget.js"
 *           data-company-id="<UUID>"
 *           data-widget-tokens='{"successAccent":"#16a34a"}'></script>
 *
 * Brand colours (foreground / primary) still come from the platform
 * tokens via `hsl(var(--foreground))` references in ChatWidget — that
 * path picks up the tenant's CSS variable overrides correctly when the
 * widget mounts in the dashboard preview. WIDGET_TOKENS only covers the
 * semantic colours (success / info / destructive / camera) that don't
 * have a brand component.
 * ──────────────────────────────────────────────────────────────────── */

const WIDGET_TOKEN_DEFAULTS = {
  // Surfaces
  modalSurface:      '#ffffff',
  fieldSurface:      '#f9fafb',
  chatInputBar:      '#F0F2F5', // WhatsApp-style input bar
  buttonInverse:     '#ffffff',

  // Text scale
  textPrimary:       '#111827',
  textSecondary:     '#374151',
  textMuted:         '#6b7280',
  textFaint:         '#9ca3af',
  textOnDark:        '#666666',

  // Borders
  borderDefault:     '#e5e7eb',

  // Presence indicators (online / offline dots on the widget header)
  statusOnline:      '#4ADE80',
  statusOffline:     '#EF4444',

  // Semantic — success (uploaded docs, completed flows)
  successBg:         '#f0fdf4',
  successBorder:     '#86efac',
  successText:       '#15803d',
  successAccent:     '#22c55e',
  successDeep:       '#065f46',

  // Semantic — info / links / "next-step" buttons (blue)
  infoBg:            '#eff6ff',
  infoBgAlt:         '#EFF6FF', // historical casing in one spot
  infoBgSoft:        '#f0f9ff',
  infoBorder:        '#2563EB',
  infoAccent:        '#3b82f6',
  infoDeep:          '#2563eb',

  // Semantic — destructive (delete / cancel buttons, errors)
  destructiveAccent: '#ef4444',
  destructiveSoft:   'rgba(239,68,68,0.85)',

  // Camera / OCR (purple)
  cameraAccent:      '#7c3aed',
  cameraBg:          '#f5f3ff',

  // Misc — a slightly different purple used by one "secondary action" button
  secondaryAccent:   '#8b5cf6',
};

function readWidgetTokens() {
  // Same selection precedence as readCompanyId — current script tag first,
  // then any tagged seva-widget script, then a plain data-widget-tokens.
  const currentScript =
    document.currentScript ||
    document.querySelector('script[data-widget-tokens][src*="seva-widget"]') ||
    document.querySelector('script[data-widget-tokens]');
  const raw = currentScript?.dataset?.widgetTokens;
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object') return parsed;
  } catch (err) {
    // Invalid JSON — log loudly once, fall back to defaults so the widget
    // still renders. A misconfigured embed shouldn't break the chat.
    // eslint-disable-next-line no-console
    console.warn('[seva-widget] data-widget-tokens is not valid JSON; using defaults.', err);
  }
  return null;
}

function readCompanyId() {
  // 1. Script-tag attribute — primary path
  const currentScript =
    document.currentScript ||
    document.querySelector('script[data-company-id][src*="seva-widget"]') ||
    document.querySelector('script[data-company-id]') ||
    document.querySelector('script[data-bot-id][src*="seva-widget"]') ||
    document.querySelector('script[data-bot-id]');
  const fromTag = currentScript?.dataset?.companyId || currentScript?.dataset?.botId;
  if (fromTag) return fromTag.trim();

  // 2. Pre-set window global (host page sets it before loading us)
  const fromWindow = window[STATE_KEY]?.companyId;
  if (fromWindow) return String(fromWindow).trim();

  // 3. URL query param — useful for local testing & previews
  try {
    const fromQuery = new URLSearchParams(window.location.search).get('company_id');
    if (fromQuery) return fromQuery.trim();
  } catch { /* SSR / sandbox — skip */ }

  return null;
}

function buildApiUrlMatcher() {
  // The widget is built with REACT_APP_BACKEND_URL pointed at the API host
  // (or empty for same-origin dev). Only inject the header on requests
  // that target THAT origin's /api/ path — never on third-party requests
  // (fonts, analytics) or the host page's own /api endpoints.
  //
  // NOTE: use the plain `process.env.REACT_APP_BACKEND_URL` form, NOT
  // optional chaining (`process.env?.REACT_APP_BACKEND_URL`). Both CRA's
  // webpack and Vite static-substitute the literal form at build time;
  // optional chaining prevents the substitution and the var stays unresolved
  // at runtime (where `process` doesn't exist), silently breaking URL
  // construction. Same pattern as ChatWidget.jsx's API_BASE.
  const apiBase = process.env.REACT_APP_BACKEND_URL || '';

  let baseOrigin = null;
  try {
    if (apiBase) baseOrigin = new URL(apiBase).origin;
  } catch { /* malformed — fall through to relative-only */ }

  return function isApiUrl(rawUrl) {
    if (!rawUrl) return false;
    try {
      // Resolve relative URLs against the current page; safe with both
      // string URLs and Request objects.
      const resolved = new URL(rawUrl, window.location.href);
      if (!resolved.pathname.startsWith('/api/') && !resolved.pathname.startsWith('/api?')) {
        // Allow exact "/api" too, no trailing slash
        if (resolved.pathname !== '/api') return false;
      }
      if (baseOrigin) return resolved.origin === baseOrigin;
      // Same-origin dev mode — only patch our own /api/ calls.
      return resolved.origin === window.location.origin;
    } catch {
      return false;
    }
  };
}

function patchAxios(companyId) {
  // Idempotent: a duplicate setup call wouldn't double-install because
  // setupWidget() guards on `installed`. We tag the interceptor anyway so
  // it's easy to spot in DevTools.
  axios.interceptors.request.use((cfg) => {
    if (!companyId) return cfg;
    cfg.headers = cfg.headers || {};
    // Don't overwrite if caller set their own.
    if (!cfg.headers[HEADER] && !cfg.headers[HEADER.toLowerCase()]) {
      cfg.headers[HEADER] = companyId;
    }
    return cfg;
  });
}

function patchFetch(companyId) {
  const originalFetch = window.fetch.bind(window);
  const isApiUrl = buildApiUrlMatcher();

  window.fetch = function patchedFetch(input, init = {}) {
    let url;
    if (typeof input === 'string') {
      url = input;
    } else if (input && typeof input === 'object' && 'url' in input) {
      url = input.url;
    }

    if (!companyId || !isApiUrl(url)) {
      return originalFetch(input, init);
    }

    // Inject without mutating the caller's init object.
    const headers = new Headers(
      init.headers ||
      (input && typeof input === 'object' && 'headers' in input ? input.headers : undefined)
    );
    if (!headers.has(HEADER)) {
      headers.set(HEADER, companyId);
    }

    return originalFetch(input, { ...init, headers });
  };
}

/**
 * One-shot setup. Call before mounting React.
 * Returns the resolved config object (also stashed on window.__SEVA_CONFIG__).
 */
export function setupWidget() {
  if (installed) return window[STATE_KEY];

  const companyId = readCompanyId();
  const tokenOverrides = readWidgetTokens();
  const tokens = { ...WIDGET_TOKEN_DEFAULTS, ...(tokenOverrides || {}) };

  const config = {
    ...(window[STATE_KEY] || {}),
    companyId: companyId || null,
    tokens,
  };
  window[STATE_KEY] = config;

  patchAxios(companyId);
  patchFetch(companyId);
  installed = true;

  if (!companyId) {
    // Loud once, not on every request. Backend falls back to env tenant.
    // eslint-disable-next-line no-console
    console.warn(
      '[seva-widget] No company_id provided via data-company-id attribute, ' +
      `window.${STATE_KEY}, or ?company_id= query param — falling back to default tenant.`
    );
  }

  return config;
}

/** Read the resolved company_id from anywhere in the React tree. */
export function getCompanyId() {
  return window[STATE_KEY]?.companyId || null;
}

/**
 * Resolved widget tokens (defaults merged with any data-widget-tokens
 * overrides). Returns the defaults verbatim if `setupWidget()` hasn't
 * been called yet — so importing this module from the main app (not the
 * widget bundle) still produces a usable palette.
 */
export function getWidgetTokens() {
  return window[STATE_KEY]?.tokens || WIDGET_TOKEN_DEFAULTS;
}

/**
 * Fetch the tenant's branding (bot name, avatar URL, colors, languages)
 * from the backend `/api/consular/widget-config` endpoint. Returns null
 * on any failure so the caller can gracefully fall back to defaults —
 * the widget must remain usable even if the config endpoint is down.
 *
 * The patched window.fetch will automatically attach the X-Company-Id
 * header, so this works without the caller threading the tenant.
 */
export async function fetchBranding() {
  // Plain `process.env.REACT_APP_BACKEND_URL` so the build's static
  // substitution kicks in — see buildApiUrlMatcher() above for why
  // optional chaining must not be used here.
  const apiBase = process.env.REACT_APP_BACKEND_URL || '';
  const url = `${apiBase}/api/consular/widget-config`;
  try {
    const res = await fetch(url, { method: 'GET' });
    if (!res.ok) return null;
    return await res.json();
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[seva-widget] branding fetch failed:', err);
    return null;
  }
}
