export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  provider: 'google' | 'kakao' | 'naver';
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  token: string | null;
}

export interface LoginCredentials {
  provider: 'google' | 'kakao' | 'naver';
  token: string;
}

export interface AuthResponse {
  user: User;
  token: string;
}
