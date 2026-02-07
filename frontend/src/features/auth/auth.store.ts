import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, ChatSession } from '@/shared/types';
import { STORAGE_KEYS, getUserChatSessionsKey } from '@/shared/config/storage-keys';
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
 * @param userId - 로그인한 사용자 ID
 */
const transferGuestSessions = (userId: string) => {
  const guestSessions = storage.get<ChatSession[]>(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true) || [];

  if (guestSessions.length === 0) return;

  // 사용자별 storage key 사용
  const userStorageKey = getUserChatSessionsKey(userId);
  const userSessions = storage.get<ChatSession[]>(userStorageKey, false) || [];

  // 게스트 세션을 사용자 세션으로 복사 (expiresAt 제거)
  const transferredSessions = guestSessions.map((session) => ({
    ...session,
    expiresAt: null, // 로그인 사용자는 만료 시간 없음
  }));

  // 사용자 세션 목록 맨 앞에 추가
  const mergedSessions = [...transferredSessions, ...userSessions];

  // 사용자별 key에 저장
  storage.set(userStorageKey, mergedSessions, false);

  // 게스트 세션 삭제
  storage.remove(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true);

  console.log(`[Auth] Transferred ${guestSessions.length} guest sessions to user ${userId}`);
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
        // 게스트 세션을 현재 사용자의 세션으로 이전
        transferGuestSessions(user.id);
        set({ user, token, isAuthenticated: true });
      },
      logout: () => {
        // 사용자별 storage key를 사용하므로 데이터 삭제 불필요
        // 각 사용자의 채팅 데이터는 localStorage에 보존됨
        set({ user: null, token: null, isAuthenticated: false });
      },
    }),
    {
      name: STORAGE_KEYS.USER_DATA,
    }
  )
);
