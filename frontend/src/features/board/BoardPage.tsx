import { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { Search, ThumbsUp, Calendar, Eye, MessageSquare, Lock, Loader2 } from 'lucide-react';
import { CATEGORY_DISPLAY_MAP, CATEGORY_LABELS, POST_CATEGORIES } from '@/shared/config/categories';
import { useAuthStore } from '@/features/auth/auth.store';
import { useUIStore } from '@/store/ui.store';
import { boardService, type PostListItem, type PostDetail as PostDetailType } from '@/shared/api/board.service';
import type { BoardCategoryId, BoardPost, BoardPostForm, BoardSearchType } from './board.types';
import WritePost from './components/WritePost';
import PostDetail from './components/PostDetail';
import EditPost from './components/EditPost';

export default function BoardPage() {
  const location = useLocation();
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const setIsAuthModalOpen = useUIStore((state) => state.setIsAuthModalOpen);

  const [activeTab, setActiveTab] = useState<BoardCategoryId>('all');
  const [currentView, setCurrentView] = useState<'list' | 'write' | 'detail' | 'edit'>('list');
  const [selectedPost, setSelectedPost] = useState<BoardPost | null>(null);
  const [selectedPostDetail, setSelectedPostDetail] = useState<PostDetailType | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchType, setSearchType] = useState<BoardSearchType>('title');

  // API 상태
  const [posts, setPosts] = useState<BoardPost[]>([]);
  const [totalPosts, setTotalPosts] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 카테고리를 첫 번째 "/"를 기준으로 2줄로 나누는 함수
  const splitCategory = (category: string) => {
    const firstSlashIndex = category.indexOf('/');
    if (firstSlashIndex === -1) return [category];
    return [
      category.substring(0, firstSlashIndex),
      category.substring(firstSlashIndex + 1)
    ];
  };

  // 작성자 표시 함수 (탈퇴한 사용자 처리)
  const getAuthorDisplayName = (nickname: string | undefined, isDeleted = false) => {
    if (isDeleted || !nickname) {
      return '탈퇴한 사용자';
    }
    return nickname;
  };

  // 날짜 포맷 함수
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('ko-KR').replace(/\. /g, '.').slice(0, -1);
  };

  // API에서 게시글 목록 가져오기
  const fetchPosts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const categoryParam = activeTab === 'all' ? undefined : activeTab;
      const response = await boardService.getPosts({
        page: currentPage,
        limit: itemsPerPage,
        category: categoryParam,
        search: searchQuery || undefined,
        search_type: searchType,
      });

      // API 응답을 BoardPost 형식으로 변환
      const convertedPosts: BoardPost[] = response.posts.map((p: PostListItem) => ({
        id: p.id,
        category: p.category,
        category_key: p.category_key,
        sub_category: p.sub_category,
        title: p.title,
        author_id: p.author_id,
        author_nickname: p.author_nickname,
        is_author_deleted: p.is_author_deleted,
        created_at: p.created_at,
        edited_at: p.edited_at,
        view_count: p.view_count,
        like_count: p.like_count,
        comment_count: p.comment_count,
        preview: p.preview,
      }));

      setPosts(convertedPosts);
      setTotalPosts(response.total);
      setTotalPages(response.total_pages);
    } catch (err) {
      setError('게시글을 불러오는데 실패했습니다.');
      console.error('Failed to fetch posts:', err);
    } finally {
      setIsLoading(false);
    }
  }, [activeTab, currentPage, itemsPerPage, searchQuery, searchType]);

  // 게시글 목록 새로고침
  useEffect(() => {
    if (isAuthenticated && currentView === 'list') {
      fetchPosts();
    }
  }, [isAuthenticated, currentView, fetchPosts]);

  // 마이페이지에서 게시글 클릭 시 해당 게시글 상세보기로 이동
  useEffect(() => {
    const state = location.state as { postId?: string; viewType?: string } | null;
    if (state?.postId && state?.viewType === 'detail') {
      handlePostClick({ id: state.postId } as BoardPost);
      window.history.replaceState({}, document.title);
    }
  }, [location.state]);

  const getCategoryDisplayName = (categoryId: BoardCategoryId) => {
    if (categoryId === 'all') {
      return CATEGORY_LABELS.all;
    }
    return CATEGORY_DISPLAY_MAP[categoryId];
  };

  const handleWritePost = async (formData: BoardPostForm) => {
    try {
      const response = await boardService.createPost({
        category: formData.category,
        sub_category: formData.subCategory as 'pre-mediation' | 'mediation' | undefined,
        title: formData.title,
        content: formData.content,
      });

      // 작성 완료 후 상세 페이지로 이동
      setSelectedPostDetail(response);
      setSelectedPost({
        id: response.id,
        category: response.category,
        category_key: response.category_key,
        sub_category: response.sub_category,
        title: response.title,
        author_id: response.author_id,
        author_nickname: response.author_nickname,
        is_author_deleted: response.is_author_deleted,
        created_at: response.created_at,
        edited_at: response.edited_at,
        view_count: response.view_count,
        like_count: response.like_count,
        comment_count: response.comment_count,
        preview: response.preview,
      });
      setCurrentView('detail');
      window.scrollTo(0, 0);
    } catch (err) {
      console.error('Failed to create post:', err);
      alert('게시글 작성에 실패했습니다.');
    }
  };

  const handlePostClick = async (post: BoardPost) => {
    try {
      const response = await boardService.getPost(post.id);
      setSelectedPostDetail(response);
      setSelectedPost({
        id: response.id,
        category: response.category,
        category_key: response.category_key,
        sub_category: response.sub_category,
        title: response.title,
        author_id: response.author_id,
        author_nickname: response.author_nickname,
        is_author_deleted: response.is_author_deleted,
        created_at: response.created_at,
        edited_at: response.edited_at,
        view_count: response.view_count,
        like_count: response.like_count,
        comment_count: response.comment_count,
        preview: response.preview,
      });
      setCurrentView('detail');
      window.scrollTo(0, 0);
    } catch (err) {
      console.error('Failed to fetch post:', err);
      alert('게시글을 불러오는데 실패했습니다.');
    }
  };

  const handleEditPost = (post: BoardPost) => {
    setSelectedPost(post);
    setCurrentView('edit');
  };

  const handleUpdatePost = async (postId: string, formData: BoardPostForm) => {
    try {
      await boardService.updatePost(postId, {
        category: formData.category,
        sub_category: formData.subCategory as 'pre-mediation' | 'mediation' | undefined,
        title: formData.title,
        content: formData.content,
      });

      // 수정 완료 후 상세 페이지 다시 로드
      const response = await boardService.getPost(postId);
      setSelectedPostDetail(response);
      setSelectedPost({
        id: response.id,
        category: response.category,
        category_key: response.category_key,
        sub_category: response.sub_category,
        title: response.title,
        author_id: response.author_id,
        author_nickname: response.author_nickname,
        is_author_deleted: response.is_author_deleted,
        created_at: response.created_at,
        edited_at: response.edited_at,
        view_count: response.view_count,
        like_count: response.like_count,
        comment_count: response.comment_count,
        preview: response.preview,
      });
      setCurrentView('detail');
      window.scrollTo(0, 0);
    } catch (err) {
      console.error('Failed to update post:', err);
      alert('게시글 수정에 실패했습니다.');
    }
  };

  const handleDeletePost = async (postId: string) => {
    try {
      await boardService.deletePost(postId);
      setCurrentView('list');
      await fetchPosts();
    } catch (err) {
      console.error('Failed to delete post:', err);
      alert('게시글 삭제에 실패했습니다.');
    }
  };

  const categories: Array<{ id: BoardCategoryId; name: string }> = [
    { id: POST_CATEGORIES.ALL, name: CATEGORY_LABELS.all },
    { id: POST_CATEGORIES.CASE_SHARING, name: CATEGORY_LABELS['case-sharing'] },
    { id: POST_CATEGORIES.QNA, name: CATEGORY_LABELS.qna },
    { id: POST_CATEGORIES.TIPS, name: CATEGORY_LABELS.tips },
  ];

  // 페이지 번호 배열 생성 (최대 10개)
  const getPageNumbers = () => {
    const pageNumbers = [];
    const maxPagesToShow = 10;

    let startPage = Math.max(1, currentPage - Math.floor(maxPagesToShow / 2));
    let endPage = Math.min(totalPages, startPage + maxPagesToShow - 1);

    if (endPage - startPage < maxPagesToShow - 1) {
      startPage = Math.max(1, endPage - maxPagesToShow + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
      pageNumbers.push(i);
    }

    return pageNumbers;
  };

  // 페이지 변경 핸들러
  const handlePageChange = (pageNumber: number) => {
    setCurrentPage(pageNumber);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // 페이지당 표시 개수 변경 핸들러
  const handleItemsPerPageChange = (newItemsPerPage: number) => {
    setItemsPerPage(newItemsPerPage);
    setCurrentPage(1);
  };

  // 카테고리 변경 시 첫 페이지로 리셋
  const handleTabChange = (tabId: BoardCategoryId) => {
    setActiveTab(tabId);
    setCurrentPage(1);
  };

  // 검색 실행
  const handleSearch = () => {
    setCurrentPage(1);
    fetchPosts();
  };

  // Conditional rendering based on current view
  if (currentView === 'write') {
    return (
      <WritePost
        onBack={() => setCurrentView('list')}
        onSubmit={handleWritePost}
      />
    );
  }

  if (currentView === 'edit' && selectedPost && selectedPostDetail) {
    return (
      <EditPost
        post={selectedPost}
        content={selectedPostDetail.content}
        onBack={() => setCurrentView('detail')}
        onSubmit={handleUpdatePost}
      />
    );
  }

  if (currentView === 'detail' && selectedPost && selectedPostDetail) {
    return (
      <PostDetail
        post={selectedPost}
        postDetail={selectedPostDetail}
        onBack={() => setCurrentView('list')}
        onEdit={handleEditPost}
        onDelete={handleDeletePost}
      />
    );
  }

  // 로그인하지 않은 경우 안내 메시지 표시
  if (!isAuthenticated) {
    return (
      <div className="board-page">
        <div className="mb-6 md:mb-8">
          <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold mb-3 md:mb-4 text-dark-navy">자유게시판</h1>
          <p className="text-sm sm:text-base text-gray-purple">소비자 분쟁 경험을 공유하고 서로 도와요</p>
        </div>

        <div className="bg-white rounded-2xl shadow-lg p-8 md:p-12 text-center">
          <div className="flex flex-col items-center gap-6">
            <div className="w-20 h-20 bg-lavender/30 rounded-full flex items-center justify-center">
              <Lock size={40} className="text-deep-teal" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-dark-navy mb-3">로그인이 필요합니다</h2>
              <p className="text-gray-purple mb-6">자유게시판은 로그인을 한 회원만 이용할 수 있습니다.</p>
              <button
                onClick={() => setIsAuthModalOpen(true)}
                className="inline-flex items-center gap-2 bg-deep-teal text-white px-8 py-3 rounded-full font-semibold hover:bg-mint-green transition-all"
              >
                로그인하러 가기
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="board-page">
      {/* Board Header */}
      <div className="mb-6 md:mb-8">
        <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold mb-3 md:mb-4 text-dark-navy">자유게시판</h1>
        <p className="text-sm sm:text-base text-gray-purple">소비자 분쟁 경험을 공유하고 서로 도와요</p>
      </div>

      {/* Category Tabs */}
      <div className="flex gap-2 mb-4 md:mb-5 flex-wrap">
        {categories.map(cat => (
          <button
            key={cat.id}
            className={`px-4 sm:px-5 md:px-6 py-2 md:py-3 rounded-full text-sm md:text-base font-medium transition-all ${
              activeTab === cat.id
                ? 'bg-deep-teal text-white'
                : 'bg-white border-2 border-ivory text-gray-purple hover:border-deep-teal'
            }`}
            onClick={() => handleTabChange(cat.id)}
          >
            {cat.name}
          </button>
        ))}
      </div>

      {/* Write Button */}
      <div className="flex justify-end mb-6 md:mb-8">
        <button
          onClick={() => setCurrentView('write')}
          className="bg-deep-teal text-white px-6 sm:px-8 py-3 md:py-4 rounded-full text-sm sm:text-base font-semibold hover:bg-mint-green hover:-translate-y-1 transition-all whitespace-nowrap"
        >
          글쓰기
        </button>
      </div>

      {/* Search Bar */}
      <div className="flex items-center gap-3 md:gap-4 bg-white px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-full mb-4 md:mb-5 shadow-md">
        <Search size={18} className="text-gray-purple sm:w-5 sm:h-5" />
        <select
          value={searchType}
          onChange={(e) => setSearchType(e.target.value as BoardSearchType)}
          className="px-3 py-1.5 border-2 border-ivory rounded-lg text-sm font-medium text-gray-700 hover:border-lavender focus:outline-none focus:border-deep-teal transition-colors cursor-pointer"
        >
          <option value="title">제목</option>
          <option value="author">작성자</option>
          <option value="content">내용</option>
          <option value="title_content">제목+내용</option>
        </select>
        <input
          type="text"
          placeholder="게시글 검색..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          className="flex-1 outline-none text-sm sm:text-base"
        />
        <button
          onClick={handleSearch}
          className="px-4 py-1.5 bg-deep-teal text-white rounded-lg text-sm font-medium hover:bg-mint-green transition-colors"
        >
          검색
        </button>
      </div>

      {/* Items Per Page Selector & Info */}
      <div className="flex justify-between items-center mb-6 md:mb-8">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <span>전체 {totalPosts}개</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-600">페이지당</span>
          <select
            value={itemsPerPage}
            onChange={(e) => handleItemsPerPageChange(Number(e.target.value))}
            className="px-3 py-1.5 border-2 border-ivory rounded-lg text-sm font-medium text-gray-700 hover:border-lavender focus:outline-none focus:border-deep-teal transition-colors cursor-pointer"
          >
            <option value={10}>10개</option>
            <option value={30}>30개</option>
            <option value={50}>50개</option>
          </select>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="flex justify-center items-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-deep-teal" />
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-50 text-red-600 p-4 rounded-xl text-center mb-6">
          {error}
          <button onClick={fetchPosts} className="ml-4 underline">다시 시도</button>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && posts.length === 0 && (
        <div className="bg-white rounded-2xl shadow-md p-12 text-center">
          <p className="text-gray-500">게시글이 없습니다.</p>
        </div>
      )}

      {/* Posts - Mobile Card View */}
      {!isLoading && !error && posts.length > 0 && (
        <>
          <div className="xl:hidden flex flex-col gap-3">
            {posts.map(post => (
              <div
                key={post.id}
                onClick={() => handlePostClick(post)}
                className="bg-white p-3 rounded-xl shadow-md hover:shadow-lg transition-all cursor-pointer"
              >
                <div className="flex items-start justify-between mb-2">
                  <span className="inline-block px-2.5 py-1 bg-lavender/20 text-dark-navy rounded-full text-[11px] font-semibold whitespace-nowrap">
                    {post.category.replace('/', ' ')}
                  </span>
                  <div className="flex items-center gap-1 text-[10px] text-gray-500">
                    <Calendar size={10} />
                    <span>{formatDate(post.created_at)}</span>
                  </div>
                </div>

                <div className="group mb-2">
                  <h3 className="text-sm font-bold text-dark-navy mb-1 hover:text-deep-teal transition-colors">
                    {post.title}
                  </h3>
                  <p className="text-xs text-gray-500 line-clamp-2 hidden group-hover:block">{post.preview}</p>
                </div>

                <div className="flex items-center justify-between text-[10px] text-gray-600 pt-2 border-t border-gray-100">
                  <span className="font-medium">{getAuthorDisplayName(post.author_nickname, post.is_author_deleted)}</span>
                  <div className="flex items-center gap-2.5">
                    <div className="flex items-center gap-0.5">
                      <Eye size={10} />
                      <span>{post.view_count}</span>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <MessageSquare size={10} />
                      <span>{post.comment_count}</span>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <ThumbsUp size={10} />
                      <span>{post.like_count}</span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Posts - Desktop Table View */}
          <div className="hidden xl:block bg-white rounded-2xl shadow-md overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b-2 border-gray-200">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 w-32">카테고리</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600">제목</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 w-28">날짜</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 w-36">닉네임</th>
                    <th className="px-3 py-3 text-center text-xs font-semibold text-gray-600 w-16">조회</th>
                    <th className="px-3 py-3 text-center text-xs font-semibold text-gray-600 w-16">댓글</th>
                    <th className="px-3 py-3 text-center text-xs font-semibold text-gray-600 w-16">좋아요</th>
                  </tr>
                </thead>
                <tbody>
                  {posts.map(post => (
                    <tr
                      key={post.id}
                      onClick={() => handlePostClick(post)}
                      className="border-b border-gray-100 hover:bg-lavender/10 transition-colors cursor-pointer"
                    >
                      <td className="px-4 py-3">
                        <span className="inline-block px-2.5 py-1 bg-lavender/20 text-dark-navy rounded-full text-[11px] font-semibold text-center leading-relaxed">
                          {splitCategory(post.category).map((line, idx) => (
                            <span key={idx}>
                              {line}
                              {idx < splitCategory(post.category).length - 1 && <br />}
                            </span>
                          ))}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="group">
                          <h3 className="text-sm font-semibold text-dark-navy mb-0.5 hover:text-deep-teal transition-colors">
                            {post.title}
                          </h3>
                          <p className="text-xs text-gray-500 line-clamp-1 hidden group-hover:block">{post.preview}</p>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5 text-xs text-gray-600">
                          <Calendar size={12} />
                          <span>{formatDate(post.created_at)}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs font-medium text-gray-700 max-w-36">
                        <div className="line-clamp-2">
                          {getAuthorDisplayName(post.author_nickname, post.is_author_deleted)}
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center justify-center gap-0.5 text-xs text-gray-600">
                          <Eye size={12} />
                          <span>{post.view_count}</span>
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center justify-center gap-0.5 text-xs text-gray-600">
                          <MessageSquare size={12} />
                          <span>{post.comment_count}</span>
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <div className="flex items-center justify-center gap-0.5 text-xs text-gray-600">
                          <ThumbsUp size={12} />
                          <span>{post.like_count}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
              {/* Previous Button */}
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                className={`px-4 py-2 rounded-lg font-medium text-sm transition-all ${
                  currentPage === 1
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-white border-2 border-ivory text-gray-700 hover:border-deep-teal hover:text-deep-teal'
                }`}
              >
                이전
              </button>

              {/* Page Numbers */}
              <div className="flex items-center gap-1 sm:gap-2 flex-wrap justify-center">
                {getPageNumbers().map(pageNumber => (
                  <button
                    key={pageNumber}
                    onClick={() => handlePageChange(pageNumber)}
                    className={`w-8 h-8 sm:w-10 sm:h-10 rounded-lg font-medium text-sm transition-all ${
                      currentPage === pageNumber
                        ? 'bg-deep-teal text-white'
                        : 'bg-white border-2 border-ivory text-gray-700 hover:border-deep-teal hover:text-deep-teal'
                    }`}
                  >
                    {pageNumber}
                  </button>
                ))}
              </div>

              {/* Next Button */}
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage === totalPages}
                className={`px-4 py-2 rounded-lg font-medium text-sm transition-all ${
                  currentPage === totalPages
                    ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                    : 'bg-white border-2 border-ivory text-gray-700 hover:border-deep-teal hover:text-deep-teal'
                }`}
              >
                다음
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
