"use client";

import { Sun, Moon, Monitor } from "lucide-react";
import { useTheme } from "./ThemeProvider";
import { useChatStore } from "@/lib/store";
import { MODELS } from "@/lib/constants";
import { cn } from "@/lib/utils";

export function Header() {
  const { theme, setTheme } = useTheme();
  const { settings, updateSettings } = useChatStore();

  const themeIcons = {
    light: Sun,
    dark: Moon,
    system: Monitor,
  } as const;

  const ThemeIcon = themeIcons[theme];
  const nextTheme = theme === "dark" ? "light" : theme === "light" ? "system" : "dark";

  return (
    <header className="flex items-center justify-between px-4 py-2.5 border-b border-surface-800 bg-surface-900/50 backdrop-blur-sm">
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-medium text-surface-100">Chat</h1>
      </div>

      <div className="flex items-center gap-2">
        {/* Model selector */}
        <select
          value={settings.model}
          onChange={(e) => updateSettings({ model: e.target.value })}
          className={cn(
            "text-xs bg-surface-800 border border-surface-700 rounded-md px-2 py-1",
            "text-surface-300 focus:outline-none focus:ring-1 focus:ring-brand-500"
          )}
        >
          {MODELS.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>

        {/* Theme toggle */}
        <button
          onClick={() => setTheme(nextTheme)}
          className="p-1.5 rounded-md text-surface-400 hover:text-surface-100 hover:bg-surface-800 transition-colors"
          title={`Switch to ${nextTheme} theme`}
        >
          <ThemeIcon className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
