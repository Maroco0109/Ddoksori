// API Client configuration
// Connected to FastAPI backend at port 8000

import { useAuthStore } from '@/features/auth/auth.store';
import { useAdminStore } from '@/features/admin/admin.store';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';

function getAuthHeaders(endpoint?: string): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };

  // Admin token은 /api/admin 엔드포인트에만 사용
  if (endpoint?.startsWith('/api/admin')) {
    const adminToken = useAdminStore.getState().adminToken;
    if (adminToken) {
      headers['Authorization'] = `Bearer ${adminToken}`;
      return headers;
    }
  }

  // 일반 사용자 토큰 사용
  // Zustand store에서 먼저 시도
  let userToken = useAuthStore.getState().token;

  // Store에 토큰이 없으면 localStorage에서 직접 읽기 (persist hydration 전 대비)
  if (!userToken) {
    try {
      const stored = localStorage.getItem('userData');
      if (stored) {
        const parsed = JSON.parse(stored);
        userToken = parsed?.state?.token || null;
      }
    } catch {
      // JSON 파싱 실패 시 무시
    }
  }

  if (userToken) {
    headers['Authorization'] = `Bearer ${userToken}`;
  }

  return headers;
}

export const apiClient = {
  get: async <T>(endpoint: string, params?: Record<string, any>): Promise<T> => {
    const url = new URL(`${API_BASE_URL}${endpoint}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          url.searchParams.append(key, String(value));
        }
      });
    }

    const response = await fetch(url.toString(), {
      method: 'GET',
      headers: getAuthHeaders(endpoint),
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  },

  post: async <T>(endpoint: string, data?: any): Promise<T> => {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: getAuthHeaders(endpoint),
      body: data ? JSON.stringify(data) : undefined,
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  },

  put: async <T>(endpoint: string, data?: any): Promise<T> => {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'PUT',
      headers: getAuthHeaders(endpoint),
      body: data ? JSON.stringify(data) : undefined,
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  },

  delete: async <T>(endpoint: string): Promise<T> => {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'DELETE',
      headers: getAuthHeaders(endpoint),
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  },
};
