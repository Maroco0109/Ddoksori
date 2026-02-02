export const ROUTES = {
  HOME: '/',
  PROCEDURE: '/procedure',
  CHAT: '/chat',
  BOARD: '/board',
  MYPAGE: '/mypage',
  ADMIN_LOGIN: '/admin/login',
  ADMIN_DASHBOARD: '/admin/dashboard',
  ADMIN_POSTS: '/admin/posts',
  ADMIN_USERS: '/admin/users',
  ADMIN_REPORTS: '/admin/reports',
} as const;

export type RoutePath = (typeof ROUTES)[keyof typeof ROUTES];
