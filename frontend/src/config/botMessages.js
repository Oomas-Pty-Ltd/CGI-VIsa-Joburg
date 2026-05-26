/**
 * ====================================================================
 * BOT — MESSAGE CONFIGURATION (DEFAULTS ONLY)
 * ====================================================================
 *
 * Per-tenant runtime values come from /api/consular/widget-config, which
 * returns the tenant's BotConfig.public_branding(). The constants below
 * are the last-resort fallbacks used only when widget-config has not been
 * fetched (or returned empty for a field). Nothing here is brand-specific.
 *
 * Bot name, organisation name, greeting, advisories, language list, contact
 * info, branding colours, etc. live on the tenant_bot_config document and
 * are editable from the super-admin Bot Config tab.
 */

export const BOT_CONFIG = {
  title:        "",
  subtitle:     "",
  tagline:      "",
  organization: "",
  location:     "",
};

export const GREETING_MESSAGE = "";

export const ADVISORY_MESSAGES = [];

// Language detector vocabulary — kept here so the menu falls back to a
// reasonable list when widget-config has not loaded yet. The runtime list
// shown to the user comes from bot_config.supported_languages.
export const SUPPORTED_LANGUAGES = ["English"];

