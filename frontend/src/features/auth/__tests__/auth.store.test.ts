import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useAuthStore } from '../auth.store';
import type { User } from '@/shared/types';
import { storage } from '@/shared/lib/storage';
import { STORAGE_KEYS } from '@/shared/config/storage-keys';

// Mock storage module
vi.mock('@/shared/lib/storage', () => ({
  storage: {
    get: vi.fn(),
    set: vi.fn(),
    remove: vi.fn(),
  },
}));

describe('Auth Store', () => {
  beforeEach(() => {
    // Reset store state before each test
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      token: null,
    });
    // Clear all mocks
    vi.clearAllMocks();
  });

  it('should start with null user and unauthenticated state', () => {
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
    expect(state.token).toBeNull();
  });

  describe('login', () => {
    it('should login user with token', () => {
      const user: User = {
        id: '1',
        name: 'Test User',
        email: 'test@test.com',
        provider: 'google',
      };

      // Mock storage.get to return empty arrays (no guest sessions)
      vi.mocked(storage.get).mockReturnValue([]);

      useAuthStore.getState().login(user, 'test-token');

      const state = useAuthStore.getState();
      expect(state.user).toEqual(user);
      expect(state.isAuthenticated).toBe(true);
      expect(state.token).toBe('test-token');
    });

    it('should transfer guest sessions on login', () => {
      const user: User = {
        id: '1',
        name: 'Test User',
        email: 'test@test.com',
        provider: 'naver',
      };

      const guestSessions = [
        {
          id: 'guest-1',
          type: 'general' as const,
          title: 'Guest Session',
          messages: [],
          createdAt: Date.now(),
          expiresAt: Date.now() + 3600000,
        },
      ];

      const userSessions = [
        {
          id: 'user-1',
          type: 'dispute' as const,
          title: 'User Session',
          messages: [],
          createdAt: Date.now(),
          expiresAt: null,
        },
      ];

      // Mock storage behavior
      vi.mocked(storage.get).mockImplementation((key: string) => {
        if (key === STORAGE_KEYS.TEMP_CHAT_SESSIONS) {
          return guestSessions;
        }
        if (key === STORAGE_KEYS.CHAT_SESSIONS) {
          return userSessions;
        }
        return null;
      });

      useAuthStore.getState().login(user, 'test-token');

      // Verify guest sessions were transferred
      expect(storage.set).toHaveBeenCalledWith(
        STORAGE_KEYS.CHAT_SESSIONS,
        expect.arrayContaining([
          expect.objectContaining({ id: 'guest-1', expiresAt: null }),
          expect.objectContaining({ id: 'user-1' }),
        ]),
        false
      );

      // Verify guest sessions were removed
      expect(storage.remove).toHaveBeenCalledWith(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true);
    });
  });

  describe('logout', () => {
    it('should logout user and clear state', () => {
      const user: User = {
        id: '1',
        name: 'Test User',
        email: 'test@test.com',
        provider: 'google',
      };

      // Mock storage.get to return empty arrays
      vi.mocked(storage.get).mockReturnValue([]);

      useAuthStore.getState().login(user, 'test-token');
      useAuthStore.getState().logout();

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.token).toBeNull();
    });

    it('should handle logout when already logged out', () => {
      useAuthStore.getState().logout();

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.token).toBeNull();
    });
  });

  describe('setUser', () => {
    it('should set user and update authentication status', () => {
      const user: User = {
        id: '1',
        name: 'Test User',
        email: 'test@test.com',
        provider: 'google',
      };
      useAuthStore.getState().setUser(user);

      const state = useAuthStore.getState();
      expect(state.user).toEqual(user);
      expect(state.isAuthenticated).toBe(true);
    });

    it('should clear user when set to null', () => {
      const user: User = {
        id: '1',
        name: 'Test User',
        email: 'test@test.com',
        provider: 'google',
      };
      useAuthStore.getState().setUser(user);
      useAuthStore.getState().setUser(null);

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });
  });

  describe('setToken', () => {
    it('should set token', () => {
      useAuthStore.getState().setToken('new-token');

      const state = useAuthStore.getState();
      expect(state.token).toBe('new-token');
    });

    it('should clear token when set to null', () => {
      useAuthStore.getState().setToken('test-token');
      useAuthStore.getState().setToken(null);

      const state = useAuthStore.getState();
      expect(state.token).toBeNull();
    });
  });
});
