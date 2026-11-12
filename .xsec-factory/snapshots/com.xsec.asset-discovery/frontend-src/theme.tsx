import { useLayoutEffect, useState, type ReactNode } from "react";
import { ThemeProvider } from "@xsec/ui-react";
import { themeAttributes, type ThemeSettings } from "@xsec/design-tokens";
import type { PluginHost } from "./types";

function parseTheme(theme: Record<string, string>): ThemeSettings {
  const mode = theme["color-mode"];
  if (mode !== "light" && mode !== "dark") throw new Error("Host color mode is invalid");
  const density = theme["ui-density"];
  if (density !== "compact" && density !== "comfortable") throw new Error("Host UI density is invalid");
  const motion = theme["reduce-motion"];
  if (motion !== "true" && motion !== "false") throw new Error("Host reduced motion preference is invalid");
  const size = theme["ui-font-size"];
  if (!/^\d+(?:\.\d+)?px$/.test(size)) throw new Error("Host UI font size is invalid");
  const settings: ThemeSettings = { colorMode: mode, density, fontScale: Number(size.slice(0, -2)) / 14, reducedMotion: motion === "true", locale: "zh-CN" };
  themeAttributes(settings);
  return settings;
}

function readInitialTheme(): ThemeSettings {
  const style = getComputedStyle(document.documentElement);
  return parseTheme(Object.fromEntries(["color-mode", "ui-density", "ui-font-size", "reduce-motion"].map(name => [name, style.getPropertyValue("--xsec-" + name).trim()])));
}

export function PluginTheme({ host, children }: { host: PluginHost; children: ReactNode }) {
  const [settings, setSettings] = useState(readInitialTheme);
  useLayoutEffect(() => {
    const subscription = host.onTheme(theme => setSettings(parseTheme(theme)));
    return () => subscription.dispose();
  }, [host]);
  return <ThemeProvider settings={settings}>{children}</ThemeProvider>;
}
