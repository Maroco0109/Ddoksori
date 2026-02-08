/**
 * 게시판 API 서비스
 *
 * 게시글, 댓글, 좋아요, 신고 관련 API 호출을 담당합니다.
 */

import { apiClient } from './client';

// ============================================================
// Types
// ============================================================

export interface Category {
  id: string;
  category_key: string;
  category_name: string;
  display_name: string;
  sort_order: number | null;
}

export interface PostListItem {
  id: string;
  category: string;
  category_key: string;
  sub_category: string | null;
  title: string;
  preview: string | null;
  author_id: string;
  author_nickname: string;
  is_author_deleted: boolean;
  view_count: number;
  like_count: number;
  comment_count: number;
  created_at: string;
  edited_at: string | null;
}

export interface PostDetail {
  id: string;
  category: string;
  category_key: string;
  sub_category: string | null;
  title: string;
  content: string;
  preview: string | null;
  author_id: string;
  author_nickname: string;
  is_author_deleted: boolean;
  view_count: number;
  like_count: number;
  comment_count: number;
  is_liked: boolean;
  created_at: string;
  edited_at: string | null;
}

export interface PostListResponse {
  posts: PostListItem[];
  total: number;
  page: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface PostCreateRequest {
  category: 'case-sharing' | 'qna' | 'tips';
  sub_category?: 'pre-mediation' | 'mediation';
  title: string;
  content: string;
}

export interface PostUpdateRequest {
  category?: 'case-sharing' | 'qna' | 'tips';
  sub_category?: 'pre-mediation' | 'mediation';
  title?: string;
  content?: string;
}

export interface Reply {
  id: string;
  content: string;
  author_id: string;
  author_nickname: string;
  is_author_deleted: boolean;
  like_count: number;
  is_liked: boolean;
  created_at: string;
  edited_at: string | null;
}

export interface Comment {
  id: string;
  content: string;
  author_id: string;
  author_nickname: string;
  is_author_deleted: boolean;
  like_count: number;
  is_liked: boolean;
  created_at: string;
  edited_at: string | null;
  replies: Reply[];
}

export interface CommentListResponse {
  comments: Comment[];
  total: number;
}

export interface LikeResponse {
  liked: boolean;
  like_count: number;
}

export interface ReportResponse {
  id: string;
  message: string;
}

// ============================================================
// API Service
// ============================================================

export const boardService = {
  // Categories
  getCategories: async (): Promise<Category[]> => {
    return apiClient.get<Category[]>('/api/board/categories');
  },

  // Posts
  getPosts: async (params?: {
    page?: number;
    limit?: number;
    category?: string;
    search?: string;
    search_type?: string;
  }): Promise<PostListResponse> => {
    return apiClient.get<PostListResponse>('/api/board/posts', params);
  },

  getPost: async (postId: string): Promise<PostDetail> => {
    return apiClient.get<PostDetail>(`/api/board/posts/${postId}`);
  },

  createPost: async (data: PostCreateRequest): Promise<PostDetail> => {
    return apiClient.post<PostDetail>('/api/board/posts', data);
  },

  updatePost: async (postId: string, data: PostUpdateRequest): Promise<{ success: boolean; message: string }> => {
    return apiClient.put<{ success: boolean; message: string }>(`/api/board/posts/${postId}`, data);
  },

  deletePost: async (postId: string): Promise<{ success: boolean; message: string }> => {
    return apiClient.delete<{ success: boolean; message: string }>(`/api/board/posts/${postId}`);
  },

  togglePostLike: async (postId: string): Promise<LikeResponse> => {
    return apiClient.post<LikeResponse>(`/api/board/posts/${postId}/like`);
  },

  reportPost: async (postId: string, reason: string): Promise<ReportResponse> => {
    return apiClient.post<ReportResponse>(`/api/board/posts/${postId}/report`, { reason });
  },

  // Comments
  getComments: async (postId: string): Promise<CommentListResponse> => {
    return apiClient.get<CommentListResponse>(`/api/board/posts/${postId}/comments`);
  },

  createComment: async (postId: string, content: string): Promise<{ success: boolean; comment_id: string }> => {
    return apiClient.post<{ success: boolean; comment_id: string }>(`/api/board/posts/${postId}/comments`, { content });
  },

  updateComment: async (commentId: string, content: string): Promise<{ success: boolean; message: string }> => {
    return apiClient.put<{ success: boolean; message: string }>(`/api/board/comments/${commentId}`, { content });
  },

  deleteComment: async (commentId: string): Promise<{ success: boolean; message: string }> => {
    return apiClient.delete<{ success: boolean; message: string }>(`/api/board/comments/${commentId}`);
  },

  toggleCommentLike: async (commentId: string): Promise<LikeResponse> => {
    return apiClient.post<LikeResponse>(`/api/board/comments/${commentId}/like`);
  },

  reportComment: async (commentId: string, reason: string): Promise<ReportResponse> => {
    return apiClient.post<ReportResponse>(`/api/board/comments/${commentId}/report`, { reason });
  },

  // Replies
  createReply: async (commentId: string, content: string): Promise<{ success: boolean; comment_id: string }> => {
    return apiClient.post<{ success: boolean; comment_id: string }>(`/api/board/comments/${commentId}/replies`, { content });
  },
};

// ============================================================
// MyPage API Types & Service
// ============================================================

export interface MyPostItem {
  id: string;
  category: string;
  category_key: string;
  title: string;
  date: string;
  views: number;
  likes: number;
  comments: number;
}

export interface MyPostsResponse {
  posts: MyPostItem[];
  total: number;
  page: number;
  total_pages: number;
}

export interface MyCommentedPostItem {
  id: string;
  category: string;
  category_key: string;
  title: string;
  date: string;
  views: number;
  likes: number;
  comments: number;
  my_comment_date: string;
  my_comment_preview: string | null;
}

export interface MyCommentedPostsResponse {
  posts: MyCommentedPostItem[];
  total: number;
  page: number;
  total_pages: number;
}

export const myPageService = {
  getMyPosts: async (page: number = 1, limit: number = 10): Promise<MyPostsResponse> => {
    return apiClient.get<MyPostsResponse>('/api/users/me/posts', { page, limit });
  },

  getMyCommentedPosts: async (page: number = 1, limit: number = 10): Promise<MyCommentedPostsResponse> => {
    return apiClient.get<MyCommentedPostsResponse>('/api/users/me/commented-posts', { page, limit });
  },
};
