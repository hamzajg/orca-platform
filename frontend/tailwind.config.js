/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"IBM Plex Mono"', 'monospace'],
        sans: ['Inter', '-apple-system', 'sans-serif'],
        display: ['Orbitron', 'sans-serif'],
      },
      colors: {
        bg: {
          primary: '#0c1220',
          secondary: '#121b2e',
          tertiary: '#1a2640',
          elevated: '#1f2d45',
        },
        border: {
          subtle: 'rgba(100, 180, 255, 0.12)',
          DEFAULT: 'rgba(100, 180, 255, 0.20)',
          hover: 'rgba(0, 212, 255, 0.25)',
        },
        text: {
          primary: '#f0f4f8',
          secondary: '#a8b8c8',
          tertiary: '#7a8a9a',
          disabled: '#5a6a7a',
        },
        accent: {
          DEFAULT: '#00d4ff',
          dim: 'rgba(0, 212, 255, 0.10)',
          glow: 'rgba(0, 212, 255, 0.25)',
          hover: '#33ddff',
        },
        metric: {
          requests: '#00d4ff',
          latency: '#a78bfa',
          errors: '#f04d4d',
          success: '#10b981',
          throughput: '#22d3c8',
          tokens: '#f59e0b',
        },
        status: {
          healthy: '#10b981',
          degraded: '#f59e0b',
          offline: '#f04d4d',
          unknown: '#5a6a7a',
        },
      },
      borderRadius: {
        sm: '4px',
        md: '8px',
        lg: '12px',
        xl: '16px',
      },
      keyframes: {
        'pulse-dot': {
          '0%,100%': { opacity: '1' },
          '50%':     { opacity: '0.35' },
        },
        'pulse-glow': {
          '0%,100%': { boxShadow: '0 0 4px rgba(16, 185, 129, 0.4)' },
          '50%':     { boxShadow: '0 0 12px rgba(16, 185, 129, 0.8)' },
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
          '0%':   { 'background-position': '-200% 0' },
          '100%': { 'background-position': '200% 0' },
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 2.2s ease-in-out infinite',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'fade-in':   'fade-in 0.25s ease forwards',
        'slide-in':  'slide-in 0.2s ease forwards',
        blink:       'blink 0.8s step-end infinite',
        shimmer:     'shimmer 2s linear infinite',
      },
    },
  },
  plugins: [],
}
