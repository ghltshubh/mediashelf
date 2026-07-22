// Display locale (M8.1). The formatting locale is INDEPENDENT of the content
// region: `country` decides which titles stream where; the locale here only
// affects how numbers and dates are *presented*. An English speaker in France
// keeps English formatting and still sees French availability. Defaults to the
// browser language; overridable in Settings. Structured so a future UI-text
// translation layer can read the same setting without rework.

import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

const BROWSER_LOCALE =
  typeof navigator !== "undefined" && navigator.language ? navigator.language : "en";

/** The active formatting locale. Prefers the user's saved choice, else the
    browser language. Cheap to call in many components — the settings query is
    shared via react-query's cache. */
export function useLocale(): string {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  return settings.data?.locale || BROWSER_LOCALE;
}

export function fmtNumber(n: number, locale: string): string {
  try {
    return new Intl.NumberFormat(locale).format(n);
  } catch {
    return String(n);
  }
}

export function fmtDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  try {
    return new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "short",
      day: "numeric",
    }).format(d);
  } catch {
    return d.toDateString();
  }
}

// Offered in the Settings selector. "" = follow the browser. Labels are shown
// in each language's own name so they're recognizable regardless of UI text.
export const LOCALE_OPTIONS: { code: string; label: string }[] = [
  { code: "", label: "Auto (browser)" },
  { code: "en-US", label: "English (US)" },
  { code: "en-GB", label: "English (UK)" },
  { code: "es-ES", label: "Español" },
  { code: "fr-FR", label: "Français" },
  { code: "de-DE", label: "Deutsch" },
  { code: "it-IT", label: "Italiano" },
  { code: "pt-BR", label: "Português (Brasil)" },
  { code: "nl-NL", label: "Nederlands" },
  { code: "hi-IN", label: "हिन्दी" },
  { code: "ja-JP", label: "日本語" },
  { code: "ko-KR", label: "한국어" },
  { code: "zh-CN", label: "中文（简体）" },
];
