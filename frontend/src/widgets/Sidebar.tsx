import { useState, useEffect } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  Home,
  ClipboardList,
  MessageCircle,
  LayoutList,
  PlusCircle,
  History,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { ROUTES } from '@/shared/config/routes';
import { formatDateTime } from '@/shared/lib/date';
import { formatTimeRemaining } from '@/shared/lib/session';
import { useChatStore } from '@/features/chat/chat.store';
import { useUIStore } from '@/store';
import { useAuthStore } from '@/features/auth/auth.store';
import logo from '@/shared/assets/icons/logo-3.png';

const navItems = [
  { to: ROUTES.HOME, label: 'HOME', icon: Home },
  { to: ROUTES.PROCEDURE, label: '조정신청 절차', icon: ClipboardList },
  { to: ROUTES.CHAT, label: 'AI 상담', icon: MessageCircle },
  { to: ROUTES.BOARD, label: '자유게시판', icon: LayoutList },
];

export default function Sidebar() {
  const [isChatMenuOpen, setIsChatMenuOpen] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState<string>('');
  const navigate = useNavigate();
  const location = useLocation();
  const chatSessions = useChatStore((state) => state.chatSessions);
  const currentSessionId = useChatStore((state) => state.currentSessionId);
  const setCurrentSessionId = useChatStore((state) => state.setCurrentSessionId);
  const setActiveChatType = useChatStore((state) => state.setActiveChatType);
  const startNewChat = useChatStore((state) => state.startNewChat);
  const refreshSessionTime = useChatStore((state) => state.refreshSessionTime);
  const loadChatSessions = useChatStore((state) => state.loadChatSessions);
  const deleteChatSession = useChatStore((state) => state.deleteChatSession);

  const isChatHistoryOpen = useUIStore((state) => state.isChatHistoryOpen);
  const setIsChatHistoryOpen = useUIStore((state) => state.setIsChatHistoryOpen);
  const isSidebarOpen = useUIStore((state) => state.isSidebarOpen);
  const setIsSidebarOpen = useUIStore((state) => state.setIsSidebarOpen);

  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  // 비로그인 사용자의 세션 만료 시간 업데이트
  useEffect(() => {
    if (!isAuthenticated && chatSessions.length > 0 && chatSessions[0].expiresAt) {
      const updateTimer = () => {
        setTimeRemaining(formatTimeRemaining(chatSessions[0].expiresAt!));
      };

      updateTimer();
      const interval = setInterval(updateTimer, 60000); // 1분마다 업데이트

      return () => clearInterval(interval);
    }
  }, [isAuthenticated, chatSessions]);

  const handleRefreshSession = (sessionId: string) => {
    refreshSessionTime(sessionId);
    loadChatSessions(isAuthenticated);
  };

  const handleDeleteSession = (sessionId: string, sessionTitle: string, event: React.MouseEvent) => {
    event.stopPropagation(); // 버튼 클릭이 상위 버튼으로 전파되지 않도록

    const confirmDelete = window.confirm(
      `"${sessionTitle}" 상담 내역을 삭제하시겠습니까?\n\n이 작업은 되돌릴 수 없습니다.`
    );

    if (confirmDelete) {
      deleteChatSession(sessionId, isAuthenticated);
      // 삭제된 세션이 현재 활성 세션이었다면 초기화
      if (currentSessionId === sessionId) {
        startNewChat();
        navigate(ROUTES.CHAT);
      }
    }
  };

  const handleNavClick = (to: string) => {
    // 모바일에서 메뉴 클릭 시 사이드바 닫기
    if (window.innerWidth < 1024) {
      setIsSidebarOpen(false);
    }
  };

  const SidebarContent = () => (
    <>
      <div className="p-6 border-b border-white/10">
        <div className="flex items-center gap-3">
          <img src={logo} alt="똑소리 로고" className="w-9 h-9 rounded-md" />
          <div>
            <h1 className="text-2xl font-bold leading-tight text-[#4C9E9F]">똑소리</h1>
            <p className="text-[11px] text-white/70">
              <span className="text-[#4C9E9F]">똑</span>똑한{' '}
              <span className="text-[#4C9E9F]">소</span>비자의 권
              <span className="text-[#4C9E9F]">리</span>
            </p>
          </div>
        </div>
      </div>
      <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
        {navItems.map((item) => {
          const isChatItem = item.to === ROUTES.CHAT;

          return (
            <div key={item.to} className="space-y-2">
              {isChatItem ? (
                // AI 상담 메뉴는 버튼으로 렌더링 (하위 메뉴만 토글)
                <button
                  type="button"
                  onClick={() => {
                    setIsChatMenuOpen((prev) => !prev);
                    setIsChatHistoryOpen(false);
                  }}
                  className={`flex w-full items-center gap-3 rounded-lg px-4 py-3 text-sm font-semibold transition-colors text-left ${
                    location.pathname === ROUTES.CHAT
                      ? 'bg-ivory text-dark-navy'
                      : 'text-white/80 hover:text-white hover:bg-white/10'
                  }`}
                >
                  <item.icon size={18} />
                  <span className="flex-1">{item.label}</span>
                  {isChatMenuOpen ? (
                    <ChevronDown size={16} className="ml-auto" />
                  ) : (
                    <ChevronRight size={16} className="ml-auto" />
                  )}
                </button>
              ) : (
                // 다른 메뉴는 NavLink로 렌더링
                <NavLink
                  to={item.to}
                  onClick={() => {
                    setIsChatMenuOpen(false);
                    setIsChatHistoryOpen(false);
                    handleNavClick(item.to);
                  }}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-semibold transition-colors ${
                      isActive
                        ? 'bg-ivory text-dark-navy'
                        : 'text-white/80 hover:text-white hover:bg-white/10'
                    }`
                  }
                  end={item.to === ROUTES.HOME}
                >
                  <item.icon size={18} />
                  <span className="flex-1">{item.label}</span>
                </NavLink>
              )}

              {isChatItem && (
                <div className="pl-4 pr-2">
                  {isChatMenuOpen && (
                    <div className="mt-1 space-y-1">
                      <button
                        type="button"
                        onClick={() => {
                          startNewChat();
                          setIsChatHistoryOpen(true);
                          navigate(ROUTES.CHAT);
                          handleNavClick(ROUTES.CHAT);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs font-semibold text-white/80 hover:bg-white/10"
                      >
                        <PlusCircle size={14} />
                        새 상담 시작
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setIsChatHistoryOpen(!isChatHistoryOpen);
                        }}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-xs font-semibold text-white/80 hover:bg-white/10"
                      >
                        <History size={14} />
                        <span className="flex-1 text-left">상담 내역</span>
                        {isChatHistoryOpen ? (
                          <ChevronDown size={14} className="ml-auto" />
                        ) : (
                          <ChevronRight size={14} className="ml-auto" />
                        )}
                      </button>
                      {isChatHistoryOpen && (
                        <div className="mt-2 space-y-2">
                          {chatSessions.length === 0 && (
                            <p className="px-2 text-[11px] text-white/50">
                              저장된 상담 내역이 없습니다.
                            </p>
                          )}
                          {!isAuthenticated && chatSessions.length > 0 && chatSessions[0].expiresAt && (
                            <div className="px-2 py-2 mb-2 bg-white/5 rounded-md">
                              <div className="flex items-center justify-between text-[10px]">
                                <span className="text-white/60">세션 유지 시간</span>
                                <div className="flex items-center gap-1">
                                  <span className="text-mint-green font-semibold">{timeRemaining}</span>
                                  <button
                                    type="button"
                                    onClick={() => handleRefreshSession(chatSessions[0].id)}
                                    className="p-1 hover:bg-white/10 rounded transition-colors"
                                    title="세션 시간 갱신"
                                  >
                                    <RefreshCw size={12} className="text-white/60 hover:text-mint-green" />
                                  </button>
                                </div>
                              </div>
                            </div>
                          )}
                          {chatSessions.map((session) => (
                            <div
                              key={session.id}
                              className={`group relative w-full rounded-md px-2 py-2 text-[11px] transition-colors ${
                                currentSessionId === session.id
                                  ? 'bg-white/15 text-white'
                                  : 'text-white/70 hover:bg-white/10'
                              }`}
                            >
                              <button
                                type="button"
                                onClick={() => {
                                  setCurrentSessionId(session.id);
                                  setActiveChatType(session.type);
                                  navigate(ROUTES.CHAT);
                                  handleNavClick(ROUTES.CHAT);
                                }}
                                className="w-full text-left"
                              >
                                <div className="flex items-center justify-between gap-2 pr-6">
                                  <span className="font-semibold">
                                    {session.type === 'dispute' ? '분쟁 상담' : '일반 상담'}
                                  </span>
                                  <span className="text-[10px] text-white/50">
                                    {formatDateTime(session.createdAt)}
                                  </span>
                                </div>
                                <div className="truncate text-white/60 pr-6">{session.title}</div>
                              </button>
                              <button
                                type="button"
                                onClick={(e) => handleDeleteSession(session.id, session.title, e)}
                                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-white/20 transition-opacity"
                                title="상담 내역 삭제"
                              >
                                <Trash2 size={12} className="text-red-400 hover:text-red-300" />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </nav>
      <div className="mt-auto px-6 py-4 text-[11px] text-white/50">
        © ㈜오작교
      </div>
    </>
  );

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex lg:flex-col lg:fixed inset-y-0 w-64 bg-dark-navy text-white z-30">
        <SidebarContent />
      </aside>

      {/* Mobile Sidebar Overlay */}
      {isSidebarOpen && (
        <>
          {/* Background Overlay */}
          <div
            onClick={() => setIsSidebarOpen(false)}
            className="fixed inset-0 bg-black/50 z-40 lg:hidden transition-opacity"
            aria-label="사이드바 닫기"
          />

          {/* Mobile Sidebar */}
          <aside className="fixed inset-y-0 left-0 w-64 bg-dark-navy text-white z-50 lg:hidden flex flex-col transform transition-transform duration-300 ease-in-out">
            <SidebarContent />
          </aside>
        </>
      )}
    </>
  );
}
