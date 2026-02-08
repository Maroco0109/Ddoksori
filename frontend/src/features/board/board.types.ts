import type { PostFormData } from '@/shared/types';

// API 응답과 호환되는 타입
export type BoardPost = {
  id: string;
  category: string;
  category_key: string;
  sub_category?: string | null;
  title: string;
  author_id: string;
  author_nickname: string;
  is_author_deleted?: boolean;
  created_at: string;
  edited_at?: string | null;
  view_count: number;
  like_count: number;
  comment_count: number;
  preview?: string | null;
};

// 게시글 상세 (content, is_liked 포함)
export type BoardPostDetail = BoardPost & {
  content: string;
  is_liked: boolean;
};

export type BoardCategoryId = 'all' | 'case-sharing' | 'qna' | 'tips';
export type BoardSearchType = 'title' | 'author' | 'content' | 'title_content';
export type BoardPostForm = PostFormData;

// 댓글 타입
export type BoardReply = {
  id: string;
  content: string;
  author_id: string;
  author_nickname: string;
  is_author_deleted: boolean;
  like_count: number;
  is_liked: boolean;
  created_at: string;
  edited_at: string | null;
};

export type BoardComment = {
  id: string;
  content: string;
  author_id: string;
  author_nickname: string;
  is_author_deleted: boolean;
  like_count: number;
  is_liked: boolean;
  created_at: string;
  edited_at: string | null;
  replies: BoardReply[];
};
