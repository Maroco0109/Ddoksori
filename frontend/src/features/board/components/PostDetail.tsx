import { useState, useEffect, useCallback } from 'react';
import type { FormEvent } from 'react';
import type { BoardPost, BoardComment } from '../board.types';
import { boardService, type PostDetail as PostDetailType, type Comment as ApiComment } from '@/shared/api/board.service';
import { useAuthStore } from '@/features/auth/auth.store';
import { ArrowLeft, ThumbsUp, Eye, MessageSquare, Send, CornerDownRight, Edit2, Trash2, Flag, Loader2 } from 'lucide-react';

interface PostDetailProps {
  post: BoardPost;
  postDetail: PostDetailType;
  onBack: () => void;
  onEdit: (post: BoardPost) => void;
  onDelete: (postId: string) => Promise<void>;
}

export default function PostDetail({ post, postDetail, onBack, onEdit, onDelete }: PostDetailProps) {
  const user = useAuthStore((state) => state.user);
  const currentUserId = user?.id || '';
  const isAuthor = post.author_id === currentUserId;

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

  // State
  const [comments, setComments] = useState<BoardComment[]>([]);
  const [isLoadingComments, setIsLoadingComments] = useState(false);
  const [newComment, setNewComment] = useState('');
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyContent, setReplyContent] = useState('');
  const [liked, setLiked] = useState(postDetail.is_liked);
  const [likeCount, setLikeCount] = useState(postDetail.like_count);
  const [editingCommentId, setEditingCommentId] = useState<string | null>(null);
  const [editingReplyId, setEditingReplyId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [reportModal, setReportModal] = useState<{
    isOpen: boolean;
    type: 'post' | 'comment' | 'reply' | '';
    targetId: string | null;
    parentId: string | null;
  }>({ isOpen: false, type: '', targetId: null, parentId: null });
  const [reportReason, setReportReason] = useState('');

  // Fetch comments from API
  const fetchComments = useCallback(async () => {
    setIsLoadingComments(true);
    try {
      const response = await boardService.getComments(post.id);
      const convertedComments: BoardComment[] = response.comments.map((c: ApiComment) => ({
        id: c.id,
        content: c.content,
        author_id: c.author_id,
        author_nickname: c.author_nickname,
        is_author_deleted: c.is_author_deleted,
        like_count: c.like_count,
        is_liked: c.is_liked,
        created_at: c.created_at,
        edited_at: c.edited_at,
        replies: c.replies.map(r => ({
          id: r.id,
          content: r.content,
          author_id: r.author_id,
          author_nickname: r.author_nickname,
          is_author_deleted: r.is_author_deleted,
          like_count: r.like_count,
          is_liked: r.is_liked,
          created_at: r.created_at,
          edited_at: r.edited_at,
        })),
      }));
      setComments(convertedComments);
    } catch (err) {
      console.error('Failed to fetch comments:', err);
    } finally {
      setIsLoadingComments(false);
    }
  }, [post.id]);

  useEffect(() => {
    fetchComments();
  }, [fetchComments]);

  const handleAddComment = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!newComment.trim()) return;

    try {
      await boardService.createComment(post.id, newComment);
      setNewComment('');
      fetchComments();
    } catch (err) {
      console.error('Failed to create comment:', err);
      alert('댓글 작성에 실패했습니다.');
    }
  };

  const handleAddReply = async (commentId: string) => {
    if (!replyContent.trim()) return;

    try {
      await boardService.createReply(commentId, replyContent);
      setReplyContent('');
      setReplyingTo(null);
      fetchComments();
    } catch (err) {
      console.error('Failed to create reply:', err);
      alert('답글 작성에 실패했습니다.');
    }
  };

  const handleTogglePostLike = async () => {
    try {
      const response = await boardService.togglePostLike(post.id);
      setLiked(response.liked);
      setLikeCount(response.like_count);
    } catch (err) {
      console.error('Failed to toggle like:', err);
    }
  };

  const handleLikeComment = async (commentId: string) => {
    try {
      const response = await boardService.toggleCommentLike(commentId);
      setComments(comments.map(comment => {
        if (comment.id === commentId) {
          return { ...comment, is_liked: response.liked, like_count: response.like_count };
        }
        // Check if this is a reply
        return {
          ...comment,
          replies: comment.replies.map(reply =>
            reply.id === commentId
              ? { ...reply, is_liked: response.liked, like_count: response.like_count }
              : reply
          ),
        };
      }));
    } catch (err) {
      console.error('Failed to toggle comment like:', err);
    }
  };

  // 댓글 수정 시작
  const startEditComment = (commentId: string, content: string) => {
    setEditingCommentId(commentId);
    setEditContent(content);
  };

  // 댓글 수정 저장
  const handleEditComment = async (commentId: string) => {
    if (!editContent.trim()) return;

    try {
      await boardService.updateComment(commentId, editContent);
      setEditingCommentId(null);
      setEditContent('');
      fetchComments();
    } catch (err) {
      console.error('Failed to update comment:', err);
      alert('댓글 수정에 실패했습니다.');
    }
  };

  // 댓글 삭제
  const handleDeleteComment = async (commentId: string) => {
    if (window.confirm('정말 이 댓글을 삭제하시겠습니까?')) {
      try {
        await boardService.deleteComment(commentId);
        fetchComments();
      } catch (err) {
        console.error('Failed to delete comment:', err);
        alert('댓글 삭제에 실패했습니다.');
      }
    }
  };

  // 대댓글 수정 시작
  const startEditReply = (replyId: string, content: string) => {
    setEditingReplyId(replyId);
    setEditContent(content);
  };

  // 대댓글 수정 저장
  const handleEditReply = async (replyId: string) => {
    if (!editContent.trim()) return;

    try {
      await boardService.updateComment(replyId, editContent);
      setEditingReplyId(null);
      setEditContent('');
      fetchComments();
    } catch (err) {
      console.error('Failed to update reply:', err);
      alert('답글 수정에 실패했습니다.');
    }
  };

  // 대댓글 삭제
  const handleDeleteReply = async (replyId: string) => {
    if (window.confirm('정말 이 답글을 삭제하시겠습니까?')) {
      try {
        await boardService.deleteComment(replyId);
        fetchComments();
      } catch (err) {
        console.error('Failed to delete reply:', err);
        alert('답글 삭제에 실패했습니다.');
      }
    }
  };

  const [isDeleting, setIsDeleting] = useState(false);

  const handleDelete = async () => {
    if (window.confirm('정말 이 게시글을 삭제하시겠습니까?')) {
      setIsDeleting(true);
      try {
        await onDelete(post.id);
      } finally {
        setIsDeleting(false);
      }
    }
  };

  // 신고 모달 열기
  const openReportModal = (type: 'post' | 'comment' | 'reply', targetId: string, parentId: string | null = null) => {
    setReportModal({ isOpen: true, type, targetId, parentId });
    setReportReason('');
  };

  // 신고 모달 닫기
  const closeReportModal = () => {
    setReportModal({ isOpen: false, type: '', targetId: null, parentId: null });
    setReportReason('');
  };

  // 신고 제출
  const handleSubmitReport = async () => {
    if (!reportReason.trim()) {
      alert('신고 사유를 입력해주세요.');
      return;
    }

    try {
      if (reportModal.type === 'post' && reportModal.targetId) {
        await boardService.reportPost(reportModal.targetId, reportReason);
      } else if ((reportModal.type === 'comment' || reportModal.type === 'reply') && reportModal.targetId) {
        await boardService.reportComment(reportModal.targetId, reportReason);
      }
      alert('신고가 접수되었습니다.');
      closeReportModal();
    } catch (err) {
      console.error('Failed to submit report:', err);
      alert('신고 접수에 실패했습니다.');
    }
  };

  return (
    <div className="post-detail-page">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 md:mb-8">
        <div className="flex items-center gap-4">
          <button
            onClick={onBack}
            className="p-2 hover:bg-gray-100 rounded-full transition-colors"
          >
            <ArrowLeft size={24} className="text-dark-navy" />
          </button>
          <h1 className="text-xl sm:text-2xl md:text-3xl font-bold text-dark-navy">게시글</h1>
        </div>

        {/* Edit & Delete Buttons - Only visible to author */}
        <div className="flex items-center gap-2">
          {isAuthor ? (
            <>
              <button
                onClick={() => onEdit(post)}
                className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg font-medium hover:bg-gray-200 transition-all"
              >
                <Edit2 size={16} />
                <span className="hidden sm:inline">수정</span>
              </button>
              <button
                onClick={handleDelete}
                disabled={isDeleting}
                className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-lg font-medium hover:bg-red-100 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isDeleting ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                <span className="hidden sm:inline">{isDeleting ? '삭제 중...' : '삭제'}</span>
              </button>
            </>
          ) : (
            <button
              onClick={() => openReportModal('post', post.id)}
              className="flex items-center gap-2 px-4 py-2 bg-orange-50 text-orange-600 rounded-lg font-medium hover:bg-orange-100 transition-all"
            >
              <Flag size={16} />
              <span className="hidden sm:inline">신고</span>
            </button>
          )}
        </div>
      </div>

      {/* Post Content */}
      <div className="bg-white rounded-2xl shadow-md p-6 md:p-8 mb-6">
        {/* Category & Date */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <span className="px-4 py-1.5 bg-lavender/20 text-dark-navy rounded-full text-sm font-semibold">
            {post.category}
          </span>
          <span className="text-sm text-gray-500">{formatDate(post.created_at)}</span>
          {post.edited_at && (
            <span className="text-sm text-gray-400">(수정됨: {formatDate(post.edited_at)})</span>
          )}
        </div>

        {/* Title */}
        <h2 className="text-2xl md:text-3xl font-bold text-dark-navy mb-4">{post.title}</h2>

        {/* Author & Stats */}
        <div className="flex items-center gap-4 pb-4 mb-6 border-b border-gray-200">
          <span className="font-semibold text-gray-700">{getAuthorDisplayName(post.author_nickname, post.is_author_deleted)}</span>
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <div className="flex items-center gap-1">
              <Eye size={16} />
              <span>{post.view_count}</span>
            </div>
            <div className="flex items-center gap-1">
              <MessageSquare size={16} />
              <span>{comments.length}</span>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="prose max-w-none mb-6">
          <p className="text-gray-700 leading-relaxed whitespace-pre-wrap">
            {postDetail.content}
          </p>
        </div>

        {/* Like Button */}
        <div className="flex justify-center pt-6 border-t border-gray-200">
          <button
            onClick={handleTogglePostLike}
            className={`flex items-center gap-2 px-8 py-3 rounded-full font-semibold transition-all ${
              liked
                ? 'bg-deep-teal text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <ThumbsUp size={20} fill={liked ? 'currentColor' : 'none'} />
            <span>좋아요 {likeCount}</span>
          </button>
        </div>
      </div>

      {/* Comments Section */}
      <div className="bg-white rounded-2xl shadow-md p-6 md:p-8">
        <h3 className="text-xl font-bold text-dark-navy mb-6 flex items-center gap-2">
          <MessageSquare size={24} />
          댓글 {comments.length}개
        </h3>

        {/* Loading State */}
        {isLoadingComments && (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin text-deep-teal" />
          </div>
        )}

        {/* Comment List */}
        {!isLoadingComments && (
          <div className="space-y-4 mb-6">
            {comments.map(comment => (
              <div key={comment.id} className="border-b border-gray-100 pb-4 last:border-0">
                {/* Main Comment */}
                <div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-semibold text-gray-800">{getAuthorDisplayName(comment.author_nickname, comment.is_author_deleted)}</span>
                      <span className="text-xs text-gray-500">{formatDate(comment.created_at)}</span>
                      {comment.edited_at && (
                        <span className="text-xs text-gray-400">(수정됨)</span>
                      )}
                    </div>

                    {/* 댓글 수정 모드 */}
                    {editingCommentId === comment.id ? (
                      <div className="mb-2 flex gap-2">
                        <input
                          type="text"
                          value={editContent}
                          onChange={(e) => setEditContent(e.target.value)}
                          className="flex-1 px-3 py-2 border-2 border-gray-200 rounded-lg text-sm outline-none focus:border-deep-teal"
                          onKeyPress={(e) => {
                            if (e.key === 'Enter') {
                              handleEditComment(comment.id);
                            }
                          }}
                        />
                        <button
                          onClick={() => handleEditComment(comment.id)}
                          className="px-3 py-1 bg-deep-teal text-white rounded-lg text-xs font-semibold hover:bg-mint-green transition-all"
                        >
                          저장
                        </button>
                        <button
                          onClick={() => {
                            setEditingCommentId(null);
                            setEditContent('');
                          }}
                          className="px-3 py-1 bg-gray-100 text-gray-700 rounded-lg text-xs font-semibold hover:bg-gray-200 transition-all"
                        >
                          취소
                        </button>
                      </div>
                    ) : (
                      <p className="text-gray-700 mb-2">{comment.content}</p>
                    )}

                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => handleLikeComment(comment.id)}
                        className={`flex items-center gap-1 text-xs transition-colors ${
                          comment.is_liked
                            ? 'text-deep-teal font-semibold'
                            : 'text-gray-500 hover:text-deep-teal'
                        }`}
                      >
                        <ThumbsUp size={14} fill={comment.is_liked ? 'currentColor' : 'none'} />
                        <span>{comment.like_count}</span>
                      </button>
                      <button
                        onClick={() => setReplyingTo(replyingTo === comment.id ? null : comment.id)}
                        className="text-xs text-gray-500 hover:text-deep-teal transition-colors"
                      >
                        답글 달기
                      </button>

                      {/* 본인이 작성한 댓글에만 수정/삭제 버튼 표시 */}
                      {comment.author_id === currentUserId ? (
                        <>
                          <button
                            onClick={() => startEditComment(comment.id, comment.content)}
                            className="flex items-center gap-1 text-xs text-gray-500 hover:text-blue-600 transition-colors"
                          >
                            <Edit2 size={14} />
                            수정
                          </button>
                          <button
                            onClick={() => handleDeleteComment(comment.id)}
                            className="flex items-center gap-1 text-xs text-gray-500 hover:text-red-600 transition-colors"
                          >
                            <Trash2 size={14} />
                            삭제
                          </button>
                        </>
                      ) : (
                        <button
                          onClick={() => openReportModal('comment', comment.id)}
                          className="flex items-center gap-1 text-xs text-gray-500 hover:text-orange-600 transition-colors"
                        >
                          <Flag size={14} />
                          신고
                        </button>
                      )}
                    </div>

                    {/* Reply Form */}
                    {replyingTo === comment.id && (
                      <div className="mt-3 flex gap-2">
                        <input
                          type="text"
                          value={replyContent}
                          onChange={(e) => setReplyContent(e.target.value)}
                          placeholder="답글을 입력하세요..."
                          className="flex-1 px-3 py-2 border-2 border-gray-200 rounded-lg text-sm outline-none focus:border-deep-teal"
                          onKeyPress={(e) => {
                            if (e.key === 'Enter') {
                              handleAddReply(comment.id);
                            }
                          }}
                        />
                        <button
                          onClick={() => handleAddReply(comment.id)}
                          className="px-4 py-2 bg-deep-teal text-white rounded-lg text-sm font-semibold hover:bg-mint-green transition-all"
                        >
                          <Send size={16} />
                        </button>
                      </div>
                    )}

                    {/* Replies */}
                    {comment.replies.length > 0 && (
                      <div className="mt-4 space-y-3 pl-4 border-l-2 border-lavender/30">
                        {comment.replies.map(reply => (
                          <div key={reply.id} className="flex gap-3">
                            <CornerDownRight size={16} className="text-gray-400 flex-shrink-0 mt-1" />
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="font-semibold text-gray-800 text-sm">{getAuthorDisplayName(reply.author_nickname, reply.is_author_deleted)}</span>
                                <span className="text-xs text-gray-500">{formatDate(reply.created_at)}</span>
                                {reply.edited_at && (
                                  <span className="text-xs text-gray-400">(수정됨)</span>
                                )}
                              </div>

                              {/* 대댓글 수정 모드 */}
                              {editingReplyId === reply.id ? (
                                <div className="mb-2 flex gap-2">
                                  <input
                                    type="text"
                                    value={editContent}
                                    onChange={(e) => setEditContent(e.target.value)}
                                    className="flex-1 px-3 py-2 border-2 border-gray-200 rounded-lg text-sm outline-none focus:border-deep-teal"
                                    onKeyPress={(e) => {
                                      if (e.key === 'Enter') {
                                        handleEditReply(reply.id);
                                      }
                                    }}
                                  />
                                  <button
                                    onClick={() => handleEditReply(reply.id)}
                                    className="px-3 py-1 bg-deep-teal text-white rounded-lg text-xs font-semibold hover:bg-mint-green transition-all"
                                  >
                                    저장
                                  </button>
                                  <button
                                    onClick={() => {
                                      setEditingReplyId(null);
                                      setEditContent('');
                                    }}
                                    className="px-3 py-1 bg-gray-100 text-gray-700 rounded-lg text-xs font-semibold hover:bg-gray-200 transition-all"
                                  >
                                    취소
                                  </button>
                                </div>
                              ) : (
                                <p className="text-gray-700 text-sm mb-2">{reply.content}</p>
                              )}

                              <div className="flex items-center gap-3">
                                <button
                                  onClick={() => handleLikeComment(reply.id)}
                                  className={`flex items-center gap-1 text-xs transition-colors ${
                                    reply.is_liked
                                      ? 'text-deep-teal font-semibold'
                                      : 'text-gray-500 hover:text-deep-teal'
                                  }`}
                                >
                                  <ThumbsUp size={14} fill={reply.is_liked ? 'currentColor' : 'none'} />
                                  <span>{reply.like_count}</span>
                                </button>

                                {/* 본인이 작성한 대댓글에만 수정/삭제 버튼 표시 */}
                                {reply.author_id === currentUserId ? (
                                  <>
                                    <button
                                      onClick={() => startEditReply(reply.id, reply.content)}
                                      className="flex items-center gap-1 text-xs text-gray-500 hover:text-blue-600 transition-colors"
                                    >
                                      <Edit2 size={12} />
                                      수정
                                    </button>
                                    <button
                                      onClick={() => handleDeleteReply(reply.id)}
                                      className="flex items-center gap-1 text-xs text-gray-500 hover:text-red-600 transition-colors"
                                    >
                                      <Trash2 size={12} />
                                      삭제
                                    </button>
                                  </>
                                ) : (
                                  <button
                                    onClick={() => openReportModal('reply', reply.id, comment.id)}
                                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-orange-600 transition-colors"
                                  >
                                    <Flag size={12} />
                                    신고
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add Comment Form */}
        <form onSubmit={handleAddComment} className="flex gap-3">
          <input
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="댓글을 입력하세요..."
            className="flex-1 px-4 py-3 border-2 border-gray-200 rounded-full outline-none focus:border-deep-teal transition-colors"
          />
          <button
            type="submit"
            className="px-4 sm:px-6 py-3 bg-deep-teal text-white rounded-full font-semibold hover:bg-mint-green transition-all flex items-center gap-2"
          >
            <Send size={18} />
            <span className="hidden sm:inline">등록</span>
          </button>
        </form>
      </div>

      {/* Report Modal */}
      {reportModal.isOpen && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-md w-full p-6">
            <div className="flex items-center gap-3 mb-4">
              <Flag size={24} className="text-orange-600" />
              <h3 className="text-xl font-bold text-dark-navy">신고하기</h3>
            </div>

            <div className="mb-4">
              <p className="text-sm text-gray-600 mb-2">
                {reportModal.type === 'post' ? '게시글' : reportModal.type === 'comment' ? '댓글' : '답글'}을 신고하는 이유를 입력해주세요.
              </p>
              <textarea
                value={reportReason}
                onChange={(e) => setReportReason(e.target.value)}
                placeholder="신고 사유를 구체적으로 작성해주세요."
                className="w-full px-4 py-3 border-2 border-gray-200 rounded-lg outline-none focus:border-orange-500 transition-colors resize-none"
                rows={5}
              />
            </div>

            <div className="flex gap-3">
              <button
                onClick={closeReportModal}
                className="flex-1 px-4 py-3 bg-gray-100 text-gray-700 rounded-lg font-semibold hover:bg-gray-200 transition-all"
              >
                취소
              </button>
              <button
                onClick={handleSubmitReport}
                className="flex-1 px-4 py-3 bg-orange-600 text-white rounded-lg font-semibold hover:bg-orange-700 transition-all"
              >
                신고하기
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
