/** Shared locale store. Never translate business identifiers or submitted enum values. */
import { useSyncExternalStore, useEffect } from "react";
import ur from "./locales/ur.json";
let locale: "en" | "ur" =
  localStorage.getItem("stockdesk-language") === "ur" ? "ur" : "en";
const listeners = new Set<() => void>();
export function setLanguage(value: "en" | "ur") {
  locale = value;
  localStorage.setItem("stockdesk-language", value);
  listeners.forEach((fn) => fn());
}
export function t(value: string): string {
  return locale === "ur"
    ? (ur as Record<string, string>)[value] || value
    : value;
}
export function useLanguage() {
  const language = useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => {
        listeners.delete(fn);
      };
    },
    () => locale,
    () => "en" as const,
  );
  useEffect(() => {
    document.documentElement.lang = language;
    document.documentElement.dir = language === "ur" ? "rtl" : "ltr";
  }, [language]);
  return [language, setLanguage] as const;
}
