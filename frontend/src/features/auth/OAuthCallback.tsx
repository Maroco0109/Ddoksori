import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from './auth.store';
import { useChatStore } from '@/features/chat/chat.store';

export default function OAuthCallback() {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const loadChatSessions = useChatStore((state) => state.loadChatSessions);
  const syncWithBackend = useChatStore((state) => state.syncWithBackend);
  const hasProcessed = useRef(false);

  useEffect(() => {
    const handleCallback = async () => {
      // Prevent double execution (React StrictMode in development)
      if (hasProcessed.current) {
        console.log('[OAuth] Already processed, skipping duplicate call');
        return;
      }
      hasProcessed.current = true;

      try {
        console.log('[OAuth] Component mounted, starting OAuth callback processing');
        console.log('[OAuth] Full URL:', window.location.href);
        console.log('[OAuth] Hash Fragment:', window.location.hash);

        // URL Hash Fragment에서 토큰 추출 (#access_token=...)
        const hash = window.location.hash.substring(1); // '#' 제거
        const params = new URLSearchParams(hash);
        const accessToken = params.get('access_token');
        const tokenType = params.get('token_type');

        console.log('[OAuth] Parsed access_token:', accessToken ? `${accessToken.substring(0, 20)}...` : 'NULL');
        console.log('[OAuth] Parsed token_type:', tokenType || 'NULL');

        // 보안: URL에서 토큰 정보 즉시 제거
        if (window.location.hash) {
          console.log('[OAuth] Clearing hash from URL for security');
          window.history.replaceState(null, '', window.location.pathname);
        }

        if (!accessToken) {
          console.error('[OAuth] 토큰이 없습니다 - redirecting to home with error');
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

        // 백엔드에서 채팅 세션 동기화 (멀티 디바이스 동기화)
        try {
          console.log('[OAuth] 백엔드 세션 동기화 시작...');
          await syncWithBackend(accessToken);
          console.log('[OAuth] 백엔드 세션 동기화 완료');
        } catch (error) {
          console.error('[OAuth] 백엔드 세션 동기화 실패:', error);
          // 동기화 실패해도 로컬 세션 로드
          loadChatSessions(true);
        }

        console.log('[OAuth] 로그인 성공:', user);

        // 홈페이지로 리다이렉트
        navigate('/', { replace: true });

      } catch (error) {
        console.error('[OAuth] 콜백 처리 실패:', error);
        navigate('/?error=auth_failed');
      }
    };

    handleCallback();
  }, [login, loadChatSessions, syncWithBackend, navigate]);

  return (
    <div className="fixed inset-0 bg-white flex items-center justify-center">
      <div className="text-center">
        <div className="w-16 h-16 border-4 border-deep-teal border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
        <p className="text-lg text-gray-700">로그인 처리중...</p>
      </div>
    </div>
  );
}
