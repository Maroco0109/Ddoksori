import type { PostFormData } from '@/shared/types';

export type BoardPost = {
  id: number;
  category: string;
  title: string;
  author: string;
  date: string;
  views: number;
  likes: number;
  comments: number;
  preview: string;
  isDeleted?: boolean;
  editedDate?: string;
};

export type BoardCategoryId = 'all' | 'case-sharing' | 'qna' | 'tips';
export type BoardSearchType = 'title' | 'author' | 'content' | 'title_content';
export type BoardPostForm = PostFormData;
