export interface TerminalTheme {
  background: string;
  foreground: string;
  cursor: string;
  selectionBackground: string;
  black: string;
  red: string;
  green: string;
  yellow: string;
  blue: string;
  magenta: string;
  cyan: string;
  white: string;
  brightBlack: string;
  brightRed: string;
  brightGreen: string;
  brightYellow: string;
  brightBlue: string;
  brightMagenta: string;
  brightCyan: string;
  brightWhite: string;
}

export interface ThemeConfig {
  name: string;
  isDark: boolean;
  terminal: TerminalTheme;
}

export const themes: Record<string, ThemeConfig> = {
  light: {
    name: "Light (Default)",
    isDark: false,
    terminal: {
      background: "#f8fafc",
      foreground: "#0f172a",
      cursor: "#0f172a",
      selectionBackground: "rgba(59, 130, 246, 0.2)",
      black: "#0f172a",
      red: "#dc2626",
      green: "#16a34a",
      yellow: "#ca8a04",
      blue: "#2563eb",
      magenta: "#9333ea",
      cyan: "#0891b2",
      white: "#cbd5e1",
      brightBlack: "#475569", // Darker gray for high contrast on light backgrounds
      brightRed: "#ef4444",
      brightGreen: "#22c55e",
      brightYellow: "#eab308",
      brightBlue: "#3b82f6",
      brightMagenta: "#a855f7",
      brightCyan: "#06b6d4",
      brightWhite: "#f8fafc",
    }
  },
  dark: {
    name: "Dark",
    isDark: true,
    terminal: {
      background: "#0f172a", // slate-900
      foreground: "#f8fafc", // slate-50
      cursor: "#f8fafc",
      selectionBackground: "rgba(255, 255, 255, 0.15)",
      black: "#020617",
      red: "#ef4444",
      green: "#22c55e",
      yellow: "#eab308",
      blue: "#3b82f6",
      magenta: "#a855f7",
      cyan: "#06b6d4",
      white: "#cbd5e1",
      brightBlack: "#64748b",
      brightRed: "#f87171",
      brightGreen: "#4ade80",
      brightYellow: "#facc15",
      brightBlue: "#60a5fa",
      brightMagenta: "#c084fc",
      brightCyan: "#22d3ee",
      brightWhite: "#f8fafc",
    }
  },
  solarizedLight: {
    name: "Solarized Light",
    isDark: false,
    terminal: {
      background: "#fdf6e3", // base3
      foreground: "#657b83", // base00
      cursor: "#657b83",
      selectionBackground: "rgba(147, 161, 161, 0.3)",
      black: "#073642",
      red: "#dc322f",
      green: "#859900",
      yellow: "#b58900",
      blue: "#268bd2",
      magenta: "#d33682",
      cyan: "#2aa198",
      white: "#eee8d5",
      brightBlack: "#586e75", // base01 - Thought logs visible
      brightRed: "#cb4b16",
      brightGreen: "#586e75",
      brightYellow: "#93a1a1",
      brightBlue: "#839496",
      brightMagenta: "#6c71c4",
      brightCyan: "#2aa198",
      brightWhite: "#fdf6e3",
    }
  },
  solarizedDark: {
    name: "Solarized Dark",
    isDark: true,
    terminal: {
      background: "#002b36", // base03
      foreground: "#839496", // base0
      cursor: "#839496",
      selectionBackground: "rgba(7, 54, 66, 0.5)",
      black: "#073642",
      red: "#dc322f",
      green: "#859900",
      yellow: "#b58900",
      blue: "#268bd2",
      magenta: "#d33682",
      cyan: "#2aa198",
      white: "#eee8d5",
      brightBlack: "#586e75", // base01
      brightRed: "#cb4b16",
      brightGreen: "#586e75",
      brightYellow: "#93a1a1",
      brightBlue: "#839496",
      brightMagenta: "#6c71c4",
      brightCyan: "#2aa198",
      brightWhite: "#fdf6e3",
    }
  },
  dracula: {
    name: "Dracula",
    isDark: true,
    terminal: {
      background: "#282a36",
      foreground: "#f8f8f2",
      cursor: "#f8f8f2",
      selectionBackground: "rgba(255, 255, 255, 0.1)",
      black: "#21222c",
      red: "#ff5555",
      green: "#50fa7b",
      yellow: "#f1fa8c",
      blue: "#bd93f9",
      magenta: "#ff79c6",
      cyan: "#8be9fd",
      white: "#bfbfbf",
      brightBlack: "#6272a4",
      brightRed: "#ff6e6e",
      brightGreen: "#69ff94",
      brightYellow: "#ffffa5",
      brightBlue: "#d6acff",
      brightMagenta: "#ff92df",
      brightCyan: "#a4ffff",
      brightWhite: "#ffffff",
    }
  },
  oneDark: {
    name: "One Dark",
    isDark: true,
    terminal: {
      background: "#282c34",
      foreground: "#abb2bf",
      cursor: "#528bff",
      selectionBackground: "rgba(82, 139, 255, 0.25)",
      black: "#1e2127",
      red: "#e06c75",
      green: "#98c379",
      yellow: "#d19a66",
      blue: "#61afef",
      magenta: "#c678dd",
      cyan: "#56b6c2",
      white: "#abb2bf",
      brightBlack: "#5c6370",
      brightRed: "#e06c75",
      brightGreen: "#98c379",
      brightYellow: "#d19a66",
      brightBlue: "#61afef",
      brightMagenta: "#c678dd",
      brightCyan: "#56b6c2",
      brightWhite: "#ffffff",
    }
  }
};
