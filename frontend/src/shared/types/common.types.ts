export interface ApiResponse<T> {
  data: T;
  message?: string;
  status: number;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
}

export type SortOrder = 'asc' | 'desc';

export interface BaseEntity {
  id: string | number;
  createdAt: string;
  updatedAt: string;
}
