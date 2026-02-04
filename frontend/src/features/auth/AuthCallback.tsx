/**
 * OAuth 콜백 처리 컴포넌트
 *
 * OAuth 로그인 완료 후 백엔드에서 리다이렉트되는 페이지입니다.
 * URL fragment(#)에서 토큰을 추출하여 인증 상태를 설정합니다.
 *
 * [보안 고려사항 - SEC-03]
 * - URL fragment(#)를 사용하여 토큰이 서버 로그나 브라우저 히스토리에 노출되지 않도록 함
 * - 토큰 추출 후 즉시 URL에서 제거
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from './auth.store';
import { useChatStore } from '@/features/chat/chat.store';
import { ROUTES } from '@/shared/config/routes';

interface TokenParams {
  access_token?: string;
  token_type?: string;
  expires_in?: string;
  error?: string;
}

/**
 * URL fragment에서 파라미터를 파싱합니다.
 * #access_token=xxx&token_type=bearer&expires_in=3600 형식
 */
function parseHashParams(hash: string): TokenParams {
  if (!hash || hash.length <= 1) return {};

  const hashString = hash.substring(1); // '#' 제거
  const params = new URLSearchParams(hashString);

  return {
    access_token: params.get('access_token') || undefined,
    token_type: params.get('token_type') || undefined,
    expires_in: params.get('expires_in') || undefined,
    error: params.get('error') || undefined,
  };
}

/**
 * 토큰으로 사용자 정보를 가져옵니다.
 */
async function fetchUserInfo(token: string) {
  const response = await fetch('/api/auth/me', {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('사용자 정보를 가져올 수 없습니다.');
  }

  return response.json();
}

export default function AuthCallback() {
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const loadChatSessions = useChatStore((state) => state.loadChatSessions);
  const [status, setStatus] = useState<'loading' | 'error'>('loading');
  const [errorMessage, setErrorMessage] = useState<string>('');

  useEffect(() => {
    const handleCallback = async () => {
      // URL fragment에서 토큰 파라미터 추출
      const params = parseHashParams(window.location.hash);

      // 보안: URL에서 토큰 정보 즉시 제거
      if (window.location.hash) {
        window.history.replaceState(null, '', window.location.pathname);
      }

      // 에러 처리
      if (params.error) {
        setStatus('error');
        setErrorMessage(
          params.error === 'auth_failed'
            ? '인증에 실패했습니다. 다시 시도해주세요.'
            : `인증 오류: ${params.error}`
        );
        return;
      }

      // 토큰 검증
      if (!params.access_token) {
        setStatus('error');
        setErrorMessage('인증 토큰을 받지 못했습니다.');
        return;
      }

      try {
        // 사용자 정보 조회
        const userData = await fetchUserInfo(params.access_token);

        // 사용자 객체 생성
        const user = {
          id: userData.user_id,
          email: userData.email,
          name: userData.name || userData.email.split('@')[0],
          avatar: userData.profile_image || undefined,
          provider: userData.provider as 'google' | 'naver',
        };

        // 로그인 상태 설정
        login(user, params.access_token);

        // 채팅 세션 로드
        loadChatSessions(true);

        // 홈으로 리다이렉트
        navigate(ROUTES.HOME, { replace: true });
      } catch (error) {
        console.error('[AuthCallback] 로그인 처리 실패:', error);
        setStatus('error');
        setErrorMessage(
          error instanceof Error ? error.message : '로그인 처리 중 오류가 발생했습니다.'
        );
      }
    };

    handleCallback();
  }, [login, loadChatSessions, navigate]);

  // 로딩 중
  if (status === 'loading') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4" />
          <p className="text-gray-600 font-medium">로그인 처리 중...</p>
        </div>
      </div>
    );
  }

  // 에러 발생
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-red-50 to-pink-100">
      <div className="text-center max-w-md mx-auto p-6">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <div className="text-red-500 text-5xl mb-4">!</div>
          <h1 className="text-xl font-bold text-gray-800 mb-2">로그인 실패</h1>
          <p className="text-gray-600 mb-6">{errorMessage}</p>
          <button
            type="button"
            onClick={() => navigate(ROUTES.HOME, { replace: true })}
            className="bg-indigo-600 text-white px-6 py-2 rounded-lg hover:bg-indigo-700 transition-colors"
          >
            홈으로 돌아가기
          </button>
        </div>
      </div>
    </div>
  );
}
