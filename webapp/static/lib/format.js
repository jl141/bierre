/**
 * Locale-aware number and date formatting.
 *
 * The locale comes from `capabilities.default_locale` (and later from the
 * user's account preference), never from `navigator.language`: the string
 * catalogue and the number formatting have to agree, and only the server knows
 * which catalogues shipped. `Intl` objects are cached because constructing one
 * per table cell is the classic way to make a 120-row render feel slow.
 */

let activeLocale = "en";
const formatters = new Map();

/** @param {string} locale A BCP 47 tag that appears in `capabilities.locales`. */
export function setLocale(locale) {
  if (!locale || locale === activeLocale) return;
  activeLocale = locale;
  formatters.clear();
}

export function getLocale() {
  return activeLocale;
}

function numberFormat(options) {
  const key = `${activeLocale}:${JSON.stringify(options)}`;
  let formatter = formatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat(activeLocale, options);
    formatters.set(key, formatter);
  }
  return formatter;
}

/** Integer with grouping separators: `1234` → `1,234` in `en`. */
export function formatCount(value) {
  return numberFormat().format(value);
}

/** Fixed-precision decimal: `formatDecimal(4.25, 1)` → `4.3`. */
export function formatDecimal(value, digits) {
  return numberFormat({ minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value);
}

/** Percentage from a 0–100 value, with the locale's own sign placement. */
export function formatPercent(value) {
  return numberFormat({ style: "percent", maximumFractionDigits: 0 }).format(value / 100);
}

/** Short absolute date from an ISO 8601 string. Empty string if unparseable. */
export function formatDate(isoString) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(activeLocale, { dateStyle: "medium" }).format(date);
}

const RELATIVE_UNITS = [
  ["year", 365 * 24 * 60 * 60 * 1000],
  ["month", 30 * 24 * 60 * 60 * 1000],
  ["day", 24 * 60 * 60 * 1000],
  ["hour", 60 * 60 * 1000],
  ["minute", 60 * 1000],
];

/** `"3 days ago"`, localised. Falls back to the absolute date if unparseable. */
export function formatRelativeTime(isoString, now = Date.now()) {
  const date = new Date(isoString);
  if (Number.isNaN(date.getTime())) return "";

  const elapsed = date.getTime() - now;
  const relative = new Intl.RelativeTimeFormat(activeLocale, { numeric: "auto" });
  for (const [unit, milliseconds] of RELATIVE_UNITS) {
    if (Math.abs(elapsed) >= milliseconds) {
      return relative.format(Math.round(elapsed / milliseconds), unit);
    }
  }
  return relative.format(Math.round(elapsed / 1000), "second");
}
