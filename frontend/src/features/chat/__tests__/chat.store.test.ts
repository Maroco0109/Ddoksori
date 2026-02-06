import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useChatStore } from '../chat.store';
import type { ChatSession, MessageWithCitations, DisputeFormData } from '@/shared/types';
import { storage } from '@/shared/lib/storage';
import { STORAGE_KEYS } from '@/shared/config/storage-keys';
import { generateGuestSessionId } from '@/shared/lib/session';

// Mock storage module
vi.mock('@/shared/lib/storage', () => ({
  storage: {
    get: vi.fn(),
    set: vi.fn(),
    remove: vi.fn(),
    clear: vi.fn(),
  },
}));

// Mock session module
vi.mock('@/shared/lib/session', () => ({
  generateGuestSessionId: vi.fn(),
  formatTimeRemaining: vi.fn(),
}));

describe('Chat Store', () => {
  const initialMessages: MessageWithCitations[] = [
    {
      id: 1,
      type: 'ai',
      content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
      timestamp: new Date(),
    },
  ];

  beforeEach(() => {
    // Reset store state before each test
    useChatStore.setState({
      currentSessionId: null,
      activeChatType: null,
      chatSessions: [],
      disputeMessages: [...initialMessages],
      generalMessages: [...initialMessages],
      isDisputeLoading: false,
      isGeneralLoading: false,
      isFormSubmitted: false,
      backendSessionId: null,
      disputeFormData: null,
    });
    // Clear all mocks
    vi.clearAllMocks();
  });

  it('should start with initial state', () => {
    const state = useChatStore.getState();
    expect(state.currentSessionId).toBeNull();
    expect(state.activeChatType).toBeNull();
    expect(state.chatSessions).toEqual([]);
    expect(state.disputeMessages).toHaveLength(1);
    expect(state.generalMessages).toHaveLength(1);
    expect(state.isDisputeLoading).toBe(false);
    expect(state.isGeneralLoading).toBe(false);
    expect(state.isFormSubmitted).toBe(false);
    expect(state.backendSessionId).toBeNull();
    expect(state.disputeFormData).toBeNull();
  });

  describe('setActiveChatType', () => {
    it('should set active chat type to dispute', () => {
      useChatStore.getState().setActiveChatType('dispute');

      const state = useChatStore.getState();
      expect(state.activeChatType).toBe('dispute');
    });

    it('should set active chat type to general', () => {
      useChatStore.getState().setActiveChatType('general');

      const state = useChatStore.getState();
      expect(state.activeChatType).toBe('general');
    });

    it('should clear active chat type when set to null', () => {
      useChatStore.getState().setActiveChatType('dispute');
      useChatStore.getState().setActiveChatType(null);

      const state = useChatStore.getState();
      expect(state.activeChatType).toBeNull();
    });
  });

  describe('setCurrentSessionId', () => {
    it('should set current session id', () => {
      useChatStore.getState().setCurrentSessionId('session-123');

      const state = useChatStore.getState();
      expect(state.currentSessionId).toBe('session-123');
    });

    it('should clear session id when set to null', () => {
      useChatStore.getState().setCurrentSessionId('session-123');
      useChatStore.getState().setCurrentSessionId(null);

      const state = useChatStore.getState();
      expect(state.currentSessionId).toBeNull();
    });
  });

  describe('message management', () => {
    it('should set dispute messages', () => {
      const messages: MessageWithCitations[] = [
        { id: 1, type: 'user', content: 'Test message', timestamp: new Date() },
        { id: 2, type: 'ai', content: 'Test response', timestamp: new Date() },
      ];

      useChatStore.getState().setDisputeMessages(messages);

      const state = useChatStore.getState();
      expect(state.disputeMessages).toEqual(messages);
    });

    it('should set general messages', () => {
      const messages: MessageWithCitations[] = [
        { id: 1, type: 'user', content: 'Test message', timestamp: new Date() },
        { id: 2, type: 'ai', content: 'Test response', timestamp: new Date() },
      ];

      useChatStore.getState().setGeneralMessages(messages);

      const state = useChatStore.getState();
      expect(state.generalMessages).toEqual(messages);
    });
  });

  describe('loading states', () => {
    it('should set dispute loading state', () => {
      useChatStore.getState().setIsDisputeLoading(true);
      expect(useChatStore.getState().isDisputeLoading).toBe(true);

      useChatStore.getState().setIsDisputeLoading(false);
      expect(useChatStore.getState().isDisputeLoading).toBe(false);
    });

    it('should set general loading state', () => {
      useChatStore.getState().setIsGeneralLoading(true);
      expect(useChatStore.getState().isGeneralLoading).toBe(true);

      useChatStore.getState().setIsGeneralLoading(false);
      expect(useChatStore.getState().isGeneralLoading).toBe(false);
    });
  });

  describe('form submission state', () => {
    it('should set form submitted state', () => {
      useChatStore.getState().setIsFormSubmitted(true);
      expect(useChatStore.getState().isFormSubmitted).toBe(true);

      useChatStore.getState().setIsFormSubmitted(false);
      expect(useChatStore.getState().isFormSubmitted).toBe(false);
    });
  });

  describe('backend session management', () => {
    it('should set backend session id', () => {
      useChatStore.getState().setBackendSessionId('backend-session-123');
      expect(useChatStore.getState().backendSessionId).toBe('backend-session-123');
    });

    it('should clear backend session id', () => {
      useChatStore.getState().setBackendSessionId('backend-session-123');
      useChatStore.getState().setBackendSessionId(null);
      expect(useChatStore.getState().backendSessionId).toBeNull();
    });
  });

  describe('dispute form data', () => {
    it('should set dispute form data', () => {
      const formData: DisputeFormData = {
        purchaseDate: '2024-01-01',
        purchasePlace: 'Test Store',
        purchasePlatform: 'Online',
        purchaseItem: 'Test Item',
        purchaseAmount: '10000',
        disputeDetails: 'Test details',
      };

      useChatStore.getState().setDisputeFormData(formData);
      expect(useChatStore.getState().disputeFormData).toEqual(formData);
    });

    it('should clear dispute form data', () => {
      const formData: DisputeFormData = {
        purchaseDate: '2024-01-01',
        purchasePlace: 'Test Store',
        purchasePlatform: 'Online',
        purchaseItem: 'Test Item',
        purchaseAmount: '10000',
        disputeDetails: 'Test details',
      };

      useChatStore.getState().setDisputeFormData(formData);
      useChatStore.getState().setDisputeFormData(null);
      expect(useChatStore.getState().disputeFormData).toBeNull();
    });
  });

  describe('loadChatSessions', () => {
    it('should load sessions for logged-in user', () => {
      const sessions: ChatSession[] = [
        {
          id: 'session-1',
          type: 'dispute',
          title: 'Dispute Session',
          messages: [],
          createdAt: Date.now(),
          expiresAt: null,
        },
      ];

      vi.mocked(storage.get).mockReturnValue(sessions);

      useChatStore.getState().loadChatSessions(true);

      expect(storage.get).toHaveBeenCalledWith(STORAGE_KEYS.CHAT_SESSIONS, false);
      expect(useChatStore.getState().chatSessions).toEqual(sessions);
    });

    it('should load and filter expired sessions for non-logged-in user', () => {
      const now = Date.now();
      const sessions: ChatSession[] = [
        {
          id: 'session-1',
          type: 'general',
          title: 'Valid Session',
          messages: [],
          createdAt: now,
          expiresAt: now + 3600000, // Valid
        },
        {
          id: 'session-2',
          type: 'general',
          title: 'Expired Session',
          messages: [],
          createdAt: now - 7200000,
          expiresAt: now - 3600000, // Expired
        },
      ];

      vi.mocked(storage.get).mockReturnValue(sessions);

      useChatStore.getState().loadChatSessions(false);

      expect(storage.get).toHaveBeenCalledWith(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true);
      expect(storage.set).toHaveBeenCalled();
      expect(useChatStore.getState().chatSessions).toHaveLength(1);
      expect(useChatStore.getState().chatSessions[0].id).toBe('session-1');
    });
  });

  describe('saveChatSession', () => {
    it('should save chat session for logged-in user', async () => {
      const messages: MessageWithCitations[] = [
        { id: 1, type: 'user', content: 'Test message', timestamp: new Date() },
        { id: 2, type: 'ai', content: 'Test response', timestamp: new Date() },
      ];

      vi.mocked(storage.get).mockReturnValue([]);
      useChatStore.getState().setCurrentSessionId('session-123');

      await useChatStore.getState().saveChatSession('dispute', messages, true);

      expect(storage.set).toHaveBeenCalledWith(
        STORAGE_KEYS.CHAT_SESSIONS,
        expect.arrayContaining([
          expect.objectContaining({
            id: 'session-123',
            type: 'dispute',
            expiresAt: null,
          }),
        ]),
        false
      );
    });

    it('should save single session for non-logged-in user', async () => {
      const messages: MessageWithCitations[] = [
        { id: 1, type: 'user', content: 'Test message', timestamp: new Date() },
      ];

      vi.mocked(storage.get).mockReturnValue([]);
      vi.mocked(generateGuestSessionId).mockResolvedValue('guest-123');

      await useChatStore.getState().saveChatSession('general', messages, false);

      expect(generateGuestSessionId).toHaveBeenCalled();
      expect(storage.set).toHaveBeenCalledWith(
        STORAGE_KEYS.TEMP_CHAT_SESSIONS,
        expect.arrayContaining([
          expect.objectContaining({
            id: 'guest-123',
            type: 'general',
            expiresAt: expect.any(Number),
          }),
        ]),
        true
      );
    });

    it('should generate title from user message', async () => {
      const messages: MessageWithCitations[] = [
        { id: 1, type: 'user', content: 'This is a long test message that should be truncated', timestamp: new Date() },
      ];

      vi.mocked(storage.get).mockReturnValue([]);

      await useChatStore.getState().saveChatSession('dispute', messages, true);

      expect(storage.set).toHaveBeenCalledWith(
        STORAGE_KEYS.CHAT_SESSIONS,
        expect.arrayContaining([
          expect.objectContaining({
            title: expect.stringContaining('This is a long test message'),
          }),
        ]),
        false
      );
    });
  });

  describe('deleteChatSession', () => {
    it('should delete chat session for logged-in user', () => {
      const sessions: ChatSession[] = [
        {
          id: 'session-1',
          type: 'dispute',
          title: 'Session 1',
          messages: [],
          createdAt: Date.now(),
        },
        {
          id: 'session-2',
          type: 'general',
          title: 'Session 2',
          messages: [],
          createdAt: Date.now(),
        },
      ];

      vi.mocked(storage.get).mockReturnValue(sessions);

      useChatStore.getState().deleteChatSession('session-1', true);

      expect(storage.set).toHaveBeenCalledWith(
        STORAGE_KEYS.CHAT_SESSIONS,
        expect.arrayContaining([
          expect.objectContaining({ id: 'session-2' }),
        ]),
        false
      );
    });

    it('should clear current session id if deleted session is active', () => {
      const sessions: ChatSession[] = [
        {
          id: 'session-1',
          type: 'dispute',
          title: 'Session 1',
          messages: [],
          createdAt: Date.now(),
        },
      ];

      vi.mocked(storage.get).mockReturnValue(sessions);
      useChatStore.getState().setCurrentSessionId('session-1');

      useChatStore.getState().deleteChatSession('session-1', true);

      expect(useChatStore.getState().currentSessionId).toBeNull();
    });

    it('should keep current session id if different session is deleted', () => {
      const sessions: ChatSession[] = [
        {
          id: 'session-1',
          type: 'dispute',
          title: 'Session 1',
          messages: [],
          createdAt: Date.now(),
        },
        {
          id: 'session-2',
          type: 'general',
          title: 'Session 2',
          messages: [],
          createdAt: Date.now(),
        },
      ];

      vi.mocked(storage.get).mockReturnValue(sessions);
      useChatStore.getState().setCurrentSessionId('session-2');

      useChatStore.getState().deleteChatSession('session-1', true);

      expect(useChatStore.getState().currentSessionId).toBe('session-2');
    });
  });

  describe('refreshSessionTime', () => {
    it('should refresh session expiry time', () => {
      const now = Date.now();
      const sessions: ChatSession[] = [
        {
          id: 'session-1',
          type: 'general',
          title: 'Session 1',
          messages: [],
          createdAt: now,
          expiresAt: now + 3600000,
          lastUpdated: now,
        },
      ];

      vi.mocked(storage.get).mockReturnValue(sessions);

      useChatStore.getState().refreshSessionTime('session-1');

      expect(storage.set).toHaveBeenCalledWith(
        STORAGE_KEYS.TEMP_CHAT_SESSIONS,
        expect.arrayContaining([
          expect.objectContaining({
            id: 'session-1',
            expiresAt: expect.any(Number),
            lastUpdated: expect.any(Number),
          }),
        ]),
        true
      );
    });
  });

  describe('startNewChat', () => {
    it('should reset chat state', () => {
      // Set up some state
      useChatStore.getState().setCurrentSessionId('session-123');
      useChatStore.getState().setActiveChatType('dispute');
      useChatStore.getState().setIsFormSubmitted(true);
      useChatStore.getState().setBackendSessionId('backend-123');
      useChatStore.getState().setDisputeFormData({
        purchaseDate: '2024-01-01',
        purchasePlace: 'Test Store',
        purchasePlatform: 'Online',
        purchaseItem: 'Test Item',
        purchaseAmount: '10000',
        disputeDetails: 'Test details',
      });

      // Start new chat
      useChatStore.getState().startNewChat();

      // Verify state is reset
      const state = useChatStore.getState();
      expect(state.currentSessionId).toBeNull();
      expect(state.activeChatType).toBeNull();
      expect(state.isFormSubmitted).toBe(false);
      expect(state.backendSessionId).toBeNull();
      expect(state.disputeFormData).toBeNull();
      expect(state.disputeMessages).toHaveLength(1);
      expect(state.generalMessages).toHaveLength(1);
    });
  });

  describe('setChatSessions', () => {
    it('should set chat sessions', () => {
      const sessions: ChatSession[] = [
        {
          id: 'session-1',
          type: 'dispute',
          title: 'Session 1',
          messages: [],
          createdAt: Date.now(),
        },
        {
          id: 'session-2',
          type: 'general',
          title: 'Session 2',
          messages: [],
          createdAt: Date.now(),
        },
      ];

      useChatStore.getState().setChatSessions(sessions);

      expect(useChatStore.getState().chatSessions).toEqual(sessions);
    });
  });
});
