/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './**/templates/**/*.html',
    './static/js/**/*.js',
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        obsidian: {
          950: '#09090b',
          900: '#0f172a',
          800: '#18181b',
          700: '#1e293b',
          border: '#27272a',
        },
        slate: {
          canvas: '#f8fafc',
          card: '#ffffff',
          border: '#e2e8f0',
        },
        aether: {
          blue: '#2563eb',
          'blue-hover': '#1d4ed8',
          'blue-subtle': '#1e3a8a',
          emerald: '#10b981',
          rose: '#f43f5e',
          amber: '#f59e0b',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      }
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/typography'),
  ],
}
