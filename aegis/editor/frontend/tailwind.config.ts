import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#ffffff",
          secondary: "#f8fafc", // slate-50
          tertiary: "#f1f5f9", // slate-100
          hover: "#e2e8f0", // slate-200
        },
        border: {
          DEFAULT: "#e2e8f0", // slate-200
          strong: "#cbd5e1", // slate-300
        },
        accent: {
          DEFAULT: "#6366f1", // indigo-500
          hover: "#4f46e5", // indigo-600
          light: "#e0e7ff", // indigo-100
          subtle: "#eef2ff", // indigo-50
        },
        status: {
          success: "#10b981", // emerald-500
          "success-light": "#d1fae5", // emerald-100
          warning: "#f59e0b", // amber-500
          "warning-light": "#fef3c7", // amber-100
          error: "#ef4444", // red-500
          "error-light": "#fee2e2", // red-100
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        md: "8px",
        lg: "12px",
      },
      width: {
        sidebar: "280px",
      },
    },
  },
  plugins: [],
} satisfies Config;
