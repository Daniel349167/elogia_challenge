/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1d1e18",
        paper: "#f8f7f1",
        rust: "#b85042",
        pine: "#18453b",
        amber: "#d79b00"
      },
      boxShadow: {
        panel: "0 20px 50px rgba(29, 30, 24, 0.15)",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        rise: "rise 280ms ease-out",
      },
    },
  },
  plugins: [],
};
