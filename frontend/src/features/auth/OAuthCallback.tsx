import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from './auth.store';
import { useChatStore } from '@/features/chat/chat.store';

export default function OAuthCallback() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const login = useAuthStore((state) => state.login);
  const loadChatSessions = useChatStore((state) => state.loadChatSessions);

  useEffect(() => {
    const handleCallback = async () => {
      try {
        // URL에서 토큰 추출
        const accessToken = searchParams.get('access_token');
        const tokenType = searchParams.get('token_type');

        if (!accessToken) {
          console.error('[OAuth] 토큰이 없습니다');
          navigate('/?error=no_token');
          return;
        }

        // 백엔드에서 사용자 정보 가져오기
        const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
        const response = await fetch(`${BACKEND_URL}/auth/me`, {
          headers: {
            'Authorization': `${tokenType || 'Bearer'} ${accessToken}`,
          },
        });

        if (!response.ok) {
          throw new Error('사용자 정보를 가져오는데 실패했습니다');
        }

        const userData = await response.json();

        // 사용자 정보를 auth store에 저장
        const user = {
          id: userData.user_id,
          email: userData.email,
          name: userData.name || userData.email,
          avatar: userData.profile_image || '',
          provider: userData.provider,
        };

        // 로그인 처리
        login(user, accessToken);

        // 채팅 세션 로드
        loadChatSessions(true);

        console.log('[OAuth] 로그인 성공:', user);

        // 홈페이지로 리다이렉트
        navigate('/', { replace: true });

      } catch (error) {
        console.error('[OAuth] 콜백 처리 실패:', error);
        navigate('/?error=auth_failed');
      }
    };

    handleCallback();
  }, [searchParams, login, loadChatSessions, navigate]);

  return (
    <div className="fixed inset-0 bg-white flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-deep-teal border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-lg text-gray-700">로그인 처리중...</p>
      </div>
    </div>
  );
}
