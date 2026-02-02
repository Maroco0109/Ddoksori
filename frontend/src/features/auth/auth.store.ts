import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, ChatSession } from '@/shared/types';
import { STORAGE_KEYS } from '@/shared/config/storage-keys';
import { storage } from '@/shared/lib/storage';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  token: string | null;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  login: (user: User, token: string) => void;
  logout: () => void;
}

/**
 * 비로그인 세션을 로그인 사용자 세션으로 이전
 */
const transferGuestSessions = () => {
  const guestSessions = storage.get<ChatSession[]>(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true) || [];

  if (guestSessions.length === 0) return;

  const userSessions = storage.get<ChatSession[]>(STORAGE_KEYS.CHAT_SESSIONS, false) || [];

  // 게스트 세션을 사용자 세션으로 복사 (expiresAt 제거)
  const transferredSessions = guestSessions.map((session) => ({
    ...session,
    expiresAt: null, // 로그인 사용자는 만료 시간 없음
  }));

  // 사용자 세션 목록 맨 앞에 추가
  const mergedSessions = [...transferredSessions, ...userSessions];

  // 저장
  storage.set(STORAGE_KEYS.CHAT_SESSIONS, mergedSessions, false);

  // 게스트 세션 삭제
  storage.remove(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true);
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      token: null,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setToken: (token) => set({ token }),
      login: (user, token) => {
        // 게스트 세션 이전
        transferGuestSessions();
        set({ user, token, isAuthenticated: true });
      },
      logout: () => set({ user: null, token: null, isAuthenticated: false }),
    }),
    {
      name: STORAGE_KEYS.USER_DATA,
    }
  )
);
