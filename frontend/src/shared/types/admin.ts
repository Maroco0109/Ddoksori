export interface Admin {
  id: string;
  username: string;
  email: string;
  role: 'admin' | 'super_admin';
}

export interface AdminLoginCredentials {
  username: string;
  password: string;
}

export interface AdminAuthResponse {
  admin: Admin;
  token: string;
}

export interface AdminAuthState {
  admin: Admin | null;
  isAdminAuthenticated: boolean;
  adminToken: string | null;
}

// 게시글 관리 관련 타입
export interface AdminPost {
  id: number;
  category: string;
  title: string;
  content: string;
  author: string;
  authorId: string;
  createdAt: string;
  updatedAt?: string;
  views: number;
  likes: number;
  commentsCount: number;
  isPublic: boolean;
  isDeleted: boolean;
}

export interface AdminComment {
  id: number;
  postId: number;
  content: string;
  author: string;
  authorId: string;
  createdAt: string;
  updatedAt?: string;
  isPublic: boolean;
  isDeleted: boolean;
}

// 회원 관리 관련 타입
export interface AdminUser {
  id: string;
  name: string;
  email: string;
  provider: 'google' | 'naver';
  createdAt: string;
  lastLoginAt: string;
  status: 'active' | 'suspended' | 'banned';
  postCount: number;
  commentCount: number;
  reportCount: number;
}

// 신고 관리 관련 타입
export interface Report {
  id: number;
  type: 'post' | 'comment';
  targetId: number;
  targetTitle?: string;
  targetContent: string;
  reporterId: string;
  reporterName: string;
  reason: string;
  createdAt: string;
  status: 'pending' | 'reviewed' | 'resolved' | 'rejected';
  adminNote?: string;
}

// 검색 및 필터링 타입
export interface PostSearchParams {
  searchType?: 'title' | 'author' | 'title_author' | 'keyword';
  searchKeyword?: string;
  category?: string;
  isPublic?: boolean;
  page?: number;
  limit?: number;
}

export interface UserSearchParams {
  searchKeyword?: string;
  status?: 'active' | 'suspended' | 'banned';
  provider?: 'google' | 'naver';
  page?: number;
  limit?: number;
}

export interface ReportSearchParams {
  type?: 'post' | 'comment';
  status?: 'pending' | 'reviewed' | 'resolved' | 'rejected';
  page?: number;
  limit?: number;
}

// 공지글 타입
export interface NoticePost {
  title: string;
  content: string;
  isPinned: boolean;
}

// 통계 데이터 타입
export interface AdminStats {
  totalUsers: number;
  totalPosts: number;
  totalComments: number;
  pendingReports: number;
  suspendedUsers: number;
  todayNewUsers: number;
  todayNewPosts: number;
  todayNewComments: number;
}
