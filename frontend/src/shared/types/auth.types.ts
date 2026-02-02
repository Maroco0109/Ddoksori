export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  provider: 'google' | 'naver';
}

export interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  token: string | null;
}

export interface LoginCredentials {
  provider: 'google' | 'naver';
  token: string;
}

export interface AuthResponse {
  user: User;
  token: string;
}
