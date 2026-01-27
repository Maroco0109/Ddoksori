// API Client configuration
// Connected to FastAPI backend at port 8000

import { useAuthStore } from '@/features/auth/auth.store';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Helper to get auth headers
const getAuthHeaders = (): Record<string, string> => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  const token = useAuthStore.getState().token;
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  return headers;
};

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
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      if (response.status === 401) {
        useAuthStore.getState().logout();
      }
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  },

  post: async <T>(endpoint: string, data?: any): Promise<T> => {
    console.log('[API Client] POST', endpoint, data);
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: data ? JSON.stringify(data) : undefined,
    });

    console.log('[API Client] Response status:', response.status);

    if (!response.ok) {
      if (response.status === 401) {
        useAuthStore.getState().logout();
      }
      throw new Error(`API Error: ${response.statusText}`);
    }

    const json = await response.json();
    console.log('[API Client] Response data:', json);
    return json;
  },

  put: async <T>(endpoint: string, data?: any): Promise<T> => {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'PUT',
      headers: getAuthHeaders(),
      body: data ? JSON.stringify(data) : undefined,
    });

    if (!response.ok) {
      if (response.status === 401) {
        useAuthStore.getState().logout();
      }
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  },

  delete: async <T>(endpoint: string): Promise<T> => {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    });

    if (!response.ok) {
      if (response.status === 401) {
        useAuthStore.getState().logout();
      }
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response.json();
  },
};
