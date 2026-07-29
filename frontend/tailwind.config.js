/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Heat severity scale
        heat: {
          1: "#fef0d9",
          2: "#fdcc8a",
          3: "#fc8d59",
          4: "#e34a33",
          5: "#b30000",
        },
        solar: {
          50: "#fffbe6",
          100: "#fff3b3",
          200: "#ffe680",
          300: "#ffd54d",
          400: "#ffbf1a",
          500: "#f59e0b", // Warm amber
          600: "#d97706",
          700: "#b45309",
          800: "#92400e",
          900: "#78350f",
        },
        flame: {
          50: "#fff5f2",
          100: "#ffe6e0",
          200: "#ffccbf",
          300: "#ff9980",
          400: "#ff5722", // Solar orange/flame
          500: "#f44336",
          600: "#e53935",
          700: "#d32f2f",
          800: "#c62828",
          900: "#b71c1c",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glass: "0 10px 30px -5px rgba(0, 0, 0, 0.05), 0 4px 12px -2px rgba(0, 0, 0, 0.02)",
        glow: "0 0 25px -5px rgba(245, 158, 11, 0.25)",
        flame: "0 0 25px -5px rgba(255, 87, 34, 0.3)",
      },
      keyframes: {
        pulseGlow: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.6", transform: "scale(1.08)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "pulse-glow": "pulseGlow 2.5s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        shimmer: "shimmer 2s infinite",
      },
    },
  },
  plugins: [],
};
