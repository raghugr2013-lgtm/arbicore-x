// Tailwind config — ArbiCore Opportunity Center
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        // distinctive non-Inter stack — operator console aesthetic
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        // ArbiCore terminal palette: deep indigo-graphite with sodium-amber accent
        bg: {
          base: '#0b0d14',
          panel: '#11141d',
          raised: '#161a26',
          line: '#1d2230',
        },
        ink: {
          50: '#f4f6fb',
          200: '#c2c8d6',
          400: '#7a8295',
          600: '#4c536a',
        },
        accent: {
          amber: '#f6b352',
          green: '#3ddc84',
          red:   '#ff5d5d',
          violet:'#7c6cff',
        },
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(255,255,255,0.04) inset, 0 0 0 1px rgba(255,255,255,0.04)',
      },
    },
  },
  plugins: [],
}
