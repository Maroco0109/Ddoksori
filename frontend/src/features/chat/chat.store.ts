import { create } from 'zustand';
import type { ChatSession, MessageWithCitations, ChatType, DisputeFormData } from '@/shared/types';
import { storage } from '@/shared/lib/storage';
import { STORAGE_KEYS, getUserChatSessionsKey, getUserHiddenSessionsKey } from '@/shared/config/storage-keys';
import { SESSION_EXPIRY_DURATION } from '@/shared/config';
import { generateGuestSessionId } from '@/shared/lib/session';
import { getUserSessions, getSessionHistory, convertBackendSessionToLocal } from '@/shared/lib/api-client';
import { useAuthStore } from '@/features/auth/auth.store';

/**
 * 현재 로그인한 사용자 ID를 가져옵니다.
 * Zustand의 in-memory 상태에서 직접 읽어 레이스 컨디션을 방지합니다.
 */
function getCurrentUserId(): string | null {
  const user = useAuthStore.getState().user;
  return user?.id || null;
}

/**
 * 숨긴 세션 목록을 가져옵니다.
 */
function getHiddenSessions(userId: string | null): Set<string> {
  const key = getUserHiddenSessionsKey(userId);
  const hidden = storage.get<string[]>(key, false) || [];
  return new Set(hidden);
}

/**
 * 세션을 숨긴 목록에 추가합니다.
 */
function addHiddenSession(userId: string | null, sessionId: string): void {
  const key = getUserHiddenSessionsKey(userId);
  const hidden = getHiddenSessions(userId);
  hidden.add(sessionId);
  storage.set(key, Array.from(hidden), false);
}

/**
 * 세션 목록에서 숨긴 세션을 필터링합니다.
 */
