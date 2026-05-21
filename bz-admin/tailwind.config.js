/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#2563eb', // BuyerZone Blue
          light: '#eff6ff',
          dark: '#1e40af',
        },
        sidebar: {
          bg: '#f8fafc',
          active: '#eff6ff',
          text: '#64748b',
          activeText: '#2563eb',
        }
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
      },
      boxShadow: {
        card: '0 2px 4px rgba(0,0,0,0.05)',
        'card-hover': '0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05)',
      }
    },
  },
  plugins: [],
}
