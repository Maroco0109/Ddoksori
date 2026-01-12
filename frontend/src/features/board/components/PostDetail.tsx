import { useState } from 'react';
import type { FormEvent } from 'react';
import type { Comment } from '@/shared/types';
import type { BoardPost } from '../board.types';
import { ArrowLeft, ThumbsUp, Eye, MessageSquare, Send, CornerDownRight, Edit2, Trash2, Flag } from 'lucide-react';

interface PostDetailProps {
  post: BoardPost;
  onBack: () => void;
  onEdit: (post: BoardPost) => void;
  onDelete: (postId: number) => void;
}

export default function PostDetail({ post, onBack, onEdit, onDelete }: PostDetailProps) {
  const currentUser = '현재사용자**'; // 현재 로그인한 사용자
  const isAuthor = post.author === currentUser;

  // 작성자 표시 함수 (탈퇴한 사용자 처리)
  const getAuthorDisplayName = (author: string | undefined, isDeleted = false) => {
    if (isDeleted || !author) {
      return '탈퇴한 사용자';
    }
    return author;
  };

  const [comments, setComments] = useState<Comment[]>([
    {
      id: 1,
      author: '박**',
      content: '정말 유용한 정보네요! 저도 비슷한 경험이 있어서 공감됩니다.',
      date: '2025.12.21',
      likes: 5,
      likedBy: ['user1', 'user2', 'user3', 'user4', 'user5'],
      replies: [
        {
          id: 1,
          author: post.author,
          content: '도움이 되셨다니 기쁩니다!',
          date: '2025.12.21',
          likes: 2,
          likedBy: ['user1', 'user2']
        }
      ]
    },
    {
      id: 2,
      author: '정**',
      content: '혹시 변호사 선임은 하셨나요?',
      date: '2025.12.21',
      likes: 3,
      likedBy: ['user1', 'user3', 'user5'],
      replies: []
    }
  ]);

  const [newComment, setNewComment] = useState('');
  const [replyingTo, setReplyingTo] = useState<number | null>(null);
  const [replyContent, setReplyContent] = useState('');
  const [liked, setLiked] = useState(false);
  const [editingCommentId, setEditingCommentId] = useState<number | null>(null);
  const [editingReplyId, setEditingReplyId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');
  const [reportModal, setReportModal] = useState<{
    isOpen: boolean;
    type: 'post' | 'comment' | 'reply' | '';
    targetId: number | null;
    parentId: number | null;
  }>({ isOpen: false, type: '', targetId: null, parentId: null });
  const [reportReason, setReportReason] = useState('');

  const handleAddComment = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!newComment.trim()) return;

    const comment = {
      id: Date.now(),
      author: '현재사용자**',
      content: newComment,
      date: new Date().toLocaleDateString('ko-KR').replace(/\. /g, '.').slice(0, -1),
      likes: 0,
      likedBy: [],
      replies: []
    };

    setComments([...comments, comment]);
    setNewComment('');
  };

  const handleAddReply = (commentId: number) => {
    if (!replyContent.trim()) return;

    const reply = {
      id: Date.now(),
      author: '현재사용자**',
      content: replyContent,
      date: new Date().toLocaleDateString('ko-KR').replace(/\. /g, '.').slice(0, -1),
      likes: 0,
      likedBy: []
    };

    setComments(comments.map(comment => {
      if (comment.id === commentId) {
        return {
          ...comment,
          replies: [...comment.replies, reply]
        };
      }
      return comment;
    }));

    setReplyContent('');
    setReplyingTo(null);
  };

  const handleLikeComment = (commentId: number, isReply = false, parentId: number | null = null) => {
    if (isReply) {
      setComments(comments.map(comment => {
        if (comment.id === parentId) {
          return {
            ...comment,
            replies: comment.replies.map(reply => {
              if (reply.id === commentId) {
                const hasLiked = reply.likedBy.includes(currentUser);
                return {
                  ...reply,
                  likes: hasLiked ? reply.likes - 1 : reply.likes + 1,
                  likedBy: hasLiked
                    ? reply.likedBy.filter(user => user !== currentUser)
                    : [...reply.likedBy, currentUser]
                };
              }
              return reply;
            })
          };
        }
        return comment;
      }));
    } else {
      setComments(comments.map(comment => {
        if (comment.id === commentId) {
          const hasLiked = comment.likedBy.includes(currentUser);
          return {
            ...comment,
            likes: hasLiked ? comment.likes - 1 : comment.likes + 1,
            likedBy: hasLiked
              ? comment.likedBy.filter(user => user !== currentUser)
              : [...comment.likedBy, currentUser]
          };
        }
        return comment;
      }));
    }
  };

  // 댓글 수정 시작
  const startEditComment = (commentId: number, content: string) => {
    setEditingCommentId(commentId);
    setEditContent(content);
  };

  // 댓글 수정 저장
  const handleEditComment = (commentId: number) => {
    if (!editContent.trim()) return;

    setComments(comments.map(comment =>
      comment.id === commentId
        ? {
            ...comment,
            content: editContent,
            editedDate: new Date().toLocaleDateString('ko-KR').replace(/\. /g, '.').slice(0, -1)
          }
        : comment
    ));

    setEditingCommentId(null);
    setEditContent('');
  };

  // 댓글 삭제
  const handleDeleteComment = (commentId: number) => {
    if (window.confirm('정말 이 댓글을 삭제하시겠습니까?')) {
      setComments(comments.filter(comment => comment.id !== commentId));
    }
  };

  // 대댓글 수정 시작
  const startEditReply = (replyId: number, content: string) => {
    setEditingReplyId(replyId);
    setEditContent(content);
  };

  // 대댓글 수정 저장
  const handleEditReply = (commentId: number, replyId: number) => {
    if (!editContent.trim()) return;

    setComments(comments.map(comment => {
      if (comment.id === commentId) {
        return {
          ...comment,
          replies: comment.replies.map(reply =>
            reply.id === replyId
              ? {
                  ...reply,
                  content: editContent,
                  editedDate: new Date().toLocaleDateString('ko-KR').replace(/\. /g, '.').slice(0, -1)
                }
              : reply
          )
        };
      }
      return comment;
    }));

    setEditingReplyId(null);
    setEditContent('');
  };

  // 대댓글 삭제
  const handleDeleteReply = (commentId: number, replyId: number) => {
    if (window.confirm('정말 이 답글을 삭제하시겠습니까?')) {
      setComments(comments.map(comment => {
        if (comment.id === commentId) {
          return {
            ...comment,
            replies: comment.replies.filter(reply => reply.id !== replyId)
          };
        }
        return comment;
      }));
    }
  };

  const handleDelete = () => {
    if (window.confirm('정말 이 게시글을 삭제하시겠습니까?')) {
      onDelete(post.id);
    }
  };

  // 신고 모달 열기
  const openReportModal = (type: 'post' | 'comment' | 'reply', targetId: number, parentId: number | null = null) => {
    setReportModal({ isOpen: true, type, targetId, parentId });
    setReportReason('');
  };

  // 신고 모달 닫기
  const closeReportModal = () => {
    setReportModal({ isOpen: false, type: '', targetId: null, parentId: null });
    setReportReason('');
  };

  // 신고 제출
  const handleSubmitReport = () => {
    if (!reportReason.trim()) {
      alert('신고 사유를 입력해주세요.');
      return;
    }

    // 여기에 실제 신고 API 호출을 추가할 수 있습니다
    console.log('신고 제출:', {
      type: reportModal.type,
      targetId: reportModal.targetId,
      parentId: reportModal.parentId,
      reason: reportReason
    });

    alert('신고가 접수되었습니다.');
    closeReportModal();
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
                className="flex items-center gap-2 px-4 py-2 bg-red-50 text-red-600 rounded-lg font-medium hover:bg-red-100 transition-all"
              >
                <Trash2 size={16} />
                <span className="hidden sm:inline">삭제</span>
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
          <span className="text-sm text-gray-500">{post.date}</span>
          {post.editedDate && (
            <span className="text-sm text-gray-400">(수정됨: {post.editedDate})</span>
          )}
        </div>

        {/* Title */}
        <h2 className="text-2xl md:text-3xl font-bold text-dark-navy mb-4">{post.title}</h2>

        {/* Author & Stats */}
        <div className="flex items-center gap-4 pb-4 mb-6 border-b border-gray-200">
          <span className="font-semibold text-gray-700">{getAuthorDisplayName(post.author, post.isDeleted)}</span>
          <div className="flex items-center gap-4 text-sm text-gray-500">
            <div className="flex items-center gap-1">
              <Eye size={16} />
              <span>{post.views}</span>
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
            {post.preview}
          </p>
        </div>

        {/* Like Button */}
        <div className="flex justify-center pt-6 border-t border-gray-200">
          <button
            onClick={() => setLiked(!liked)}
            className={`flex items-center gap-2 px-8 py-3 rounded-full font-semibold transition-all ${
              liked
                ? 'bg-deep-teal text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            <ThumbsUp size={20} fill={liked ? 'currentColor' : 'none'} />
            <span>좋아요 {post.likes + (liked ? 1 : 0)}</span>
          </button>
        </div>
      </div>

      {/* Comments Section */}
      <div className="bg-white rounded-2xl shadow-md p-6 md:p-8">
        <h3 className="text-xl font-bold text-dark-navy mb-6 flex items-center gap-2">
          <MessageSquare size={24} />
          댓글 {comments.length}개
        </h3>

        {/* Comment List */}
        <div className="space-y-4 mb-6">
          {comments.map(comment => (
            <div key={comment.id} className="border-b border-gray-100 pb-4 last:border-0">
              {/* Main Comment */}
              <div className="flex gap-3">
                <div className="w-10 h-10 bg-lavender/30 rounded-full flex items-center justify-center flex-shrink-0">
                  <span className="text-sm font-bold text-deep-teal">
                    {comment.author.charAt(0)}
                  </span>
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-gray-800">{getAuthorDisplayName(comment.author, comment.isDeleted)}</span>
                    <span className="text-xs text-gray-500">{comment.date}</span>
                    {comment.editedDate && (
                      <span className="text-xs text-gray-400">(수정됨: {comment.editedDate})</span>
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
                        comment.likedBy.includes(currentUser)
                          ? 'text-deep-teal font-semibold'
                          : 'text-gray-500 hover:text-deep-teal'
                      }`}
                    >
                      <ThumbsUp size={14} fill={comment.likedBy.includes(currentUser) ? 'currentColor' : 'none'} />
                      <span>{comment.likes}</span>
                    </button>
                    <button
                      onClick={() => setReplyingTo(replyingTo === comment.id ? null : comment.id)}
                      className="text-xs text-gray-500 hover:text-deep-teal transition-colors"
                    >
                      답글 달기
                    </button>

                    {/* 본인이 작성한 댓글에만 수정/삭제 버튼 표시 */}
                    {comment.author === currentUser ? (
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
                              <span className="font-semibold text-gray-800 text-sm">{getAuthorDisplayName(reply.author, reply.isDeleted)}</span>
                              <span className="text-xs text-gray-500">{reply.date}</span>
                              {reply.editedDate && (
                                <span className="text-xs text-gray-400">(수정됨: {reply.editedDate})</span>
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
                                      handleEditReply(comment.id, reply.id);
                                    }
                                  }}
                                />
                                <button
                                  onClick={() => handleEditReply(comment.id, reply.id)}
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
                                onClick={() => handleLikeComment(reply.id, true, comment.id)}
                                className={`flex items-center gap-1 text-xs transition-colors ${
                                  reply.likedBy.includes(currentUser)
                                    ? 'text-deep-teal font-semibold'
                                    : 'text-gray-500 hover:text-deep-teal'
                                }`}
                              >
                                <ThumbsUp size={14} fill={reply.likedBy.includes(currentUser) ? 'currentColor' : 'none'} />
                                <span>{reply.likes}</span>
                              </button>

                              {/* 본인이 작성한 대댓글에만 수정/삭제 버튼 표시 */}
                              {reply.author === currentUser ? (
                                <>
                                  <button
                                    onClick={() => startEditReply(reply.id, reply.content)}
                                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-blue-600 transition-colors"
                                  >
                                    <Edit2 size={12} />
                                    수정
                                  </button>
                                  <button
                                    onClick={() => handleDeleteReply(comment.id, reply.id)}
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
