import { useUIStore } from '@/store';
import { useAuthStore } from '@/features/auth/auth.store';
import { useChatStore } from '@/features/chat/chat.store';

// Google 로고 SVG
const GoogleIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M19.8 10.2273C19.8 9.51818 19.7364 8.83636 19.6182 8.18182H10.2V12.05H15.6091C15.3727 13.3 14.6545 14.3591 13.5864 15.0682V17.5773H16.8182C18.7091 15.8364 19.8 13.2727 19.8 10.2273Z" fill="#4285F4"/>
    <path d="M10.2 20C12.9 20 15.1727 19.1045 16.8182 17.5773L13.5864 15.0682C12.6909 15.6682 11.5455 16.0227 10.2 16.0227C7.59545 16.0227 5.38182 14.2636 4.58636 11.9H1.24545V14.4909C2.87727 17.7591 6.27273 20 10.2 20Z" fill="#34A853"/>
    <path d="M4.58636 11.9C4.38636 11.3 4.27273 10.6591 4.27273 10C4.27273 9.34091 4.38636 8.7 4.58636 8.1V5.50909H1.24545C0.554545 6.89091 0.181818 8.40909 0.181818 10C0.181818 11.5909 0.554545 13.1091 1.24545 14.4909L4.58636 11.9Z" fill="#FBBC05"/>
    <path d="M10.2 3.97727C11.6682 3.97727 12.9864 4.48182 14.0227 5.47273L16.8909 2.60455C15.1682 0.990909 12.9 0 10.2 0C6.27273 0 2.87727 2.24091 1.24545 5.50909L4.58636 8.1C5.38182 5.73636 7.59545 3.97727 10.2 3.97727Z" fill="#EA4335"/>
  </svg>
);

// Naver 로고 SVG
const NaverIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M13.6042 10.8333L6.04167 0H0V20H6.39583V9.16667L13.9583 20H20V0H13.6042V10.8333Z" fill="white"/>
  </svg>
);

export default function LoginModal() {
  const setIsAuthModalOpen = useUIStore((state) => state.setIsAuthModalOpen);
  const login = useAuthStore((state) => state.login);
  const loadChatSessions = useChatStore((state) => state.loadChatSessions);

  const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';

  const handleGoogleLogin = () => {
    window.location.href = `${BACKEND_URL}/auth/google`;
  };

  const handleNaverLogin = () => {
    window.location.href = `${BACKEND_URL}/auth/naver`;
  };

  // 개발 환경에서만 사용할 테스트 로그인 함수
  const handleTestLogin = () => {
    const dummyUser = {
      id: 'test-user-123',
      email: 'test@example.com',
      name: '테스트 사용자',
      avatar: 'https://via.placeholder.com/100',
      provider: 'google' as const,
    };
    const dummyToken = 'test-jwt-token-12345';

    login(dummyUser, dummyToken);
    loadChatSessions(true);
    setIsAuthModalOpen(false);
  };

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={() => setIsAuthModalOpen(false)}
    >
      <div
        className="bg-white p-6 sm:p-8 rounded-2xl w-full max-w-sm shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-dark-navy">1초 만에 시작하기</h2>
            <p className="text-sm text-gray-purple mt-1">
              간편하게 소셜 계정으로 시작하세요
            </p>
          </div>
          <button
            type="button"
            onClick={() => setIsAuthModalOpen(false)}
            className="text-gray-500 hover:text-dark-navy"
            aria-label="닫기"
          >
            ✕
          </button>
        </div>

        <div className="space-y-3">
          {/* Google 로그인 */}
          <button
            type="button"
            onClick={handleGoogleLogin}
            className="w-full rounded-lg border-2 border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all flex items-center justify-center gap-3 shadow-sm"
          >
            <GoogleIcon />
            <span>Google로 계속하기</span>
          </button>

          {/* 네이버 로그인 */}
          <button
            type="button"
            onClick={handleNaverLogin}
            className="w-full rounded-lg bg-[#03C75A] text-white px-4 py-3 text-sm font-semibold hover:bg-[#02B350] transition-all flex items-center justify-center gap-3 shadow-sm"
          >
            <NaverIcon />
            <span>네이버로 계속하기</span>
          </button>

          {/* 개발 환경에서만 보이는 테스트 로그인 버튼 */}
          {import.meta.env.DEV && (
            <>
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300"></div>
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white px-2 text-gray-500">개발 전용</span>
                </div>
              </div>
              <button
                type="button"
                onClick={handleTestLogin}
                className="w-full rounded-lg border-2 border-dashed border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-all flex items-center justify-center gap-3"
              >
                <span>🧪 테스트 로그인</span>
              </button>
            </>
          )}
        </div>

        <p className="text-[11px] text-gray-500 mt-5 leading-relaxed">
          로그인 시 서비스 이용약관과 개인정보 처리방침에 동의하게 됩니다.
        </p>
      </div>
    </div>
  );
}
