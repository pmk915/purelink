import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
    "./api/**/*.{ts,tsx}",
    "./schemas/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))"
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))"
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))"
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))"
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))"
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))"
        }
      },
      borderRadius: {
        xl: "1rem",
        "2xl": "1.5rem"
      },
      boxShadow: {
        soft: "0 16px 40px -24px rgba(70, 85, 140, 0.22)",
        card: "0 16px 50px -30px rgba(60, 76, 126, 0.2)"
      },
      fontFamily: {
        sans: [
          "Manrope",
          "Aptos",
          "\"SF Pro Display\"",
          "\"Segoe UI\"",
          "\"Helvetica Neue\"",
          "Arial",
          "sans-serif"
        ],
        mono: [
          "\"JetBrains Mono\"",
          "\"SFMono-Regular\"",
          "Menlo",
          "Monaco",
          "Consolas",
          "\"Liberation Mono\"",
          "monospace"
        ]
      },
      backgroundImage: {
        "app-grid":
          "radial-gradient(circle at top left, rgba(79,70,229,0.08), transparent 24%), radial-gradient(circle at bottom right, rgba(59,130,246,0.08), transparent 18%)"
      }
    }
  },
  plugins: []
};

export default config;
