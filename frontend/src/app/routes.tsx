import { createBrowserRouter, Navigate } from 'react-router-dom';
import { ROUTES } from '@/shared/config/routes';
import RootLayout from './RootLayout';
import HomePage from '@/features/home/HomePage';
import ProcedurePage from '@/features/procedure/ProcedurePage';
import ChatPage from '@/features/chat/ChatPage';
import BoardPage from '@/features/board/BoardPage';
import MyPage from '@/features/mypage/MyPage';

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
]);
