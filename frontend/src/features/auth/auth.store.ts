import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, ChatSession } from '@/shared/types';
import { STORAGE_KEYS, getUserChatSessionsKey } from '@/shared/config/storage-keys';
import { storage } from '@/shared/lib/storage';
import { claimGuestSessions } from '@/shared/lib/api-client';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  token: string | null;
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  login: (user: User, token: string) => Promise<void>;
  logout: () => void;
}

/**
 * 비로그인 세션을 로그인 사용자 세션으로 이전
 * 백엔드 API를 호출하여 DB 레벨에서 소유권을 이전하고,
 * localStorage도 함께 업데이트합니다.
 */
const transferGuestSessions = async (userId: string, token: string) => {
  const guestSessions = storage.get<ChatSession[]>(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true) || [];

  if (guestSessions.length === 0) return;

  // 1. 백엔드에 게스트 세션 소유권 이전 요청
  const backendSessionIds = guestSessions
    .map(s => s.id)
    .filter(Boolean);

  if (backendSessionIds.length > 0) {
    try {
      await claimGuestSessions(token, backendSessionIds);
      console.log(`[Auth] Claimed ${backendSessionIds.length} guest sessions on backend`);
    } catch (error) {
      console.error('[Auth] Failed to claim guest sessions on backend:', error);
      // 백엔드 실패해도 로컬 이전은 계속 진행 (graceful degradation)
    }
  }

  // 2. 기존 localStorage 이전 로직 (로컬 캐시)
  const userStorageKey = getUserChatSessionsKey(userId);
  const userSessions = storage.get<ChatSession[]>(userStorageKey, false) || [];

  const transferredSessions = guestSessions.map((session) => ({
    ...session,
    expiresAt: null,
  }));

  const mergedSessions = [...transferredSessions, ...userSessions];
  storage.set(userStorageKey, mergedSessions, false);

  // 3. 게스트 세션 삭제
  storage.remove(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true);

  console.log(`[Auth] Transferred ${guestSessions.length} guest sessions to user ${userId}`);
};

// Auth hydration 상태 추적 (F5 새로고침 시 race condition 방지)
let _isAuthHydrated = false;
export const isAuthHydrated = () => _isAuthHydrated;
export const resetAuthHydration = () => { _isAuthHydrated = false; };

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      token: null,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setToken: (token) => set({ token }),
      login: async (user, token) => {
        // 먼저 상태 설정 (getCurrentUserId가 작동하도록)
        set({ user, token, isAuthenticated: true });
        // 그 다음 게스트 세션 이전 (백엔드 API 호출 포함)
        await transferGuestSessions(user.id, token);
      },
      logout: () => {
        // auth 상태만 초기화 (chatStore는 RootLayout에서 처리 — 순환 참조 방지)
        set({ user: null, token: null, isAuthenticated: false });
      },
    }),
    {
      name: STORAGE_KEYS.USER_DATA,
      onRehydrateStorage: () => {
        return () => {
          _isAuthHydrated = true;
        };
      },
    }
  )
);
