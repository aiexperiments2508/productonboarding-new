import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
} from "react";
import type { ReactNode } from "react";

/* Theme, density and brand hue.
 *
 * Three independent axes, one provider, because they share a persistence
 * scheme and all three write to <html> - splitting them into three providers
 * would triple the boilerplate to save nothing.
 *
 * The initial values are read back from the same localStorage keys the inline
 * script in index.html already used before first paint. This provider does not
 * apply them on mount for that reason: doing so would be a second write of a
 * value that is already on the element. It applies on *change*.
 */

export type Theme = "light" | "dark" | "system";
export type Density = "comfortable" | "compact";

const KEY = { theme: "sc.theme", density: "sc.density", hue: "sc.brandHue" };

/** Brand presets. The whole palette derives from the hue, so these are one
 *  number each rather than a set of swatches to keep in sync. */
export const BRAND_PRESETS = [
  { id: "indigo", label: "Indigo", hue: 250 },
  { id: "azure", label: "Azure", hue: 232 },
  { id: "teal", label: "Teal", hue: 195 },
  { id: "violet", label: "Violet", hue: 285 },
  { id: "slate", label: "Graphite", hue: 262 },
] as const;

export const DEFAULT_HUE = 250;

interface ThemeContextValue {
  theme: Theme;
  setTheme: (t: Theme) => void;
  /** What `theme` actually resolves to right now. "system" is never returned. */
  resolvedTheme: "light" | "dark";
  density: Density;
  setDensity: (d: Density) => void;
  brandHue: number;
  setBrandHue: (h: number) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T | null) ?? fallback;
  } catch {
    return fallback;
  }
}

function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode - the setting simply does not survive the session */
  }
}

const prefersDark = () =>
  typeof matchMedia === "function" &&
  matchMedia("(prefers-color-scheme: dark)").matches;

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() =>
    readStored<Theme>(KEY.theme, "system"));
  const [density, setDensityState] = useState<Density>(() =>
    readStored<Density>(KEY.density, "comfortable"));
  const [brandHue, setBrandHueState] = useState<number>(() => {
    const raw = readStored(KEY.hue, "");
    const n = Number(raw);
    return raw && Number.isFinite(n) ? n : DEFAULT_HUE;
  });
  const [systemDark, setSystemDark] = useState(prefersDark);

  // Track the OS preference for as long as "system" might be selected. The
  // listener stays mounted regardless of the current choice: a user on Light
  // who switches to System should get the correct answer immediately, not
  // whatever the OS happened to be when the listener was last attached.
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const query = matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  const resolvedTheme: "light" | "dark" =
    theme === "system" ? (systemDark ? "dark" : "light") : theme;

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    persist(KEY.theme, next);
    const root = document.documentElement;
    // "system" removes the attribute rather than setting it to anything: the
    // CSS resolves the OS preference through :root:not([data-theme="light"]),
    // so the absence of the attribute IS the system state.
    if (next === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", next);
  }, []);

  const setDensity = useCallback((next: Density) => {
    setDensityState(next);
    persist(KEY.density, next);
    document.documentElement.setAttribute("data-density", next);
  }, []);

  const setBrandHue = useCallback((next: number) => {
    setBrandHueState(next);
    persist(KEY.hue, String(next));
    document.documentElement.style.setProperty("--brand-hue", String(next));
  }, []);

  // One reconciliation on mount, for the case the inline script could not run
  // (storage blocked, script stripped by a proxy). Cheap, and it means the
  // element state is guaranteed to match React state from here on.
  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    root.setAttribute("data-density", density);
    root.style.setProperty("--brand-hue", String(brandHue));
    // Intentionally mount-only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo(
    () => ({
      theme, setTheme, resolvedTheme,
      density, setDensity, brandHue, setBrandHue,
    }),
    [theme, setTheme, resolvedTheme, density, setDensity, brandHue, setBrandHue]
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside <ThemeProvider>");
  return ctx;
}
