import { useEffect, useLayoutEffect } from 'react';
import { Outlet, useLocation, ScrollRestoration } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { useUIStore } from '@/store';
import { useAuthStore } from '@/features/auth/auth.store';
import { useChatStore } from '@/features/chat/chat.store';
import Sidebar from '@/widgets/Sidebar';
import LoginModal from '@/features/auth/LoginModal';

export default function RootLayout() {
  const location = useLocation();
  const isAuthModalOpen = useUIStore((state) => state.isAuthModalOpen);
  const setIsAuthModalOpen = useUIStore((state) => state.setIsAuthModalOpen);
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);

  const isLoggedIn = useAuthStore((state) => state.isAuthenticated);
  const loadChatSessions = useChatStore((state) => state.loadChatSessions);

  useEffect(() => {
    loadChatSessions(isLoggedIn);

    if (!isLoggedIn) {
      const interval = setInterval(() => loadChatSessions(false), 60000);
      return () => clearInterval(interval);
    }
  }, [location.pathname, isLoggedIn, loadChatSessions]);

  // 브라우저 자동 스크롤 복원 비활성화
  useEffect(() => {
    if ('scrollRestoration' in history) {
      history.scrollRestoration = 'manual';
    }
  }, []);

  // 페이지 이동 시 스크롤 최상단으로 이동 (useLayoutEffect로 동기적 처리)
  useLayoutEffect(() => {
    // DOM 업데이트 직후 즉시 실행
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [location.pathname]);

  // 추가적인 스크롤 처리 (렌더링 완료 후)
  useEffect(() => {
    const scrollToTop = () => {
      window.scrollTo(0, 0);
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    };

    // requestAnimationFrame으로 다음 프레임에서 실행
    requestAnimationFrame(() => {
      scrollToTop();
      requestAnimationFrame(scrollToTop);
    });

    // 추가 지연 실행
    const timer = setTimeout(scrollToTop, 100);
    return () => clearTimeout(timer);
  }, [location.pathname]);

  return (
    <div className="flex min-h-screen">
      <ScrollRestoration />
      <Sidebar />

      <main className="lg:ml-64 flex-1 p-4 sm:p-6 md:p-8 lg:p-12 w-full">
        <div className="max-w-7xl mx-auto">
          <div className="flex justify-between items-center mb-4 sm:mb-6">
            {/* Mobile Hamburger Menu Button */}
            <button
              onClick={toggleSidebar}
              className="lg:hidden p-2 hover:bg-gray-100 rounded-lg transition-colors"
              aria-label="메뉴 열기"
            >
              <Menu size={24} className="text-dark-navy" />
            </button>

            <div className="flex-1 flex justify-end">
              <button
                onClick={() => setIsAuthModalOpen(true)}
                className="bg-dark-navy text-white px-6 sm:px-7 md:px-8 py-2 sm:py-2.5 md:py-3 rounded-full text-xs sm:text-sm md:text-base font-semibold hover:bg-mint-green transition-all"
              >
                가입/로그인
              </button>
            </div>
          </div>

          <Outlet />
        </div>
      </main>

      {isAuthModalOpen && <LoginModal />}
    </div>
  );
}
