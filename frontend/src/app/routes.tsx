import { createBrowserRouter, Navigate } from 'react-router-dom';
import { ROUTES } from '@/shared/config/routes';
import RootLayout from './RootLayout';
import HomePage from '@/features/home/HomePage';
import ProcedurePage from '@/features/procedure/ProcedurePage';
import ChatPage from '@/features/chat/ChatPage';
import BoardPage from '@/features/board/BoardPage';
import MyPage from '@/features/mypage/MyPage';
import AuthCallback from '@/features/auth/AuthCallback';
import AdminLoginPage from '@/features/admin/AdminLoginPage';
import AdminLayout from '@/features/admin/AdminLayout';
import AdminDashboard from '@/features/admin/pages/AdminDashboard';
import AdminPostsPage from '@/features/admin/pages/AdminPostsPage';
import AdminUsersPage from '@/features/admin/pages/AdminUsersPage';
import AdminReportsPage from '@/features/admin/pages/AdminReportsPage';
import AdminGuard from '@/features/admin/AdminGuard';

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { index: true, element: <HomePage /> },
      { path: ROUTES.PROCEDURE, element: <ProcedurePage /> },
      { path: ROUTES.CHAT, element: <ChatPage /> },
      { path: ROUTES.BOARD, element: <BoardPage /> },
      { path: ROUTES.MYPAGE, element: <MyPage /> },
      { path: '*', element: <Navigate to={ROUTES.HOME} replace /> },
    ],
  },
  {
    path: ROUTES.AUTH_CALLBACK,
    element: <AuthCallback />,
  },
  {
    path: ROUTES.ADMIN_LOGIN,
    element: <AdminLoginPage />,
  },
  {
    path: '/admin',
    element: (
      <AdminGuard>
        <AdminLayout />
      </AdminGuard>
    ),
    children: [
      { path: 'dashboard', element: <AdminDashboard /> },
      { path: 'posts', element: <AdminPostsPage /> },
      { path: 'users', element: <AdminUsersPage /> },
      { path: 'reports', element: <AdminReportsPage /> },
    ],
  },
]);
