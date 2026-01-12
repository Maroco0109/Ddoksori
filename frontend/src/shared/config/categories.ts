import type { PostCategory } from '@/shared/types';

export const POST_CATEGORIES = {
  ALL: 'all',
  CASE_SHARING: 'case-sharing',
  QNA: 'qna',
  TIPS: 'tips',
} as const;

export const CATEGORY_LABELS: Record<PostCategory | 'all', string> = {
  all: '전체',
  'case-sharing': '분쟁해결사례 공유',
  qna: '무엇이든 물어보세요',
  tips: '소비자 꿀팁/노하우',
};

export const CATEGORY_DISPLAY_MAP: Record<PostCategory, string> = {
  'case-sharing': '분쟁해결사례/공유',
  qna: '무엇이든/물어보세요',
  tips: '소비자/꿀팁/노하우',
};

export const DISPLAY_TO_CATEGORY_MAP: Record<string, PostCategory> = {
  '분쟁해결사례/공유': 'case-sharing',
  '무엇이든/물어보세요': 'qna',
  '소비자/꿀팁/노하우': 'tips',
};
