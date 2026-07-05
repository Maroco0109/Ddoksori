import { create } from 'zustand';
import type { ChatSession, MessageWithCitations, ChatType, DisputeFormData, TestVariant } from '@/shared/types';
import { storage } from '@/shared/lib/storage';
import { STORAGE_KEYS } from '@/shared/config/storage-keys';
import { SESSION_EXPIRY_DURATION } from '@/shared/config';
import { generateGuestSessionId } from '@/shared/lib/session';
import { getUserSessions, deleteSession, convertBackendSessionToLocal } from '@/shared/lib/api-client';
import { useAuthStore } from '@/features/auth/auth.store';

/**
 * 메시지에서 세션 title을 생성합니다.
 */
function generateTitleFromMessages(type: ChatType, messages: MessageWithCitations[]): string {
  if (type === 'dispute') {
    // 분쟁 상담: [분쟁 정보]로 시작하지 않는 user 메시지 찾기
    const actualQuestion = messages.find(
      (msg) => msg.type === 'user' && !msg.content.startsWith('[분쟁 정보]')
    );

    if (actualQuestion) {
      return actualQuestion.content.substring(0, 30) +
        (actualQuestion.content.length > 30 ? '...' : '');
    } else {
      // 실제 질문이 없으면 폼 데이터에서 구매품목 추출
      const formMessage = messages.find((msg) => msg.type === 'user' && msg.content.includes('구매품목'));
      if (formMessage) {
        const match = formMessage.content.match(/구매품목\s*[:：]\s*([^\n]+)/);
        return match ? `${match[1].trim()} 관련 상담` : '분쟁 상담';
      } else {
        return '분쟁 상담';
      }
    }
  } else {
    // 일반 상담: 첫 번째 user 메시지 사용
    const userMessage = messages.find((msg) => msg.type === 'user');
    return userMessage
      ? userMessage.content.substring(0, 30) +
        (userMessage.content.length > 30 ? '...' : '')
      : '일반 상담';
  }
}

interface ChatState {
  currentSessionId: string | null;
  activeChatType: ChatType | null;
  chatSessions: ChatSession[];
  disputeMessages: MessageWithCitations[];
  generalMessages: MessageWithCitations[];
  isDisputeLoading: boolean;
  isGeneralLoading: boolean;
  isFormSubmitted: boolean;
  backendSessionId: string | null;
  disputeFormData: DisputeFormData | null;
  testVariant: TestVariant;

  // Actions
  setCurrentSessionId: (id: string | null) => void;
  setActiveChatType: (type: ChatType | null) => void;
  setChatSessions: (sessions: ChatSession[]) => void;
  setDisputeMessages: (messages: MessageWithCitations[]) => void;
  setGeneralMessages: (messages: MessageWithCitations[]) => void;
  setIsDisputeLoading: (loading: boolean) => void;
  setIsGeneralLoading: (loading: boolean) => void;
  setIsFormSubmitted: (submitted: boolean) => void;
  setBackendSessionId: (id: string | null) => void;
  setDisputeFormData: (data: DisputeFormData | null) => void;
  setTestVariant: (tv: TestVariant) => void;

  loadChatSessions: (isLoggedIn: boolean) => void;
  saveChatSession: (type: ChatType, messages: MessageWithCitations[], isLoggedIn: boolean) => void;
  deleteChatSession: (sessionId: string, isLoggedIn: boolean) => Promise<void>;
  refreshSessionTime: (sessionId: string) => void;
  startNewChat: () => void;
  resetState: () => void;
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
  backendSessionId: null,
  disputeFormData: null,
  testVariant: 'A',

  setCurrentSessionId: (id) => set({ currentSessionId: id }),
  setActiveChatType: (type) => set({ activeChatType: type }),
  setChatSessions: (sessions) => set({ chatSessions: sessions }),
  setDisputeMessages: (messages) => set({ disputeMessages: messages }),
  setGeneralMessages: (messages) => set({ generalMessages: messages }),
  setIsDisputeLoading: (loading) => set({ isDisputeLoading: loading }),
  setIsGeneralLoading: (loading) => set({ isGeneralLoading: loading }),
  setIsFormSubmitted: (submitted) => set({ isFormSubmitted: submitted }),
  setBackendSessionId: (id) => set({ backendSessionId: id }),
  setDisputeFormData: (data) => set({ disputeFormData: data }),
  setTestVariant: (tv) => set({ testVariant: tv }),

