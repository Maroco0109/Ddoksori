import type { Config } from 'tailwindcss';

export default {
  darkMode: ['class'],
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // 1번 팔레트: 부드러운 라벤더 (메인)
        'dark-navy': '#2B2D42',
        'gray-purple': '#555B6E',
        lavender: '#B8A9C9',
        'beige-pink': '#D4C5D0',
        ivory: '#FAF0E6',

        // 2번 팔레트: 틸 (포인트)
        'deep-teal': '#0A7E8C',
        'mint-green': '#8ECFC0',
        coral: '#E9967A',
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'Pretendard',
          'Segoe UI',
          'sans-serif',
        ],
      },
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },
    },
  },
  plugins: [],
} satisfies Config;
