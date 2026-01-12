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

// Kakao 로고 SVG
const KakaoIcon = () => (
  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path fillRule="evenodd" clipRule="evenodd" d="M10 0C4.477 0 0 3.51 0 7.837C0 10.45 1.654 12.74 4.175 14.092L3.233 17.788C3.137 18.147 3.548 18.419 3.853 18.208L8.214 15.316C8.805 15.4 9.399 15.673 10 15.673C15.523 15.673 20 12.163 20 7.837C20 3.51 15.523 0 10 0Z" fill="#181600"/>
  </svg>
);

export default function LoginModal() {
  const setIsAuthModalOpen = useUIStore((state) => state.setIsAuthModalOpen);
  const login = useAuthStore((state) => state.login);
  const loadChatSessions = useChatStore((state) => state.loadChatSessions);

  // OAuth 로그인 성공 시 호출할 함수 예시
  // const handleLoginSuccess = (user: User, token: string) => {
  //   login(user, token); // 세션 이전이 자동으로 처리됩니다
  //   loadChatSessions(true); // 로그인 사용자 세션 로드
  //   setIsAuthModalOpen(false);
  // };

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
            <h2 className="text-2xl font-bold text-dark-navy">가입/로그인</h2>
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
            className="w-full rounded-lg border-2 border-gray-300 bg-white px-4 py-3 text-sm font-semibold text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-all flex items-center justify-center gap-3 shadow-sm"
          >
            <GoogleIcon />
            <span>Google로 계속하기</span>
          </button>

          {/* 네이버 로그인 */}
          <button
            type="button"
            className="w-full rounded-lg bg-[#03C75A] text-white px-4 py-3 text-sm font-semibold hover:bg-[#02B350] transition-all flex items-center justify-center gap-3 shadow-sm"
          >
            <NaverIcon />
            <span>네이버로 계속하기</span>
          </button>

          {/* 카카오 로그인 */}
          <button
            type="button"
            className="w-full rounded-lg bg-[#FEE500] text-[#000000] px-4 py-3 text-sm font-semibold hover:bg-[#FDD835] transition-all flex items-center justify-center gap-3 shadow-sm"
          >
            <KakaoIcon />
            <span>카카오로 계속하기</span>
          </button>
        </div>

        <p className="text-[11px] text-gray-500 mt-5 leading-relaxed">
          로그인 시 서비스 이용약관과 개인정보 처리방침에 동의하게 됩니다.
        </p>
      </div>
    </div>
  );
}
