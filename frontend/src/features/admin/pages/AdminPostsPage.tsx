import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '@/shared/api/client';
import type { AdminPost, PostSearchParams } from '@/shared/types/admin';

/**
 * 게시글 관리 페이지
 *
 * SEC-34: 테스트 토큰 조건 분기 제거
 * 모든 데이터는 백엔드 API를 통해서만 조회/수정됩니다.
 */
export default function AdminPostsPage() {
  const [searchParams] = useSearchParams();
  const [posts, setPosts] = useState<AdminPost[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedPost, setSelectedPost] = useState<AdminPost | null>(null);
  const [showNoticeModal, setShowNoticeModal] = useState(false);

  const [searchFilters, setSearchFilters] = useState<PostSearchParams>({
    searchType: 'title',
    searchKeyword: '',
    category: '',
    isPublic: undefined,
    page: 1,
    limit: 20,
  });

  useEffect(() => {
    fetchPosts();
  }, [searchFilters]);

  useEffect(() => {
    const action = searchParams.get('action');
    if (action === 'write-notice') {
      setShowNoticeModal(true);
    }
  }, [searchParams]);

  const fetchPosts = async () => {
    setIsLoading(true);
    try {
      // SEC-34: 백엔드 API만 사용
      const data = await apiClient.get<AdminPost[]>('/api/admin/posts', searchFilters);
      setPosts(data);
    } catch (error) {
      console.error('게시글 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = () => {
    setSearchFilters({ ...searchFilters, page: 1 });
    fetchPosts();
  };

  const handleTogglePublic = async (postId: number, isPublic: boolean) => {
    if (!confirm(`이 게시글을 ${isPublic ? '비공개' : '공개'} 처리하시겠습니까?`)) {
      return;
    }

    try {
      await apiClient.put(`/api/admin/posts/${postId}/visibility`, { isPublic: !isPublic });
      alert('게시글 상태가 변경되었습니다.');
      fetchPosts();
    } catch {
      alert('상태 변경에 실패했습니다.');
    }
  };

  const handleDeletePost = async (postId: number) => {
    if (!confirm('이 게시글을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) {
      return;
    }

    try {
      await apiClient.delete(`/api/admin/posts/${postId}`);
      alert('게시글이 삭제되었습니다.');
      fetchPosts();
    } catch {
      alert('게시글 삭제에 실패했습니다.');
    }
  };

  const handleViewDetail = async (postId: number) => {
    try {
      const post = await apiClient.get<AdminPost>(`/api/admin/posts/${postId}`);
      setSelectedPost(post);
    } catch {
      alert('게시글을 불러올 수 없습니다.');
    }
  };

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">게시글 관리</h1>
        <button
          onClick={() => setShowNoticeModal(true)}
          className="px-4 py-2 bg-teal-600 text-white text-sm rounded-md hover:bg-teal-700"
        >
          공지사항 작성
        </button>
      </div>

      {/* 검색 필터 */}
      <div className="bg-white p-4 rounded-lg shadow mb-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <select
            value={searchFilters.searchType}
            onChange={(e) => setSearchFilters({ ...searchFilters, searchType: e.target.value as any })}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="title">제목</option>
            <option value="author">작성자</option>
            <option value="title_author">제목+작성자</option>
            <option value="keyword">키워드</option>
          </select>

          <input
            type="text"
            value={searchFilters.searchKeyword}
            onChange={(e) => setSearchFilters({ ...searchFilters, searchKeyword: e.target.value })}
            placeholder="검색어 입력"
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          />

          <select
            value={searchFilters.isPublic === undefined ? '' : searchFilters.isPublic.toString()}
            onChange={(e) =>
              setSearchFilters({
                ...searchFilters,
                isPublic: e.target.value === '' ? undefined : e.target.value === 'true',
              })
            }
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">전체</option>
            <option value="true">공개</option>
            <option value="false">비공개</option>
          </select>

          <button
            onClick={handleSearch}
            className="px-4 py-2 bg-gray-800 text-white text-sm rounded-md hover:bg-gray-900"
          >
            검색
          </button>
        </div>
      </div>

      {/* 게시글 목록 */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">로딩 중...</div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">분류</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">제목</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">작성자</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">작성일</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">조회수</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">상태</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">작업</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {posts.map((post) => (
                <tr key={post.id} className={!post.isPublic ? 'bg-red-50' : ''}>
                  <td className="px-4 py-3 text-xs">{post.id}</td>
                  <td className="px-4 py-3 text-xs">{post.category}</td>
                  <td className="px-4 py-3 text-xs">
                    <button
                      onClick={() => handleViewDetail(post.id)}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      {post.title}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs">{post.author}</td>
                  <td className="px-4 py-3 text-xs">{new Date(post.createdAt).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-xs">{post.views}</td>
                  <td className="px-4 py-3 text-xs">
                    <span
                      className={`px-2 py-1 rounded-full text-xs ${
                        post.isPublic
                          ? 'bg-green-100 text-green-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {post.isPublic ? '공개' : '비공개'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs space-x-2">
                    <button
                      onClick={() => handleTogglePublic(post.id, post.isPublic)}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      {post.isPublic ? '비공개' : '공개'}
                    </button>
                    <button
                      onClick={() => handleDeletePost(post.id)}
                      className="text-red-600 hover:underline text-xs"
                    >
                      삭제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {posts.length === 0 && (
            <div className="text-center py-12 text-gray-500">게시글이 없습니다.</div>
          )}
        </div>
      )}

      {/* 게시글 상세 모달 */}
      {selectedPost && (
        <PostDetailModal post={selectedPost} onClose={() => setSelectedPost(null)} />
      )}

      {/* 공지사항 작성 모달 */}
      {showNoticeModal && (
        <NoticeModal onClose={() => setShowNoticeModal(false)} onSuccess={fetchPosts} />
      )}
    </div>
  );
}

interface PostDetailModalProps {
  post: AdminPost;
  onClose: () => void;
}

function PostDetailModal({ post, onClose }: PostDetailModalProps) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-3xl w-full max-h-[80vh] overflow-y-auto">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h2 className="text-2xl font-bold">{post.title}</h2>
            <p className="text-sm text-gray-500 mt-1">
              {post.author} · {new Date(post.createdAt).toLocaleString()}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        <div className="mb-4">
          <span className="px-3 py-1 bg-gray-100 rounded-full text-sm">{post.category}</span>
          <span
            className={`ml-2 px-3 py-1 rounded-full text-sm ${
              post.isPublic ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
            }`}
          >
            {post.isPublic ? '공개' : '비공개'}
          </span>
        </div>

        <div className="prose max-w-none mb-4">
          <div className="whitespace-pre-wrap">{post.content}</div>
        </div>

        <div className="flex gap-2 text-sm text-gray-600 mb-4">
          <span>조회수: {post.views}</span>
          <span>·</span>
          <span>좋아요: {post.likes}</span>
          <span>·</span>
          <span>댓글: {post.commentsCount}</span>
        </div>

        <div className="flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 text-white rounded-md hover:bg-gray-900"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

interface NoticeModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

function NoticeModal({ onClose, onSuccess }: NoticeModalProps) {
  const [notice, setNotice] = useState({
    title: '',
    content: '',
    isPinned: true,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!notice.title || !notice.content) {
      alert('제목과 내용을 모두 입력해주세요.');
      return;
    }

    try {
      await apiClient.post('/api/admin/posts/notice', notice);
      alert('공지사항이 작성되었습니다.');
      onSuccess();
      onClose();
    } catch {
      alert('공지사항 작성에 실패했습니다.');
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full">
        <h2 className="text-2xl font-bold mb-4">공지사항 작성</h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">제목</label>
            <input
              type="text"
              value={notice.title}
              onChange={(e) => setNotice({ ...notice, title: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              placeholder="공지사항 제목"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">내용</label>
            <textarea
              value={notice.content}
              onChange={(e) => setNotice({ ...notice, content: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md h-64"
              placeholder="공지사항 내용을 입력하세요.&#10;&#10;게시판 이용 규칙:&#10;- 욕설, 비방, 혐오 표현 금지&#10;- 음란물, 불법 정보 게시 금지&#10;- 동일 내용 반복 게시 및 상업적 광고 금지&#10;&#10;위반 시 제재:&#10;- 게시물 비공개 또는 삭제 처리&#10;- 경고, 이용 제한, 계정 정지 조치 가능"
            />
          </div>

          <div className="flex items-center">
            <input
              type="checkbox"
              id="isPinned"
              checked={notice.isPinned}
              onChange={(e) => setNotice({ ...notice, isPinned: e.target.checked })}
              className="mr-2"
            />
            <label htmlFor="isPinned" className="text-sm">
              상단 고정
            </label>
          </div>

          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              취소
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700"
            >
              작성
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
