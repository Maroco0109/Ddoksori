import { BaseEntity } from './common.types';

export type PostCategory = 'case-sharing' | 'qna' | 'tips';

export interface Post extends BaseEntity {
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
}

export interface Comment {
  id: number;
  author: string;
  content: string;
  date: string;
  likes: number;
  likedBy: string[];
  replies: Reply[];
  isDeleted?: boolean;
  editedDate?: string;
}

export interface Reply {
  id: number;
  author: string;
  content: string;
  date: string;
  likes: number;
  likedBy: string[];
  isDeleted?: boolean;
  editedDate?: string;
}

export interface PostFormData {
  category: PostCategory;
  title: string;
  content: string;
}

export interface PostFilters {
  category?: PostCategory | 'all';
  search?: string;
  searchType?: 'title' | 'author' | 'content' | 'title_content';
  page?: number;
  limit?: number;
  sortBy?: 'latest' | 'popular' | 'views';
}

export interface CreatePostDto {
  category: PostCategory;
  title: string;
  content: string;
}

export interface UpdatePostDto {
  category?: PostCategory;
  title?: string;
  content?: string;
}
