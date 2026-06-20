/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'resilience-dark': '#0f172a',
        'resilience-primary': '#3b82f6',
        'resilience-critical': '#ef4444',
        'resilience-warning': '#f59e0b',
        'resilience-safe': '#10b981',
      }
    },
  },
  plugins: [],
}
