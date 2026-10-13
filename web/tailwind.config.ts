import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        terminal: {
          950: "#080B10",
          900: "#0D1117",
          850: "#131822",
          800: "#18202D",
          700: "#243042",
          600: "#36465D",
          500: "#4B5F7D",
          400: "#768DAE",
          300: "#A2B4CC",
          200: "#CDD9E8",
          100: "#E9EFF7",
        },
        profit: {
          DEFAULT: "#10B981",
          dim: "#065F46",
          bg: "#064E3B20",
        },
        loss: {
          DEFAULT: "#EF4444",
          dim: "#991B1B",
          bg: "#7F1D1D20",
        },
        warning: {
          DEFAULT: "#F59E0B",
          dim: "#92400E",
          bg: "#78350F20",
        },
        accent: {
          DEFAULT: "#38BDF8",
          dim: "#0369A1",
          bg: "#0C4A6E20",
        },
      },
      fontFamily: {
        mono: [
          "JetBrains Mono",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "Courier New",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
