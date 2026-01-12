export const ROUTES = {
  HOME: '/',
  PROCEDURE: '/procedure',
  CHAT: '/chat',
  BOARD: '/board',
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];