function filterHiddenSessions(sessions: ChatSession[], userId: string | null): ChatSession[] {
  const hiddenSessions = getHiddenSessions(userId);
  return sessions.filter(session => !hiddenSessions.has(session.id));
}

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
  isSyncing: boolean;
  isTransitioning: boolean;

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
  setIsTransitioning: (transitioning: boolean) => void;

  loadChatSessions: (isLoggedIn: boolean) => void;
  saveChatSession: (type: ChatType, messages: MessageWithCitations[], isLoggedIn: boolean) => void;
  deleteChatSession: (sessionId: string, isLoggedIn: boolean) => Promise<void>;
  refreshSessionTime: (sessionId: string) => void;
  startNewChat: () => void;
  resetState: () => void;
  syncWithBackend: (token: string) => Promise<void>;
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
  isSyncing: false,
  isTransitioning: false,

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
  setIsTransitioning: (transitioning) => set({ isTransitioning: transitioning }),

  loadChatSessions: (isLoggedIn) => {
    // 동기화 중이면 로드 건너뛰기 (race condition 방지)
    if (get().isSyncing) {
      console.log('[ChatStore] Skipping loadChatSessions — sync in progress');
      return;
    }
    let storageKey: string;
    let userId: string | null = null;

    if (isLoggedIn) {
      // 로그인 사용자: 사용자별 고유 key 사용
      userId = getCurrentUserId();
      storageKey = getUserChatSessionsKey(userId);
    } else {
      // 비로그인 사용자: 임시 세션 key 사용
      storageKey = STORAGE_KEYS.TEMP_CHAT_SESSIONS;
    }

    let sessions = storage.get<ChatSession[]>(storageKey, !isLoggedIn) || [];

    // Filter expired sessions for non-logged-in users
    if (!isLoggedIn) {
      const now = Date.now();
      sessions = sessions.filter((s) => !s.expiresAt || s.expiresAt > now);
      storage.set(storageKey, sessions, true);
    } else {
      // 로그인 사용자: 숨긴 세션 필터링
      sessions = filterHiddenSessions(sessions, userId);
    }

    set({ chatSessions: sessions });
  },

  saveChatSession: async (type, messages, isLoggedIn) => {
    const state = get();
    // Guard: skip save during session transition to prevent message contamination
    if (state.isTransitioning) {
      console.log('[ChatStore] Skipping save — session transition in progress');
      return;
    }
    let storageKey: string;
    let userId: string | null = null;

    console.log('[ChatStore] saveChatSession called:', {
      type,
      messageCount: messages.length,
      backendSessionId: state.backendSessionId,
      currentSessionId: state.currentSessionId,
    });

    if (isLoggedIn) {
      // 로그인 사용자: 사용자별 고유 key 사용
      userId = getCurrentUserId();
      storageKey = getUserChatSessionsKey(userId);
    } else {
      // 비로그인 사용자: 임시 세션 key 사용
      storageKey = STORAGE_KEYS.TEMP_CHAT_SESSIONS;
    }

    let sessions = storage.get<ChatSession[]>(storageKey, !isLoggedIn) || [];

    // 세션 ID 결정 우선순위:
    // 1. backendSessionId (백엔드에서 반환한 ID - 가장 우선)
    // 2. currentSessionId (프론트엔드 로컬 ID)
    // 3. 새 ID 생성
    let newSessionId = state.backendSessionId || state.currentSessionId;

    // 백엔드 session_id를 받았고, 기존 currentSessionId와 다른 경우
    // 임시 ID로 저장된 세션을 백엔드 ID로 변경
    if (state.backendSessionId && state.currentSessionId &&
        state.backendSessionId !== state.currentSessionId) {

      // 이미 백엔드 ID를 가진 세션이 있는지 확인 (중복 방지)
      const backendSessionExists = sessions.some((s) => s.id === state.backendSessionId);

      if (!backendSessionExists) {
        const oldSessionIndex = sessions.findIndex((s) => s.id === state.currentSessionId);
        if (oldSessionIndex >= 0) {
          // 임시 ID 세션을 백엔드 ID로 변경
          sessions[oldSessionIndex].id = state.backendSessionId;
          console.log(`[ChatStore] Updated session ID: ${state.currentSessionId} -> ${state.backendSessionId}`);
        }
      }
    }

    if (!isLoggedIn) {
      // 비로그인 사용자는 최대 1개의 세션만 유지
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
      // 로그인 사용자: ID가 없으면 새로 생성 (단, 중복 방지)
      if (!newSessionId) {
        newSessionId = Date.now().toString();
        console.log(`[ChatStore] Generated new session ID: ${newSessionId}`);
      } else {
        console.log(`[ChatStore] Using existing session ID: ${newSessionId}`);
      }
    }

    // Title 생성
    const title = generateTitleFromMessages(type, messages);

    // 중복 세션 제거: 같은 ID를 가진 세션이 여러 개 있으면 하나만 남김
    const uniqueSessions: ChatSession[] = [];
    const seenIds = new Set<string>();
    for (const session of sessions) {
      if (!seenIds.has(session.id)) {
        uniqueSessions.push(session);
        seenIds.add(session.id);
      }
    }
    sessions = uniqueSessions;

    const sessionIndex = sessions.findIndex((s) => s.id === newSessionId);
    const now = Date.now();
    const expiresAt = !isLoggedIn ? now + SESSION_EXPIRY_DURATION : null;

    const sessionData: ChatSession = {
      id: newSessionId,
      type,
      title,
      createdAt: sessionIndex >= 0 ? sessions[sessionIndex].createdAt : now,
      lastMessageAt: new Date(),
      expiresAt:
        sessionIndex >= 0 ? sessions[sessionIndex].expiresAt : expiresAt,
      lastUpdated: now,
      messages: messages.map((msg) => ({
        ...msg,
        timestamp: msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp),
      })),
    };

    if (sessionIndex >= 0) {
      console.log(`[ChatStore] Updating existing session at index ${sessionIndex}`);
      sessions[sessionIndex] = sessionData;
    } else {
      console.log(`[ChatStore] Creating new session`);
      sessions.unshift(sessionData);
    }

    storage.set(storageKey, sessions, !isLoggedIn);

    // 로그인 사용자의 경우 숨긴 세션 필터링
    const visibleSessions = isLoggedIn ? filterHiddenSessions(sessions, getCurrentUserId()) : sessions;
    set({ chatSessions: visibleSessions, currentSessionId: newSessionId });
  },

  deleteChatSession: async (sessionId, isLoggedIn) => {
    console.log(`[ChatStore] Hiding session (not deleting from backend): ${sessionId}`);

    if (isLoggedIn) {
      // 로그인 사용자: 숨긴 세션 목록에 추가
      const userId = getCurrentUserId();
      addHiddenSession(userId, sessionId);
      console.log(`[ChatStore] Added session to hidden list: ${sessionId}`);
    } else {
      // 비로그인 사용자: localStorage에서 실제로 삭제
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

    console.log(`[ChatStore] Session hidden from UI: ${sessionId}`);
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
      isTransitioning: false,
    });
  },

  syncWithBackend: async (token: string) => {
    set({ isSyncing: true });
    try {
      const userId = getCurrentUserId();
      if (!userId) {
        console.warn('[ChatStore] syncWithBackend: No user ID');
        return;
      }

      console.log('[ChatStore] Syncing with backend...');

      // 백엔드에서 세션 목록 가져오기
      const response = await getUserSessions(token, 100, 0);
      const backendSessions = response.sessions;

      console.log(`[ChatStore] Fetched ${backendSessions.length} sessions from backend`);

      // localStorage의 현재 세션들
      const storageKey = getUserChatSessionsKey(userId);
      const localSessions = storage.get<ChatSession[]>(storageKey, false) || [];

      // 백엔드 세션을 ChatSession 형식으로 변환
      const convertedSessions: ChatSession[] = [];

      for (const backendSession of backendSessions) {
        // localStorage에 이미 있는 세션인지 확인
        const existingSession = localSessions.find(s => s.id === backendSession.id);

        if (existingSession) {
          // 기존 세션 업데이트 (메시지는 유지)
          // 백엔드 title이 기본값이면 메시지에서 재생성
          const needsTitleRegeneration =
            backendSession.title === 'dispute 상담' ||
            backendSession.title === 'general 상담' ||
            !backendSession.title;

          const finalTitle = needsTitleRegeneration
            ? generateTitleFromMessages(existingSession.type, existingSession.messages)
            : backendSession.title;

          convertedSessions.push({
            ...existingSession,
            title: finalTitle,
            lastMessageAt: new Date(backendSession.lastMessageAt),
            lastUpdated: new Date(backendSession.lastMessageAt).getTime(),
          });
        } else {
          // 새 세션: 메시지를 백엔드에서 가져와야 함
          try {
            const historyResponse = await getSessionHistory(token, backendSession.id, 50);

            // 백엔드는 최신순(DESC)으로 반환하므로 역순으로 변환 (오래된 것부터)
            const messages: MessageWithCitations[] = historyResponse.messages
              .map(msg => ({
                id: msg.id,
                type: msg.type,
                content: msg.content,
                timestamp: new Date(msg.timestamp),
              }))
              .reverse(); // 역순 변환: 최신순 → 시간순

            // 메시지에서 title 재생성
            const sessionType = backendSession.type as ChatType;
            const generatedTitle = generateTitleFromMessages(sessionType, messages);

            convertedSessions.push({
              ...convertBackendSessionToLocal(backendSession),
              title: generatedTitle,
              messages,
            });
          } catch (error) {
            console.error(`[ChatStore] Failed to fetch history for session ${backendSession.id}:`, error);
            // 메시지 없이라도 세션은 추가
            convertedSessions.push({
              ...convertBackendSessionToLocal(backendSession),
              messages: [],
            });
          }
        }
      }

      // 백엔드에 없지만 최근 5분 이내 생성된 로컬 세션 보존 (DB 저장 지연 방어)
      const backendSessionIds = new Set(convertedSessions.map(s => s.id));
      const recentLocalOnly = localSessions.filter(
        s => !backendSessionIds.has(s.id) && s.lastUpdated && (Date.now() - s.lastUpdated < 5 * 60 * 1000)
      );
      const mergedSessions = [...convertedSessions, ...recentLocalOnly];

      if (recentLocalOnly.length > 0) {
        console.log(`[ChatStore] Preserved ${recentLocalOnly.length} recent local-only sessions`);
      }

      // 숨긴 세션 필터링
      const visibleSessions = filterHiddenSessions(mergedSessions, userId);

      // localStorage에 저장 (필터링되지 않은 전체 세션 저장 - 숨김 해제 가능하도록)
      storage.set(storageKey, mergedSessions, false);

      // state 업데이트 (필터링된 세션만)
      set({ chatSessions: visibleSessions });

      console.log(`[ChatStore] Sync complete: ${visibleSessions.length} sessions (${mergedSessions.length - visibleSessions.length} hidden)`);
    } catch (error) {
      console.error('[ChatStore] syncWithBackend failed:', error);
      // 동기화 실패 시 localStorage 데이터 사용
      const userId = getCurrentUserId();
      if (userId) {
        const storageKey = getUserChatSessionsKey(userId);
        const localSessions = storage.get<ChatSession[]>(storageKey, false) || [];
        // 숨긴 세션 필터링
        const visibleSessions = filterHiddenSessions(localSessions, userId);
        set({ chatSessions: visibleSessions });
      }
    } finally {
      set({ isSyncing: false });
    }
  },
}));
