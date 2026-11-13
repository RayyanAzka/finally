import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#0a0e14', 900: '#0d1117', 800: '#131a24', 700: '#1a2330', 600: '#243040', 500: '#33425a' },
        accent: '#ecad0a',
        brand: '#209dd7',
        violet: '#753991',
        up: '#26c281',
        down: '#ef4b5f',
        mute: '#7d8b9f',
      },
      fontFamily: {
        sans: ['"Segoe UI"', 'system-ui', '-apple-system', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', '"Cascadia Mono"', '"SF Mono"', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
};
export default config;