  loadChatSessions: async (isLoggedIn) => {
    if (isLoggedIn) {
      // 로그인 사용자: API로 세션 목록 조회
      const token = useAuthStore.getState().token;
      if (!token) return;

      try {
        const response = await getUserSessions(token, 100, 0);
        const sessions: ChatSession[] = response.sessions.map(s => ({
          ...convertBackendSessionToLocal(s),
          messages: [],
        }));
        set({ chatSessions: sessions });
      } catch (error) {
        console.error('[ChatStore] loadChatSessions API error:', error);
      }
    } else {
      // 비로그인 사용자: sessionStorage에서 로드
      const storageKey = STORAGE_KEYS.TEMP_CHAT_SESSIONS;
      let sessions = storage.get<ChatSession[]>(storageKey, true) || [];

      // Filter expired sessions
      const now = Date.now();
      sessions = sessions.filter((s) => !s.expiresAt || s.expiresAt > now);
      storage.set(storageKey, sessions, true);

      set({ chatSessions: sessions });
    }
  },

  saveChatSession: async (type, messages, isLoggedIn) => {
    if (isLoggedIn) {
      // 로그인 사용자: 백엔드가 DB에 자동 저장하므로 아무것도 하지 않음.
      // 단, store의 chatSessions에 현재 세션 반영 (사이드바 표시용)
      const state = get();
      const sessionId = state.backendSessionId || state.currentSessionId;
      if (!sessionId) return;

      const title = generateTitleFromMessages(type, messages);
      const existingIndex = state.chatSessions.findIndex(s => s.id === sessionId);

      if (existingIndex >= 0) {
        const updated = [...state.chatSessions];
        updated[existingIndex] = {
          ...updated[existingIndex],
          title,
          messages: messages.map(msg => ({
            ...msg,
            timestamp: msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp),
          })),
          lastMessageAt: new Date(),
          lastUpdated: Date.now(),
        };
        set({ chatSessions: updated, currentSessionId: sessionId });
      } else {
        // 새 세션을 목록에 추가
        const newSession: ChatSession = {
          id: sessionId,
          type,
          title,
          createdAt: Date.now(),
          lastMessageAt: new Date(),
          expiresAt: null,
          lastUpdated: Date.now(),
          messages: messages.map(msg => ({
            ...msg,
            timestamp: msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp),
          })),
        };
        set({ chatSessions: [newSession, ...state.chatSessions], currentSessionId: sessionId });
      }
      return;
    }

    // 비로그인 사용자: sessionStorage에 저장 (기존 방식)
    const state = get();
    const storageKey = STORAGE_KEYS.TEMP_CHAT_SESSIONS;
    let sessions = storage.get<ChatSession[]>(storageKey, true) || [];

    let newSessionId = state.backendSessionId || state.currentSessionId;

    if (sessions.length > 0 && !newSessionId) {
      newSessionId = sessions[0].id;
    } else if (!newSessionId) {
      newSessionId = await generateGuestSessionId();
    }
    sessions = sessions.filter((s) => s.id === newSessionId);

    const title = generateTitleFromMessages(type, messages);
    const sessionIndex = sessions.findIndex((s) => s.id === newSessionId);
    const now = Date.now();
    const expiresAt = now + SESSION_EXPIRY_DURATION;

    const sessionData: ChatSession = {
      id: newSessionId,
      type,
      title,
      createdAt: sessionIndex >= 0 ? sessions[sessionIndex].createdAt : now,
      lastMessageAt: new Date(),
      expiresAt: sessionIndex >= 0 ? sessions[sessionIndex].expiresAt : expiresAt,
      lastUpdated: now,
      messages: messages.map((msg) => ({
        ...msg,
        timestamp: msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp),
      })),
    };

    if (sessionIndex >= 0) {
      sessions[sessionIndex] = sessionData;
    } else {
      sessions.unshift(sessionData);
    }

    storage.set(storageKey, sessions, true);
    set({ chatSessions: sessions, currentSessionId: newSessionId });
  },

  deleteChatSession: async (sessionId, isLoggedIn) => {
    if (isLoggedIn) {
      // 로그인 사용자: API로 삭제
      const token = useAuthStore.getState().token;
      if (token) {
        try {
          await deleteSession(token, sessionId);
        } catch (error) {
          console.error('[ChatStore] deleteSession API error:', error);
        }
      }
    } else {
      // 비로그인 사용자: sessionStorage에서 삭제
      const storageKey = STORAGE_KEYS.TEMP_CHAT_SESSIONS;
      const sessions = storage.get<ChatSession[]>(storageKey, true) || [];
      const filteredSessions = sessions.filter((s) => s.id !== sessionId);
      storage.set(storageKey, filteredSessions, true);
    }

    // state에서 세션 제거
    set((state) => {
      const filteredSessions = state.chatSessions.filter((s) => s.id !== sessionId);
      return {
        chatSessions: filteredSessions,
        currentSessionId: state.currentSessionId === sessionId ? null : state.currentSessionId,
      };
    });
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
      backendSessionId: null,
      disputeFormData: null,
    });
  },

  resetState: () => {
    set({
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
  },
}));
