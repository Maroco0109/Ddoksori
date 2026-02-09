import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Outlet, useLocation, ScrollRestoration } from 'react-router-dom';
import { Menu } from 'lucide-react';
import { useUIStore } from '@/store';
import { useAuthStore, isAuthHydrated } from '@/features/auth/auth.store';
import { useChatStore } from '@/features/chat/chat.store';
import Sidebar from '@/widgets/Sidebar';
import LoginModal from '@/features/auth/LoginModal';

export default function RootLayout() {
  const location = useLocation();
  const isAuthModalOpen = useUIStore((state) => state.isAuthModalOpen);
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);

  const isLoggedIn = useAuthStore((state) => state.isAuthenticated);
  const token = useAuthStore((state) => state.token);
  const loadChatSessions = useChatStore((state) => state.loadChatSessions);

  const lastSyncTime = useRef<number>(0);
  const prevAuthRef = useRef(isLoggedIn);

  // Auth hydration 완료 대기 (F5 새로고침 시 race condition 방지)
  const [authReady, setAuthReady] = useState(isAuthHydrated());

  useEffect(() => {
    if (isAuthHydrated()) {
      setAuthReady(true);
      return;
    }
    let mounted = true;
    const timeout = setTimeout(() => {
      if (mounted) {
        console.warn('[RootLayout] Auth hydration timeout — proceeding with current state');
        setAuthReady(true);
      }
    }, 5000);
    const check = setInterval(() => {
      if (!mounted) {
        clearInterval(check);
        clearTimeout(timeout);
        return;
      }
      if (isAuthHydrated()) {
        setAuthReady(true);
        clearInterval(check);
        clearTimeout(timeout);
      }
    }, 50);
    return () => {
      mounted = false;
      clearInterval(check);
      clearTimeout(timeout);
    };
  }, []);

  // 로그아웃 감지 시 chatStore 상태 초기화 (순환 참조 방지)
  useEffect(() => {
    if (!authReady) return;
    if (prevAuthRef.current && !isLoggedIn) {
      useChatStore.getState().resetState();
      console.log('[RootLayout] Auth state changed to logged out — chat state reset');
    }
    prevAuthRef.current = isLoggedIn;
  }, [authReady, isLoggedIn]);

  useEffect(() => {
    if (!authReady) return;

    if (isLoggedIn && token) {
      // 로그인 상태: API로 세션 목록 조회 (5초 쿨다운)
      const now = Date.now();
      if (now - lastSyncTime.current > 5000) {
        loadChatSessions(true);
        lastSyncTime.current = Date.now();
      }
    } else {
      loadChatSessions(false);
    }

    if (!isLoggedIn) {
      const interval = setInterval(() => loadChatSessions(false), 60000);
      return () => clearInterval(interval);
    }
  }, [authReady, isLoggedIn, token, loadChatSessions]);

  // 페이지 focus 시 자동 동기화 (멀티 디바이스 지원)
  useEffect(() => {
    if (!authReady || !isLoggedIn || !token) return;

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const now = Date.now();
        const timeSinceLastSync = now - lastSyncTime.current;

        // 최소 30초 간격으로 동기화
        if (timeSinceLastSync > 30000) {
          loadChatSessions(true);
          lastSyncTime.current = now;
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
  }, [authReady, isLoggedIn, token, loadChatSessions]);

  // 브라우저 자동 스크롤 복원 비활성화
  useEffect(() => {
    if ('scrollRestoration' in history) {
      history.scrollRestoration = 'manual';
    }
  }, []);

  // 페이지 이동 시 스크롤 최상단으로 이동 (useLayoutEffect로 동기적 처리)
  useLayoutEffect(() => {
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

    requestAnimationFrame(() => {
      scrollToTop();
      requestAnimationFrame(scrollToTop);
    });

    const timer = setTimeout(scrollToTop, 100);
    return () => clearTimeout(timer);
  }, [location.pathname]);

  const isHomePage = location.pathname === '/';

  return (
    <div
      className="flex min-h-screen"
      style={{ backgroundColor: isHomePage ? '#fbeae9' : '#FAF0E6' }}
    >
      <ScrollRestoration />
      <Sidebar />

      <main className={`lg:ml-64 flex-1 w-full ${isHomePage ? '' : 'p-4 sm:p-6 md:p-8 lg:p-12'}`}>
        <div className={isHomePage ? '' : 'max-w-7xl mx-auto'}>
          {!isHomePage && (
            <div className="flex justify-between items-center mb-4 sm:mb-6">
              {/* Mobile Hamburger Menu Button */}
              <button
                onClick={toggleSidebar}
                className="lg:hidden p-2 hover:bg-gray-100 rounded-lg transition-colors"
                aria-label="메뉴 열기"
              >
                <Menu size={24} className="text-dark-navy" />
              </button>
            </div>
          )}

          {isHomePage && (
            <div className="absolute top-0 left-0 right-0 z-50 px-4 sm:px-6 md:px-8 lg:px-12 pt-4 sm:pt-6 md:pt-8 lg:pt-12">
              {/* Mobile Hamburger Menu Button */}
              <button
                onClick={toggleSidebar}
                className="lg:hidden p-2 hover:bg-white/80 backdrop-blur-sm rounded-lg transition-colors"
                aria-label="메뉴 열기"
              >
                <Menu size={24} className="text-dark-navy" />
              </button>
            </div>
          )}

          <Outlet />
        </div>
      </main>

      {isAuthModalOpen && <LoginModal />}
    </div>
  );
}
