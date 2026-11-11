/** @type {import('tailwindcss').Config} */
// Every themed color resolves to a CSS variable (see src/index.css) so light/dark and the IBI palette swap in one place.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`
const scale = (name, steps) => Object.fromEntries(steps.map((s) => [s, v(`${name}-${s}`)]))
const ALL = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900]

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Heebo', 'system-ui', 'sans-serif'] },
      colors: {
        surface: v('surface'),
        page: v('page'),
        primary: v('primary'),
        'on-primary': v('on-primary'),
        navy: scale('navy', ALL),
        brand: scale('brand', ALL),
        slate: scale('slate', ALL),
        emerald: scale('emerald', ALL),
        amber: scale('amber', ALL),
        red: scale('red', ALL),
        sky: scale('sky', ALL),
        orange: scale('orange', ALL),
        violet: scale('violet', ALL),
      },
      boxShadow: {
        card: '0 1px 2px rgb(22 25 50 / 0.04), 0 4px 16px -4px rgb(22 25 50 / 0.08)',
        'card-hover': '0 2px 4px rgb(22 25 50 / 0.06), 0 14px 32px -10px rgb(22 25 50 / 0.22)',
      },
    },
  },
  plugins: [],
}
