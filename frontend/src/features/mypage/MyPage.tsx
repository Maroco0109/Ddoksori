import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/features/auth/auth.store';
import { useChatStore } from '@/features/chat/chat.store';
import { ROUTES } from '@/shared/config/routes';
import { User, LogOut, MessageCircle, Calendar, FileText, Eye, ThumbsUp, ChevronLeft, ChevronRight, MessageSquare } from 'lucide-react';
import { formatDateTime } from '@/shared/lib/date';
import { DISPLAY_TO_CATEGORY_MAP, CATEGORY_LABELS } from '@/shared/config/categories';

export default function MyPage() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const logout = useAuthStore((state) => state.logout);
  const chatSessions = useChatStore((state) => state.chatSessions);
  const setCurrentSessionId = useChatStore((state) => state.setCurrentSessionId);
  const setActiveChatType = useChatStore((state) => state.setActiveChatType);

  // 페이지네이션 상태
  const [chatPage, setChatPage] = useState(1);
  const [myPostsPage, setMyPostsPage] = useState(1);
  const [commentedPostsPage, setCommentedPostsPage] = useState(1);
  const itemsPerPage = 10;

  // 로그인하지 않은 경우 홈으로 리다이렉트
  if (!isAuthenticated || !user) {
    navigate(ROUTES.HOME);
    return null;
  }

  const handleLogout = () => {
    logout();
    navigate(ROUTES.HOME);
  };

  const handleDeleteAccount = () => {
    const confirmDelete = window.confirm(
      '정말로 회원탈퇴 하시겠습니까?\n\n탈퇴 시 모든 상담 내역과 데이터가 삭제되며, 이 작업은 되돌릴 수 없습니다.'
    );

    if (confirmDelete) {
      const doubleConfirm = window.confirm(
        '마지막 확인입니다.\n\n정말로 탈퇴하시겠습니까?'
      );

      if (doubleConfirm) {
        // TODO: 백엔드 API 연동 시 회원탈퇴 API 호출
        // const token = useAuthStore.getState().token;
        // const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
        //
        // try {
        //   const response = await fetch(`${API_BASE_URL}/auth/delete-account`, {
        //     method: 'DELETE',
        //     headers: {
        //       'Authorization': `Bearer ${token}`,
        //     },
        //   });
        //
        //   if (!response.ok) {
        //     throw new Error('회원탈퇴 처리 중 오류가 발생했습니다.');
        //   }
        //
        //   const data = await response.json();
        //   logout();
        //   navigate(ROUTES.HOME);
        //   alert(data.message);
        // } catch (error) {
        //   console.error('Delete account error:', error);
        //   alert('회원탈퇴 처리 중 오류가 발생했습니다.');
        //   return;
        // }

        // 임시: 백엔드 연동 전까지는 프론트엔드에서만 로그아웃 처리
        logout();
        navigate(ROUTES.HOME);
        alert('회원탈퇴가 완료되었습니다.');
      }
    }
  };

  const handleChatClick = (sessionId: string, chatType: 'general' | 'dispute') => {
    setCurrentSessionId(sessionId);
    setActiveChatType(chatType);
    navigate(ROUTES.CHAT);
  };

  const getProviderName = (provider: string) => {
    switch (provider) {
      case 'google':
        return 'Google';
      case 'naver':
        return '네이버';
      case 'kakao':
        return '카카오';
      default:
        return provider;
    }
  };

  const getProviderColor = (provider: string) => {
    switch (provider) {
      case 'google':
        return 'bg-white text-gray-700 border-2 border-gray-300';
      case 'naver':
        return 'bg-[#03C75A]';
      case 'kakao':
        return 'bg-[#FEE500] text-black';
      default:
        return 'bg-gray-500';
    }
  };

  // 게시글 카테고리를 DISPLAY_MAP 형식에서 LABELS 형식으로 변환
  const getCategoryLabel = (displayCategory: string) => {
    const categoryId = DISPLAY_TO_CATEGORY_MAP[displayCategory];
    return categoryId ? CATEGORY_LABELS[categoryId] : displayCategory;
  };

  // 테스트용 자유게시판 작성 글 (TODO: 실제 구현 시 로컬스토리지나 API에서 가져오기)
  const myBoardPosts = [
    {
      id: 4,
      category: '무엇이든/물어보세요',
      title: '환불 절차가 궁금합니다',
      date: '2025.12.17',
      views: 567,
      likes: 89,
      comments: 34,
    },
    {
      id: 3,
      category: '소비자/꿀팁/노하우',
      title: '소비자분쟁 조정 신청할 때 꼭 알아야 할 3가지',
      date: '2025.12.18',
      views: 456,
      likes: 78,
      comments: 23,
    },
  ];

  // 테스트용 댓글을 단 게시글 (TODO: 실제 구현 시 로컬스토리지나 API에서 가져오기)
  const commentedPosts = [
    {
      id: 1,
      category: '분쟁해결사례/공유',
      title: '당근마켓 사기 피해 복구 성공했습니다',
      date: '2025.12.20',
      views: 234,
      likes: 45,
      comments: 12,
      myCommentDate: '2025.12.21',
    },
    {
      id: 6,
      category: '소비자/꿀팁/노하우',
      title: '전자제품 AS 받을 때 꼭 챙겨야 할 것들',
      date: '2025.12.15',
      views: 523,
      likes: 92,
      comments: 19,
      myCommentDate: '2025.12.16',
    },
  ];

  // 페이지네이션 계산
  const getPaginatedItems = <T,>(items: T[], page: number) => {
    const startIndex = (page - 1) * itemsPerPage;
    const endIndex = startIndex + itemsPerPage;
    return items.slice(startIndex, endIndex);
  };

  const getTotalPages = (totalItems: number) => {
    return Math.ceil(totalItems / itemsPerPage);
  };

  // 각 섹션별 페이지네이션 데이터
  const paginatedChatSessions = getPaginatedItems(chatSessions, chatPage);
  const paginatedMyPosts = getPaginatedItems(myBoardPosts, myPostsPage);
  const paginatedCommentedPosts = getPaginatedItems(commentedPosts, commentedPostsPage);

  const chatTotalPages = getTotalPages(chatSessions.length);
  const myPostsTotalPages = getTotalPages(myBoardPosts.length);
  const commentedPostsTotalPages = getTotalPages(commentedPosts.length);

  // 페이지네이션 컴포넌트
  const Pagination = ({ currentPage, totalPages, onPageChange }: { currentPage: number; totalPages: number; onPageChange: (page: number) => void }) => {
    if (totalPages <= 1) return null;

    return (
      <div className="flex items-center justify-center gap-2 mt-4">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 1}
          className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft size={20} className="text-dark-navy" />
        </button>

        <div className="flex gap-1">
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
            <button
              key={page}
              onClick={() => onPageChange(page)}
              className={`px-3 py-1 rounded-lg text-sm font-semibold transition-all ${
                currentPage === page
                  ? 'bg-deep-teal text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {page}
            </button>
          ))}
        </div>

        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage === totalPages}
          className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronRight size={20} className="text-dark-navy" />
        </button>
      </div>
    );
  };

  return (
    <div className="mypage-container">
      {/* 페이지 헤더 */}
      <div className="mb-8">
        <h1 className="text-2xl sm:text-3xl md:text-4xl font-extrabold text-dark-navy">마이페이지</h1>
        <p className="text-sm sm:text-base text-gray-purple mt-2">
          내 정보와 상담 내역을 확인하세요
        </p>
      </div>

      {/* 프로필 섹션 */}
      <div className="bg-white rounded-2xl shadow-lg p-6 sm:p-8 mb-6">
        <div className="flex flex-col sm:flex-row items-center sm:items-start gap-6">
          {/* 사용자 정보 */}
          <div className="flex-1 text-center sm:text-left">
            <h2 className="text-2xl font-bold text-dark-navy mb-2">{user.name}</h2>
            <p className="text-gray-purple mb-3">{user.email}</p>
            <div className="inline-flex items-center gap-2 mb-4">
              <span
                className={`px-3 py-1 rounded-full text-sm font-semibold ${getProviderColor(
                  user.provider
                )}`}
              >
                {getProviderName(user.provider)} 계정
              </span>
            </div>
          </div>

          {/* 로그아웃 & 회원탈퇴 버튼 */}
          <div className="flex flex-col gap-2">
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-50 hover:bg-gray-100 text-dark-navy font-semibold transition-all border border-gray-300"
            >
              <LogOut size={18} />
              로그아웃
            </button>
            <button
              onClick={handleDeleteAccount}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-50 hover:bg-red-100 text-red-600 font-semibold transition-all border border-red-200"
            >
              <User size={18} />
              회원탈퇴
            </button>
          </div>
        </div>
      </div>

      {/* 내 상담 내역 */}
      <div className="bg-white rounded-2xl shadow-lg p-6 sm:p-8">
        <div className="flex items-center gap-3 mb-6">
          <MessageCircle size={24} className="text-deep-teal" />
          <h3 className="text-xl font-bold text-dark-navy">내 상담 내역</h3>
          <span className="text-sm text-gray-purple">({chatSessions.length}개)</span>
        </div>

        {chatSessions.length === 0 ? (
          <div className="text-center py-12">
            <MessageCircle size={48} className="text-gray-300 mx-auto mb-4" />
            <p className="text-gray-purple mb-4">아직 상담 내역이 없습니다</p>
            <button
              onClick={() => navigate(ROUTES.CHAT)}
              className="inline-flex items-center gap-2 bg-deep-teal text-white px-6 py-3 rounded-full font-semibold hover:bg-mint-green transition-all"
            >
              <MessageCircle size={18} />
              첫 상담 시작하기
            </button>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {paginatedChatSessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => handleChatClick(session.id, session.type)}
                  className="w-full bg-gray-50 hover:bg-gray-100 rounded-xl p-4 transition-all text-left border-2 border-transparent hover:border-deep-teal"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span
                          className={`inline-block px-2.5 py-1 rounded-full text-xs font-semibold ${
                            session.type === 'dispute'
                              ? 'bg-deep-teal/20 text-dark-navy'
                              : 'bg-mint-green/20 text-dark-navy'
                          }`}
                        >
                          {session.type === 'dispute' ? '분쟁 상담' : '일반 상담'}
                        </span>
                        <span className="text-xs text-gray-500 flex items-center gap-1">
                          <Calendar size={12} />
                          {formatDateTime(session.createdAt)}
                        </span>
                      </div>
                      <h4 className="font-semibold text-dark-navy mb-1 truncate">{session.title}</h4>
                      <p className="text-sm text-gray-purple line-clamp-2">
                        {session.messages?.[0]?.content || '대화 내용이 없습니다'}
                      </p>
                    </div>
                    <div className="flex-shrink-0">
                      <div className="w-10 h-10 bg-deep-teal rounded-full flex items-center justify-center">
                        <MessageCircle size={20} className="text-white" />
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
            <Pagination currentPage={chatPage} totalPages={chatTotalPages} onPageChange={setChatPage} />
          </>
        )}
      </div>

      {/* 내 게시글 */}
      <div className="bg-white rounded-2xl shadow-lg p-6 sm:p-8 mt-6">
        <div className="flex items-center gap-3 mb-6">
          <FileText size={24} className="text-deep-teal" />
          <h3 className="text-xl font-bold text-dark-navy">내 게시글</h3>
          <span className="text-sm text-gray-purple">({myBoardPosts.length}개)</span>
        </div>

        {myBoardPosts.length === 0 ? (
          <div className="text-center py-12">
            <FileText size={48} className="text-gray-300 mx-auto mb-4" />
            <p className="text-gray-purple mb-4">아직 작성한 게시글이 없습니다</p>
            <button
              onClick={() => navigate(ROUTES.BOARD)}
              className="inline-flex items-center gap-2 bg-deep-teal text-white px-6 py-3 rounded-full font-semibold hover:bg-mint-green transition-all"
            >
              <FileText size={18} />
              게시글 작성하기
            </button>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {paginatedMyPosts.map((post) => (
                <button
                  key={post.id}
                  onClick={() => navigate(ROUTES.BOARD, { state: { postId: post.id, viewType: 'detail' } })}
                  className="w-full bg-gray-50 hover:bg-gray-100 rounded-xl p-4 transition-all text-left border-2 border-transparent hover:border-deep-teal"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="inline-block px-2.5 py-1 rounded-full text-xs font-semibold bg-lavender/20 text-dark-navy">
                          {getCategoryLabel(post.category)}
                        </span>
                        <span className="text-xs text-gray-500 flex items-center gap-1">
                          <Calendar size={12} />
                          {post.date}
                        </span>
                      </div>
                      <h4 className="font-semibold text-dark-navy mb-2 truncate">{post.title}</h4>
                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <Eye size={12} />
                          {post.views}
                        </span>
                        <span className="flex items-center gap-1">
                          <ThumbsUp size={12} />
                          {post.likes}
                        </span>
                        <span className="flex items-center gap-1">
                          <MessageCircle size={12} />
                          {post.comments}
                        </span>
                      </div>
                    </div>
                    <div className="flex-shrink-0">
                      <div className="w-10 h-10 bg-deep-teal rounded-full flex items-center justify-center">
                        <FileText size={20} className="text-white" />
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
            <Pagination currentPage={myPostsPage} totalPages={myPostsTotalPages} onPageChange={setMyPostsPage} />
          </>
        )}
      </div>

      {/* 내가 댓글을 단 게시글 */}
      <div className="bg-white rounded-2xl shadow-lg p-6 sm:p-8 mt-6">
        <div className="flex items-center gap-3 mb-6">
          <MessageSquare size={24} className="text-deep-teal" />
          <h3 className="text-xl font-bold text-dark-navy">내가 댓글을 단 게시글</h3>
          <span className="text-sm text-gray-purple">({commentedPosts.length}개)</span>
        </div>

        {commentedPosts.length === 0 ? (
          <div className="text-center py-12">
            <MessageSquare size={48} className="text-gray-300 mx-auto mb-4" />
            <p className="text-gray-purple mb-4">아직 댓글을 단 게시글이 없습니다</p>
            <button
              onClick={() => navigate(ROUTES.BOARD)}
              className="inline-flex items-center gap-2 bg-deep-teal text-white px-6 py-3 rounded-full font-semibold hover:bg-mint-green transition-all"
            >
              <FileText size={18} />
              게시판 둘러보기
            </button>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {paginatedCommentedPosts.map((post) => (
                <button
                  key={post.id}
                  onClick={() => navigate(ROUTES.BOARD, { state: { postId: post.id, viewType: 'detail' } })}
                  className="w-full bg-gray-50 hover:bg-gray-100 rounded-xl p-4 transition-all text-left border-2 border-transparent hover:border-deep-teal"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="inline-block px-2.5 py-1 rounded-full text-xs font-semibold bg-lavender/20 text-dark-navy">
                          {getCategoryLabel(post.category)}
                        </span>
                        <span className="text-xs text-gray-500 flex items-center gap-1">
                          <Calendar size={12} />
                          댓글 작성: {post.myCommentDate}
                        </span>
                      </div>
                      <h4 className="font-semibold text-dark-navy mb-2 truncate">{post.title}</h4>
                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <Eye size={12} />
                          {post.views}
                        </span>
                        <span className="flex items-center gap-1">
                          <ThumbsUp size={12} />
                          {post.likes}
                        </span>
                        <span className="flex items-center gap-1">
                          <MessageCircle size={12} />
                          {post.comments}
                        </span>
                      </div>
                    </div>
                    <div className="flex-shrink-0">
                      <div className="w-10 h-10 bg-deep-teal rounded-full flex items-center justify-center">
                        <MessageSquare size={20} className="text-white" />
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
            <Pagination currentPage={commentedPostsPage} totalPages={commentedPostsTotalPages} onPageChange={setCommentedPostsPage} />
          </>
        )}
      </div>
    </div>
  );
}
