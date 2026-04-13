/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
        sans: ['"DM Sans"', 'sans-serif'],
      },
      colors: {
        bg: {
          0: '#07090b',
          1: '#0d1117',
          2: '#131920',
          3: '#192028',
          4: '#1f2a33',
          5: '#263340',
        },
        border: {
          DEFAULT: '#1c2a35',
          2: '#253545',
          3: '#2f4255',
        },
        ink: {
          0: '#e6eef5',
          1: '#8fa3b0',
          2: '#4d6475',
          3: '#2d4050',
        },
        amber: {
          DEFAULT: '#f0a030',
          dim:     '#6b420a',
          glow:    '#f0a03040',
        },
        jade: {
          DEFAULT: '#2fd87c',
          dim:     '#134d2c',
          glow:    '#2fd87c30',
        },
        crimson: {
          DEFAULT: '#f05c5c',
          dim:     '#5c1515',
          glow:    '#f05c5c30',
        },
        sky: {
          DEFAULT: '#45a0e8',
          dim:     '#143558',
          glow:    '#45a0e830',
        },
        teal: {
          DEFAULT: '#22d3c8',
          dim:     '#0c3d3a',
          glow:    '#22d3c830',
        },
        violet: {
          DEFAULT: '#a78bfa',
          dim:     '#2d1f5e',
        },
      },
      keyframes: {
        'pulse-dot': {
          '0%,100%': { opacity: '1' },
          '50%':     { opacity: '0.35' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateX(-8px)' },
          to:   { opacity: '1', transform: 'translateX(0)' },
        },
        blink: {
          '0%,100%': { opacity: '1' },
          '50%':     { opacity: '0' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 2.2s ease-in-out infinite',
        'fade-in':   'fade-in 0.25s ease forwards',
        'slide-in':  'slide-in 0.2s ease forwards',
        blink:       'blink 0.8s step-end infinite',
        shimmer:     'shimmer 2s linear infinite',
      },
    },
  },
  plugins: [],
}
