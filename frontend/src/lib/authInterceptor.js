/**
 * Global 401 / session-expiry handler for the admin app.
 *
 * Why a separate file: there are ~30+ scattered fetch/axios calls in the
 * admin pages that hand-roll the Authorization header. Before this
 * interceptor, a JWT that had expired (default 7-day lifetime) would
 * silently 401 every protected request — each call site shows its own
 * "Failed to load …" error and the user is stuck until they manually
 * log out and back in.
 *
 * What this does:
 *   - Patches axios.interceptors.response AND wraps window.fetch.
 *   - On 401 from any /api/* response (except /api/auth/login, where 401
 *     is the normal "bad credentials" path), if the user is currently
 *     logged in (localStorage has a token), we:
 *       1. Clear the auth keys from localStorage.
 *       2. Stash a one-shot flag so the next page (LoginPage) can toast.
 *       3. Hard-redirect to /login so any in-flight component state is
 *          discarded — half-loaded dashboards otherwise keep firing more
 *          401s.
 *   - Idempotent: setupAuthInterceptor() is safe to call once at boot.
 *
 * LoginPage reads `auth_expired_flash` on mount and surfaces the toast
 * (see LoginPage.jsx). The flag survives the full-page navigation that
 * `window.location.href = …` triggers.
 */
import axios from "axios";

const AUTH_KEYS = ["token", "user_type", "user_id", "company_id", "password_change_required"];
const FLASH_KEY = "auth_expired_flash";

let installed = false;

function isLoggedIn() {
  return !!localStorage.getItem("token");
}

function isApiPath(url) {
  if (!url) return false;
  try {
    const resolved = new URL(url, window.location.href);
    return resolved.pathname.startsWith("/api/") || resolved.pathname === "/api";
  } catch {
    return false;
  }
}

function isLoginPath(url) {
  if (!url) return false;
  try {
    const resolved = new URL(url, window.location.href);
    return resolved.pathname === "/api/auth/login";
  } catch {
    return false;
  }
}

function handleExpiry() {
  // Avoid loop: if we're already on /login, just clear and stay put.
  AUTH_KEYS.forEach((k) => localStorage.removeItem(k));
  localStorage.setItem(FLASH_KEY, "1");
  if (window.location.pathname !== "/login") {
    window.location.href = "/login";
  }
}

function patchAxios() {
  axios.interceptors.response.use(
    (response) => response,
    (error) => {
      const status = error?.response?.status;
      const url = error?.config?.url;
      if (status === 401 && isLoggedIn() && !isLoginPath(url)) {
        handleExpiry();
      }
      return Promise.reject(error);
    }
  );
}

function patchFetch() {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async function patchedFetch(input, init) {
    const response = await originalFetch(input, init);
    if (response.status === 401) {
      const url = typeof input === "string" ? input : input && input.url;
      if (isApiPath(url) && !isLoginPath(url) && isLoggedIn()) {
        handleExpiry();
      }
    }
    return response;
  };
}

export function setupAuthInterceptor() {
  if (installed) return;
  patchAxios();
  patchFetch();
  installed = true;
}

export function consumeExpiryFlash() {
  const had = localStorage.getItem(FLASH_KEY);
  if (had) localStorage.removeItem(FLASH_KEY);
  return !!had;
}
