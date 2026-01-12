import { create } from 'zustand';
import type { ChatSession, MessageWithCitations, ChatType } from '@/shared/types';
import { storage } from '@/shared/lib/storage';
import { STORAGE_KEYS } from '@/shared/config/storage-keys';
import { SESSION_EXPIRY_DURATION } from '@/shared/config';
import { generateGuestSessionId } from '@/shared/lib/session';

interface ChatState {
  currentSessionId: string | null;
  activeChatType: ChatType | null;
  chatSessions: ChatSession[];
  disputeMessages: MessageWithCitations[];
  generalMessages: MessageWithCitations[];
  isDisputeLoading: boolean;
  isGeneralLoading: boolean;
  isFormSubmitted: boolean;

  // Actions
  setCurrentSessionId: (id: string | null) => void;
  setActiveChatType: (type: ChatType | null) => void;
  setChatSessions: (sessions: ChatSession[]) => void;
  setDisputeMessages: (messages: MessageWithCitations[]) => void;
  setGeneralMessages: (messages: MessageWithCitations[]) => void;
  setIsDisputeLoading: (loading: boolean) => void;
  setIsGeneralLoading: (loading: boolean) => void;
  setIsFormSubmitted: (submitted: boolean) => void;

  loadChatSessions: (isLoggedIn: boolean) => void;
  saveChatSession: (type: ChatType, messages: MessageWithCitations[], isLoggedIn: boolean) => void;
  deleteChatSession: (sessionId: string, isLoggedIn: boolean) => void;
  refreshSessionTime: (sessionId: string) => void;
  startNewChat: () => void;
}

const initialMessages: MessageWithCitations[] = [
  {
    id: 1,
    type: 'ai',
    content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
    timestamp: new Date(),
  },
];

export const useChatStore = create<ChatState>((set, get) => ({
  currentSessionId: null,
  activeChatType: null,
  chatSessions: [],
  disputeMessages: [...initialMessages],
  generalMessages: [...initialMessages],
  isDisputeLoading: false,
  isGeneralLoading: false,
  isFormSubmitted: false,

  setCurrentSessionId: (id) => set({ currentSessionId: id }),
  setActiveChatType: (type) => set({ activeChatType: type }),
  setChatSessions: (sessions) => set({ chatSessions: sessions }),
  setDisputeMessages: (messages) => set({ disputeMessages: messages }),
  setGeneralMessages: (messages) => set({ generalMessages: messages }),
  setIsDisputeLoading: (loading) => set({ isDisputeLoading: loading }),
  setIsGeneralLoading: (loading) => set({ isGeneralLoading: loading }),
  setIsFormSubmitted: (submitted) => set({ isFormSubmitted: submitted }),

  loadChatSessions: (isLoggedIn) => {
    const storageKey = isLoggedIn
      ? STORAGE_KEYS.CHAT_SESSIONS
      : STORAGE_KEYS.TEMP_CHAT_SESSIONS;
    let sessions = storage.get<ChatSession[]>(storageKey, !isLoggedIn) || [];

    // Filter expired sessions for non-logged-in users
    if (!isLoggedIn) {
      const now = Date.now();
      sessions = sessions.filter((s) => !s.expiresAt || s.expiresAt > now);
      storage.set(storageKey, sessions, true);
    }

    set({ chatSessions: sessions });
  },

  saveChatSession: async (type, messages, isLoggedIn) => {
    const state = get();
    const storageKey = isLoggedIn
      ? STORAGE_KEYS.CHAT_SESSIONS
      : STORAGE_KEYS.TEMP_CHAT_SESSIONS;

    let sessions = storage.get<ChatSession[]>(storageKey, !isLoggedIn) || [];

    // 비로그인 사용자는 최대 1개의 세션만 유지
    let newSessionId = state.currentSessionId;
    if (!isLoggedIn) {
      if (sessions.length > 0 && !newSessionId) {
        // 기존 세션이 있으면 재사용
        newSessionId = sessions[0].id;
      } else if (!newSessionId) {
        // 새 게스트 세션 ID 생성
        newSessionId = await generateGuestSessionId();
      }
      // 기존 세션 모두 삭제 (최대 1개만 유지)
      sessions = sessions.filter((s) => s.id === newSessionId);
    } else {
      newSessionId = newSessionId || Date.now().toString();
    }

    const userMessage = messages.find((msg) => msg.type === 'user');
    const title = userMessage
      ? userMessage.content.substring(0, 30) +
        (userMessage.content.length > 30 ? '...' : '')
      : type === 'dispute'
      ? '분쟁 상담'
      : '일반 상담';

    const sessionIndex = sessions.findIndex((s) => s.id === newSessionId);
    const now = Date.now();
    const expiresAt = !isLoggedIn ? now + SESSION_EXPIRY_DURATION : null;

    const sessionData: ChatSession = {
      id: newSessionId,
      type,
      title,
      createdAt: sessionIndex >= 0 ? sessions[sessionIndex].createdAt : now,
      expiresAt:
        sessionIndex >= 0 ? sessions[sessionIndex].expiresAt : expiresAt,
      lastUpdated: now,
      messages: messages.map((msg) => ({
        ...msg,
        timestamp: msg.timestamp instanceof Date ? msg.timestamp.getTime() : msg.timestamp,
      })),
    };

    if (sessionIndex >= 0) {
      sessions[sessionIndex] = sessionData;
    } else {
      sessions.unshift(sessionData);
    }

    storage.set(storageKey, sessions, !isLoggedIn);
    set({ chatSessions: sessions, currentSessionId: newSessionId });
  },

  deleteChatSession: (sessionId, isLoggedIn) => {
    const storageKey = isLoggedIn
      ? STORAGE_KEYS.CHAT_SESSIONS
      : STORAGE_KEYS.TEMP_CHAT_SESSIONS;

    const sessions = storage.get<ChatSession[]>(storageKey, !isLoggedIn) || [];
    const filteredSessions = sessions.filter((s) => s.id !== sessionId);

    storage.set(storageKey, filteredSessions, !isLoggedIn);

    set((state) => ({
      chatSessions: filteredSessions,
      currentSessionId: state.currentSessionId === sessionId ? null : state.currentSessionId,
    }));
  },

  refreshSessionTime: (sessionId) => {
    const sessions = storage.get<ChatSession[]>(STORAGE_KEYS.TEMP_CHAT_SESSIONS, true) || [];
    const sessionIndex = sessions.findIndex((s) => s.id === sessionId);

    if (sessionIndex >= 0) {
      const now = Date.now();
      sessions[sessionIndex].expiresAt = now + SESSION_EXPIRY_DURATION;
      sessions[sessionIndex].lastUpdated = now;
      storage.set(STORAGE_KEYS.TEMP_CHAT_SESSIONS, sessions, true);
      set({ chatSessions: sessions });
    }
  },

  startNewChat: () => {
    set({
      currentSessionId: null,
      activeChatType: null,
      isFormSubmitted: false,
      disputeMessages: [...initialMessages],
      generalMessages: [...initialMessages],
    });
  },
}));
