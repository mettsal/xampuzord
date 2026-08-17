/** Tailwind build config — gera static/css/tailwind.css (ver package.json).
 *  Substitui o Play CDN: escaneia templates e JS em busca das classes usadas. */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './templates/**/*.html',
    './static/js/**/*.js',
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
