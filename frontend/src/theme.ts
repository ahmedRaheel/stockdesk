/**
 * Presentation-only helpers: which Bootstrap stylesheet is active (LTR/RTL)
 * and whether the interface is light or dark. Nothing here touches app data.
 */
import { useSyncExternalStore } from "react";
import bootstrapLtr from "bootstrap/dist/css/bootstrap.min.css?url";
import bootstrapRtl from "bootstrap/dist/css/bootstrap.rtl.min.css?url";

const LINK_ID = "bootstrap-css";

/** Bootstrap ships a separate RTL build, so swap the <link> when the language flips. */
export function applyBootstrapDirection(dir: "ltr" | "rtl") {
  const href = dir === "rtl" ? bootstrapRtl : bootstrapLtr;
  let link = document.getElementById(LINK_ID) as HTMLLinkElement | null;
  if (!link) {
    link = document.createElement("link");
    link.id = LINK_ID;
    link.rel = "stylesheet";
    // Sit before our own CSS so our tokens always win the cascade.
    document.head.prepend(link);
  }
  if (link.getAttribute("href") !== href) link.setAttribute("href", href);
}

export type ColorMode = "light" | "dark";
const MODE_KEY = "stockdesk-color-mode";
const modeListeners = new Set<() => void>();

function readMode(): ColorMode {
  try {
    const saved = localStorage.getItem(MODE_KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* private mode: fall through to the OS preference */
  }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

let mode: ColorMode = readMode();
document.documentElement.setAttribute("data-bs-theme", mode);

export function setColorMode(next: ColorMode) {
  mode = next;
  document.documentElement.setAttribute("data-bs-theme", next);
  try {
    localStorage.setItem(MODE_KEY, next);
  } catch {
    /* non-fatal: preference just won't persist */
  }
  modeListeners.forEach((fn) => fn());
}

export function useColorMode() {
  const current = useSyncExternalStore(
    (fn) => {
      modeListeners.add(fn);
      return () => {
        modeListeners.delete(fn);
      };
    },
    () => mode,
    () => "light" as const,
  );
  return [current, setColorMode] as const;
}
