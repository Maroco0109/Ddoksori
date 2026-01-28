export const ROUTES = {
  HOME: '/',
  PROCEDURE: '/procedure',
  CHAT: '/chat',
  BOARD: '/board',
  MYPAGE: '/mypage',
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];
