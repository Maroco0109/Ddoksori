import { useState, useRef, useEffect, useCallback } from 'react';
import type { ChangeEvent, FormEvent, RefObject } from 'react';
import type { ChatSession, ChatType, DisputeForm, DisputeFormData, MessageWithCitations } from '@/shared/types';
import { Send } from 'lucide-react';
import { useChatStore } from '@/features/chat/chat.store';
import { useAuthStore } from '@/features/auth/auth.store';
import { useChatMutation } from './hooks/useChatMutation';
import { useStreamingChat } from './hooks/useStreamingChat';
import { extractCitations } from '@/shared/lib/citation';
import { simulateStreaming } from '@/shared/lib/streaming';
import { MessageBubble } from './components/MessageBubble';
import { SafetyWarning } from './components/SafetyWarning';
import { StatusIndicator } from './components/StatusIndicator';

interface ChatPageProps {
  currentSessionId?: string | null;
  onSessionCreate?: (sessionId: string) => void;
}

export default function ChatPage({ currentSessionId = null, onSessionCreate }: ChatPageProps) {
  const storeSessionId = useChatStore((state) => state.currentSessionId);
  const storeActiveChatType = useChatStore((state) => state.activeChatType);
  const storeChatSessions = useChatStore((state) => state.chatSessions);
  const setStoreSessionId = useChatStore((state) => state.setCurrentSessionId);
  const setStoreChatType = useChatStore((state) => state.setActiveChatType);
  const saveChatSessionToStore = useChatStore((state) => state.saveChatSession);
  const setDisputeFormData = useChatStore((state) => state.setDisputeFormData);
  const setBackendSessionId = useChatStore((state) => state.setBackendSessionId);
  const isTransitioning = useChatStore((state) => state.isTransitioning);
  const setIsTransitioning = useChatStore((state) => state.setIsTransitioning);
  const isTransitioningRef = useRef(false);
  const resolvedSessionId = currentSessionId ?? storeSessionId;

  // Bug 1 fix: Track previous session ID to detect actual session switches
  // undefined = initial mount (never seen a session), null = new chat, string = specific session
  const prevSessionIdRef = useRef<string | null | undefined>(undefined);
  // Bug 2 fix: Track all transition timers for cleanup on rapid switches
  const transitionTimersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  // 현재 세션 ID
  const [sessionId, setSessionId] = useState<string | null>(resolvedSessionId);

  // React Query mutation for API calls (fallback)
  const chatMutation = useChatMutation();

  // PR-7: SSE Streaming hook for real-time agent status
  const { streamingState: disputeStreamingState, startStream: startDisputeStream, cancelStream: cancelDisputeStream } = useStreamingChat();
  const { streamingState: generalStreamingState, startStream: startGeneralStream, cancelStream: cancelGeneralStream } = useStreamingChat();

  // 분쟁 상담 state
  const [disputeMessages, setDisputeMessages] = useState<MessageWithCitations[]>([
    {
      id: 1,
      type: 'ai',
      content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
      timestamp: new Date()
    }
  ]);
  const [disputeInputValue, setDisputeInputValue] = useState('');
  const [isDisputeLoading, setIsDisputeLoading] = useState(false);
  const [isFormSubmitted, setIsFormSubmitted] = useState(false);

  // 일반 상담 state
  const [generalMessages, setGeneralMessages] = useState<MessageWithCitations[]>([
    {
      id: 1,
      type: 'ai',
      content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
      timestamp: new Date()
    }
  ]);
  const [generalInputValue, setGeneralInputValue] = useState('');
  const [isGeneralLoading, setIsGeneralLoading] = useState(false);

  // 분쟁 상담 폼 state
  const [disputeForm, setDisputeForm] = useState<DisputeForm>({
    purchaseDate: '',
    purchasePlace: '',
    platform: '',
    purchaseItem: '',
    purchaseAmount: '',
    disputeDetail: ''
  });

  // 활성 상담 타입 (null, 'dispute', 'general')
  const [activeChatType, setActiveChatType] = useState<ChatType | null>(null);

  // 로그인 여부 확인
  const isLoggedIn = useAuthStore((state) => state.isAuthenticated);

  // 컴포넌트 마운트 시 스크롤 최상단으로 이동 (한 번만 실행)
  useEffect(() => {
    const scrollToTop = () => {
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      document.documentElement.scrollTop = 0;
      document.body.scrollTop = 0;
    };

    scrollToTop();
    setTimeout(scrollToTop, 50);
    setTimeout(scrollToTop, 100);
  }, []); // 빈 의존성 배열 - 마운트 시 한 번만 실행

  // 세션 불러오기
  useEffect(() => {
    // Bug 2 fix: Cancel all pending timers from previous transition
    transitionTimersRef.current.forEach(clearTimeout);
    transitionTimersRef.current = [];

    // Bug 1 fix: Skip if resolvedSessionId hasn't actually changed (spurious re-trigger)
    if (prevSessionIdRef.current !== undefined
        && prevSessionIdRef.current === resolvedSessionId) {
      return;
    }

    // Bug 1 fix: Only cancel streams on actual session switch (ID_A → ID_B)
    // null → ID is session "creation" (not a switch), so don't cancel streams
    const isSessionSwitch = prevSessionIdRef.current !== undefined
      && prevSessionIdRef.current !== resolvedSessionId
      && prevSessionIdRef.current !== null;

    prevSessionIdRef.current = resolvedSessionId;

    // Synchronous ref lock (immediate, no batching delay)
    isTransitioningRef.current = true;
    setIsTransitioning(true);

    // Cancel active streams only on actual session switch
    if (isSessionSwitch) {
      cancelDisputeStream();
      cancelGeneralStream();
    }

    if (resolvedSessionId) {
      setSessionId(resolvedSessionId);

      if (storeSessionId !== resolvedSessionId) {
        setStoreSessionId(resolvedSessionId);
      }

      // store의 chatSessions에서 세션 찾기 (이미 숨긴 세션이 필터링된 상태)
      // stale closure 방지를 위해 직접 store에서 가져오기
      const currentSessions = useChatStore.getState().chatSessions;
      const session = currentSessions.find(s => s.id === resolvedSessionId);

      if (session) {
        // 메시지를 id(turn_number) 순서로 정렬 (혹시 역순으로 저장된 경우 대비)
        const restoredMessages = session.messages
          .map(msg => ({
            ...msg,
            timestamp: msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp)
          }))
          .sort((a, b) => a.id - b.id); // id 오름차순 정렬

        // store에서 설정한 chatType을 우선 사용, 없으면 세션의 type 사용
        const chatType = storeActiveChatType || session.type;

        if (chatType === 'dispute') {
          setDisputeMessages(restoredMessages);
          setActiveChatType('dispute');
          setIsFormSubmitted(true);
          setStoreChatType('dispute');
          // Bug 2 fix: Register scroll timer for cleanup
          const scrollTimer = setTimeout(() => {
            disputeMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
          }, 200);
          transitionTimersRef.current.push(scrollTimer);
        } else {
          setGeneralMessages(restoredMessages);
          setActiveChatType('general');
          setStoreChatType('general');
          // Bug 2 fix: Register scroll timer for cleanup
          const scrollTimer = setTimeout(() => {
            generalMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
          }, 200);
          transitionTimersRef.current.push(scrollTimer);
        }
        // Bug 2 fix: Register unlock timer for cleanup
        const unlockTimer = setTimeout(() => {
          isTransitioningRef.current = false;
          setIsTransitioning(false);
        }, 300);
        transitionTimersRef.current.push(unlockTimer);
      } else if (storeActiveChatType) {
        // 세션이 없지만 store에 chatType이 설정되어 있는 경우
        setActiveChatType(storeActiveChatType);
        if (storeActiveChatType === 'dispute') {
          setIsFormSubmitted(false);
        }
        isTransitioningRef.current = false;
        setIsTransitioning(false);
      }
    } else {
      setSessionId(null);
      setActiveChatType(null);
      setIsFormSubmitted(false);
      setStoreSessionId(null);
      setStoreChatType(null);
      setBackendSessionId(null);
      setDisputeFormData(null);
      setDisputeMessages([
        {
          id: 1,
          type: 'ai',
          content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
          timestamp: new Date()
        }
      ]);
      setGeneralMessages([
        {
          id: 1,
          type: 'ai',
          content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
          timestamp: new Date()
        }
      ]);
      setDisputeForm({
        purchaseDate: '',
        purchasePlace: '',
        platform: '',
        purchaseItem: '',
        purchaseAmount: '',
        disputeDetail: ''
      });
      isTransitioningRef.current = false;
      setIsTransitioning(false);
    }

    // Bug 2 fix: Cleanup all timers on unmount or next re-trigger
    return () => {
      transitionTimersRef.current.forEach(clearTimeout);
      transitionTimersRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedSessionId, setStoreChatType, setStoreSessionId, storeSessionId, storeActiveChatType]);

  // 채팅 세션 저장 함수 (store 함수를 래핑)
  const saveChatSession = useCallback(async (type: ChatType, messages: MessageWithCitations[]) => {
    // store의 saveChatSession만 호출 (store에서 모든 state 관리)
    await saveChatSessionToStore(type, messages, isLoggedIn);
  }, [saveChatSessionToStore, isLoggedIn]);

  const disputeMessagesEndRef = useRef<HTMLDivElement | null>(null);
  const generalMessagesEndRef = useRef<HTMLDivElement | null>(null);
  const pageTopRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = (ref: RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (isTransitioningRef.current || isTransitioning) return;
    // 2차 방어: store의 세션 ID와 로컬 세션 ID가 일치하는지 확인
    const storeCurrentSessionId = useChatStore.getState().currentSessionId;
    if (storeCurrentSessionId && sessionId && storeCurrentSessionId !== sessionId) return;
    if (disputeMessages.length > 1) {
      scrollToBottom(disputeMessagesEndRef);
    }
    const hasUserMessage = disputeMessages.some(m => m.type === 'user');
    if (disputeMessages.length > 1 && hasUserMessage) {
      saveChatSession('dispute', disputeMessages);
    }
  }, [disputeMessages, saveChatSession, isTransitioning, sessionId]);

  useEffect(() => {
    if (isTransitioningRef.current || isTransitioning) return;
    // 2차 방어: store의 세션 ID와 로컬 세션 ID가 일치하는지 확인
    const storeCurrentSessionId = useChatStore.getState().currentSessionId;
    if (storeCurrentSessionId && sessionId && storeCurrentSessionId !== sessionId) return;
    if (generalMessages.length > 1) {
      scrollToBottom(generalMessagesEndRef);
    }
    const hasUserMessage = generalMessages.some(m => m.type === 'user');
    if (generalMessages.length > 1 && hasUserMessage) {
      saveChatSession('general', generalMessages);
    }
  }, [generalMessages, saveChatSession, isTransitioning, sessionId]);

  // 분쟁 상담 폼 제출 핸들러
  const handleDisputeFormSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    // 폼 데이터 검증
    if (!disputeForm.purchaseDate || !disputeForm.purchasePlace ||
        !disputeForm.purchaseItem || !disputeForm.purchaseAmount ||
        !disputeForm.disputeDetail) {
      alert('모든 항목을 입력해주세요.');
      return;
    }

    // 핸들러 진입 시 세션 ID 캡처 (스트림 응답 후 세션 전환 감지용)
    const expectedSessionId = resolvedSessionId;

    const formDataForBackend: DisputeFormData = {
      purchaseDate: disputeForm.purchaseDate,
      purchasePlace: disputeForm.purchasePlace,
      purchasePlatform: disputeForm.platform,
      purchaseItem: disputeForm.purchaseItem,
      purchaseAmount: disputeForm.purchaseAmount.replace(/,/g, ''),
      disputeDetails: disputeForm.disputeDetail,
    };
    setDisputeFormData(formDataForBackend);

    // 폼 데이터를 메시지로 변환
    const platformInfo = disputeForm.platform ? `\n● 플랫폼 : ${disputeForm.platform}` : '';
    const formMessage: MessageWithCitations = {
      id: disputeMessages.length + 1,
      type: 'user' as const,
      content: `[분쟁 정보]\n● 구매일자 : ${disputeForm.purchaseDate}\n● 구매처 : ${disputeForm.purchasePlace}${platformInfo}\n● 구매품목 : ${disputeForm.purchaseItem}\n● 구매금액 : ${disputeForm.purchaseAmount}원\n● 분쟁 상세 : ${disputeForm.disputeDetail}`,
      timestamp: new Date()
    };

    setDisputeMessages([...disputeMessages, formMessage]);
    setIsFormSubmitted(true);
    setStoreChatType('dispute');
    setActiveChatType('dispute');

    // AI 메시지 ID 미리 생성 (placeholder 없이)
    const aiMessageId = disputeMessages.length + 2;

    try {
      // PR-7: Use SSE streaming API for real-time progress
      const response = await startDisputeStream({
        message: formMessage.content,
        chat_type: 'dispute',
        top_k: 5,
        onboarding: {
          purchase_date: disputeForm.purchaseDate,
          purchase_place: disputeForm.purchasePlace,
          purchase_platform: disputeForm.platform || undefined,
          purchase_item: disputeForm.purchaseItem,
          purchase_amount: disputeForm.purchaseAmount.replace(/,/g, ''),
          dispute_details: disputeForm.disputeDetail,
        },
      });

      // 스트림 응답 후 세션이 전환됐는지 확인 (버퍼에 남은 데이터로 인한 오염 방지)
      // store에서 직접 읽어야 함 - 클로저의 resolvedSessionId는 렌더 시점 값이라 변하지 않음
      if (isTransitioningRef.current || useChatStore.getState().currentSessionId !== expectedSessionId) {
        return;
      }

      if (response) {
        const citations = extractCitations(response.answer, response.sources);
        const aiMessage: MessageWithCitations = {
          id: aiMessageId,
          type: 'ai' as const,
          content: response.answer,
          timestamp: new Date(),
          citations,
          isRestricted: response.is_restricted,
          agencyCode: response.agency_code,
          agencyInfo: response.agency_info,
        };
        setDisputeMessages((prev) => [...prev, aiMessage]);

        if (response.awaiting_user_choice && response.clarifying_questions && response.clarifying_questions.length > 0) {
          const warningMessage: MessageWithCitations = {
            id: aiMessageId + 1,
            type: 'ai' as const,
            content: '',
            timestamp: new Date(),
            hasSafetyWarning: true,
            clarifyingQuestions: response.clarifying_questions,
          };
          setDisputeMessages((prev) => [...prev, warningMessage]);
        }
      }
    } catch (error) {
      console.error('Chat API error:', error);
      const errorMessage: MessageWithCitations = {
        id: aiMessageId,
        type: 'ai' as const,
        content: '죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
        timestamp: new Date(),
      };
      setDisputeMessages((prev) => [...prev, errorMessage]);
    }
  };

  /**
   * Phase 2-16: 입력 텍스트에서 불필요한 대화 히스토리 제거
   * 사용자가 실수로 이전 답변을 복사해서 붙여넣은 경우를 방지
   */
  const cleanUserInput = (input: string): string => {
    const text = input.trim();

    // 답변 템플릿 헤더 패턴
    const answerHeaders = [
      '[답변 요약]',
      '[규정]',
      '[유사 사례]',
      '[주의 사항]',
      '[출처]',
      '[이전 대화]',
    ];

    // 텍스트가 답변 템플릿 헤더로 시작하는지 확인
    const startsWithTemplate = answerHeaders.some(header => text.startsWith(header));

    if (!startsWithTemplate) {
      return text; // 정상적인 사용자 질문
    }

    // 템플릿이 포함된 경우: 마지막 줄에서 실제 질문 추출
    const lines = text.split('\n');

    // 뒤에서부터 유효한 사용자 질문 찾기
    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();

      // 빈 줄이나 템플릿 요소 건너뛰기
      if (!line) continue;
      if (line.startsWith('#') || line.startsWith('-') || line.startsWith('●')) continue;
      if (line.startsWith('[') && line.endsWith(']')) continue;
      if (/^\d+\./.test(line)) continue; // 번호 리스트
      if (line.startsWith('*') || line.startsWith('¹') || line.startsWith('²')) continue;

      // 의미있는 질문 (최소 5글자)
      if (line.length >= 5) {
        console.warn('[ChatPage] Detected conversation history in input, extracted:', line.substring(0, 50));
        return line;
      }
    }

    // 추출 실패 시 원본 반환
    return text;
  };

  // 분쟁 상담 메시지 전송 핸들러 (PR-7: SSE Streaming)
  const handleDisputeSend = async () => {
    if (!disputeInputValue.trim() || disputeStreamingState.isStreaming) return;

    // 핸들러 진입 시 세션 ID 캡처 (스트림 응답 후 세션 전환 감지용)
    const expectedSessionId = resolvedSessionId;

    // DEBUG: 원본 입력값 로깅
    console.log('[ChatPage] Original disputeInputValue (length=' + disputeInputValue.length + '):', disputeInputValue.substring(0, 100));

    // Phase 2-16: 입력 텍스트 정제 (대화 히스토리 제거)
    const cleanedInput = cleanUserInput(disputeInputValue);

    // DEBUG: 정제 후 로깅
    console.log('[ChatPage] Cleaned input (length=' + cleanedInput.length + '):', cleanedInput.substring(0, 100));

    const newMessage: MessageWithCitations = {
      id: disputeMessages.length + 1,
      type: 'user' as const,
      content: cleanedInput,
      timestamp: new Date()
    };

    setDisputeMessages([...disputeMessages, newMessage]);
    setDisputeInputValue('');

    // AI 메시지 ID 미리 생성 (placeholder 없이)
    const aiMessageId = disputeMessages.length + 2;

    try {
      // PR-7: Use SSE streaming API for real-time progress
      const response = await startDisputeStream({
        message: cleanedInput,
        chat_type: 'dispute',
        top_k: 5,
      });

      // 스트림 응답 후 세션이 전환됐는지 확인 (버퍼에 남은 데이터로 인한 오염 방지)
      // store에서 직접 읽어야 함 - 클로저의 resolvedSessionId는 렌더 시점 값이라 변하지 않음
      if (isTransitioningRef.current || useChatStore.getState().currentSessionId !== expectedSessionId) {
        return;
      }

      if (response) {
        const citations = extractCitations(response.answer, response.sources);
        const aiMessage: MessageWithCitations = {
          id: aiMessageId,
          type: 'ai' as const,
          content: response.answer,
          timestamp: new Date(),
          citations,
        };
        setDisputeMessages((prev) => [...prev, aiMessage]);

        if (response.awaiting_user_choice && response.clarifying_questions && response.clarifying_questions.length > 0) {
          const warningMessage: MessageWithCitations = {
            id: aiMessageId + 1,
            type: 'ai' as const,
            content: '',
            timestamp: new Date(),
            hasSafetyWarning: true,
            clarifyingQuestions: response.clarifying_questions,
          };
          setDisputeMessages((prev) => [...prev, warningMessage]);
        }
      }
    } catch (error) {
      console.error('Chat API error:', error);
      const errorMessage: MessageWithCitations = {
        id: aiMessageId,
        type: 'ai' as const,
        content: '죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
        timestamp: new Date(),
      };
      setDisputeMessages((prev) => [...prev, errorMessage]);
    }
  };

  // 일반 상담 메시지 전송 핸들러 (PR-7: SSE Streaming)
  const handleGeneralSend = async () => {
    if (!generalInputValue.trim() || generalStreamingState.isStreaming) return;

    // 핸들러 진입 시 세션 ID 캡처 (스트림 응답 후 세션 전환 감지용)
    const expectedSessionId = resolvedSessionId;

    // Phase 2-16: 입력 텍스트 정제 (대화 히스토리 제거)
    const cleanedInput = cleanUserInput(generalInputValue);

    const newMessage: MessageWithCitations = {
      id: generalMessages.length + 1,
      type: 'user' as const,
      content: cleanedInput,
      timestamp: new Date()
    };

    setGeneralMessages([...generalMessages, newMessage]);
    setGeneralInputValue('');
    setActiveChatType('general');
    setStoreChatType('general');

    // AI 메시지 ID 미리 생성 (placeholder 없이)
    const aiMessageId = generalMessages.length + 2;

    try {
      // PR-7: Use SSE streaming API for real-time progress
      const response = await startGeneralStream({
        message: cleanedInput,
        chat_type: 'general',
        top_k: 5,
      });

      // 스트림 응답 후 세션이 전환됐는지 확인 (버퍼에 남은 데이터로 인한 오염 방지)
      // store에서 직접 읽어야 함 - 클로저의 resolvedSessionId는 렌더 시점 값이라 변하지 않음
      if (isTransitioningRef.current || useChatStore.getState().currentSessionId !== expectedSessionId) {
        return;
      }

      if (response) {
        const citations = extractCitations(response.answer, response.sources);
        const aiMessage: MessageWithCitations = {
          id: aiMessageId,
          type: 'ai' as const,
          content: response.answer,
          timestamp: new Date(),
          citations,
        };
        setGeneralMessages((prev) => [...prev, aiMessage]);

        if (response.awaiting_user_choice && response.clarifying_questions && response.clarifying_questions.length > 0) {
          const warningMessage: MessageWithCitations = {
            id: aiMessageId + 1,
            type: 'ai' as const,
            content: '',
            timestamp: new Date(),
            hasSafetyWarning: true,
            clarifyingQuestions: response.clarifying_questions,
          };
          setGeneralMessages((prev) => [...prev, warningMessage]);
        }
      }
    } catch (error) {
      console.error('Chat API error:', error);
      const errorMessage: MessageWithCitations = {
        id: aiMessageId,
        type: 'ai' as const,
        content: '죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
        timestamp: new Date(),
      };
      setGeneralMessages((prev) => [...prev, errorMessage]);
    }
  };

  // 숫자 포맷팅 함수 (천원 단위 콤마)
  const formatNumber = (value: string) => {
    const number = value.replace(/[^0-9]/g, '');
    return number.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  };

  // 폼 입력 핸들러
  const handleFormChange = (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = event.target;

    if (name === 'purchaseAmount') {
      const formattedValue = formatNumber(value);
      setDisputeForm(prev => ({
        ...prev,
        [name]: formattedValue
      }));
    } else {
      setDisputeForm(prev => ({
        ...prev,
        [name]: value
      }));
    }
  };

  return (
    <div className="chat-page flex flex-col h-full">
      {/* 페이지 최상단 참조 */}
      <div ref={pageTopRef} />
      {/* Custom scrollbar styles */}
      <style>{`
        .chat-scrollbar::-webkit-scrollbar {
          width: 8px;
        }
        .chat-scrollbar::-webkit-scrollbar-track {
          background: #f0f0f0;
          border-radius: 10px;
        }
        .chat-scrollbar::-webkit-scrollbar-thumb {
          background: #0d9488;
          border-radius: 10px;
        }
        .chat-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #0f766e;
        }
      `}</style>

      {/* Chat Header */}
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl sm:text-3xl md:text-4xl lg:text-5xl font-extrabold mb-3 md:mb-4 text-dark-navy">AI 상담 챗봇</h1>
        <p className="text-sm sm:text-base text-gray-purple">24시간 언제든지 질문하세요</p>
      </div>

      {/* Main Container - 좌우 분할 */}
      <div className={`flex-1 grid gap-4 md:gap-6 min-h-0 ${
        activeChatType === null ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-1'
      }`}>

        {/* 분쟁 상담 영역 */}
        {(activeChatType === null || activeChatType === 'dispute') && (
          <div className="bg-white rounded-xl md:rounded-2xl shadow-lg flex flex-col overflow-hidden">
          {/* 분쟁 상담 헤더 */}
          <div className="bg-deep-teal text-white px-4 sm:px-6 py-3 sm:py-4">
            <h2 className="text-lg sm:text-xl font-bold">분쟁 상담</h2>
          </div>

          {!isFormSubmitted ? (
            /* 폼 입력 화면 */
            <div className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto chat-scrollbar">
              {/* 초기 메시지 */}
              <div className="mb-6">
                <div className="bg-lavender/30 px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-2xl rounded-bl-sm text-dark-navy leading-relaxed text-sm sm:text-base">
                  {disputeMessages[0].content}
                </div>
              </div>

              <p className="text-sm text-gray-purple mb-4">분쟁 정보를 입력해주세요.</p>

              <form onSubmit={handleDisputeFormSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-dark-navy mb-2">
                    1. 구매일자
                  </label>
                  <input
                    type="date"
                    name="purchaseDate"
                    value={disputeForm.purchaseDate}
                    onChange={handleFormChange}
                    className="w-full px-4 py-3 border-2 border-ivory rounded-lg outline-none focus:border-deep-teal transition-all"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-dark-navy mb-2">
                    2. 구매처
                  </label>
                  <p className="text-xs text-gray-purple mb-2">
                    판매자의 상호명 또는 브랜드명을 입력하세요. 네이버, 쿠팡 등 플랫폼을 통해서 구매했을 경우, 플랫폼 내용은 (플랫폼)에 추가로 기입해주세요.
                  </p>
                  <input
                    type="text"
                    name="purchasePlace"
                    value={disputeForm.purchasePlace}
                    onChange={handleFormChange}
                    placeholder="예: ABC상사, 가나다전자 등"
                    className="w-full px-4 py-3 border-2 border-ivory rounded-lg outline-none focus:border-deep-teal transition-all"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-dark-navy mb-2">
                    (플랫폼)
                  </label>
                  <input
                    type="text"
                    name="platform"
                    value={disputeForm.platform}
                    onChange={handleFormChange}
                    placeholder="예: 네이버, 쿠팡 등"
                    className="w-full px-4 py-3 border-2 border-ivory rounded-lg outline-none focus:border-deep-teal transition-all"
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-dark-navy mb-2">
                    3. 구매품목
                  </label>
                  <input
                    type="text"
                    name="purchaseItem"
                    value={disputeForm.purchaseItem}
                    onChange={handleFormChange}
                    placeholder="예: 노트북, 의류, 가전제품 등"
                    className="w-full px-4 py-3 border-2 border-ivory rounded-lg outline-none focus:border-deep-teal transition-all"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-dark-navy mb-2">
                    4. 구매금액
                  </label>
                  <input
                    type="text"
                    name="purchaseAmount"
                    value={disputeForm.purchaseAmount}
                    onChange={handleFormChange}
                    placeholder="숫자만 입력 (원 단위)"
                    className="w-full px-4 py-3 border-2 border-ivory rounded-lg outline-none focus:border-deep-teal transition-all"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-semibold text-dark-navy mb-2">
                    5. 분쟁 상세 내용
                  </label>
                  <textarea
                    name="disputeDetail"
                    value={disputeForm.disputeDetail}
                    onChange={handleFormChange}
                    placeholder="분쟁 상황을 자세히 설명해주세요"
                    rows="4"
                    className="w-full px-4 py-3 border-2 border-ivory rounded-lg outline-none focus:border-deep-teal transition-all resize-none"
                    required
                  />
                </div>

                <button
                  type="submit"
                  className="w-full bg-deep-teal text-white py-3 rounded-lg font-semibold hover:bg-mint-green transition-all"
                >
                  상담 시작하기
                </button>
              </form>
            </div>
          ) : (
            /* 채팅 화면 */
            <>
              <div
                className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto chat-scrollbar"
                style={{ scrollbarColor: '#0d9488 #f0f0f0', scrollbarWidth: 'thin' }}
              >
                {disputeMessages.map((msg) =>
                  msg.hasSafetyWarning ? (
                    <SafetyWarning
                      key={msg.id}
                      questions={msg.clarifyingQuestions || []}
                    />
                  ) : (
                    <MessageBubble key={msg.id} message={msg} chatType="dispute" />
                  )
                )}
                {/* PR-7: StatusIndicator for real-time agent progress */}
                {disputeStreamingState.isStreaming && (
                  <div className="flex items-start mb-4 md:mb-6">
                    <div className="bg-lavender/30 px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-2xl rounded-bl-sm w-full max-w-md">
                      <StatusIndicator streamingState={disputeStreamingState} />
                    </div>
                  </div>
                )}
                <div ref={disputeMessagesEndRef} />
              </div>

              {/* Input Area */}
              <div className="p-4 sm:p-5 md:p-6 border-t border-ivory flex gap-2 sm:gap-3 md:gap-4">
                <input
                  type="text"
                  placeholder="추가 질문을 입력하세요..."
                  value={disputeInputValue}
                  onChange={(e) => setDisputeInputValue(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleDisputeSend()}
                  className="flex-1 px-4 sm:px-5 md:px-6 py-3 md:py-4 border-2 border-ivory rounded-full outline-none focus:border-deep-teal transition-all text-sm sm:text-base"
                  disabled={disputeStreamingState.isStreaming}
                />
                <button
                  onClick={handleDisputeSend}
                  disabled={disputeStreamingState.isStreaming}
                  className="w-[44px] h-[44px] sm:w-[48px] sm:h-[48px] md:w-[50px] md:h-[50px] bg-deep-teal text-white rounded-full flex items-center justify-center hover:bg-mint-green hover:scale-105 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
                >
                  <Send size={18} className="sm:w-5 sm:h-5" />
                </button>
              </div>
            </>
          )}
          </div>
        )}

        {/* 일반 상담 영역 */}
        {(activeChatType === null || activeChatType === 'general') && (
          <div className="bg-white rounded-xl md:rounded-2xl shadow-lg flex flex-col overflow-hidden">
          {/* 일반 상담 헤더 */}
          <div className="bg-mint-green text-white px-4 sm:px-6 py-3 sm:py-4">
            <h2 className="text-lg sm:text-xl font-bold">일반 상담</h2>
          </div>

          {/* Messages Area */}
          <div
            className="flex-1 p-4 sm:p-6 md:p-8 overflow-y-auto chat-scrollbar"
            style={{ scrollbarColor: '#0d9488 #f0f0f0', scrollbarWidth: 'thin' }}
          >
            {generalMessages.map((msg) =>
              msg.hasSafetyWarning ? (
                <SafetyWarning
                  key={msg.id}
                  questions={msg.clarifyingQuestions || []}
                />
              ) : (
                <MessageBubble key={msg.id} message={msg} chatType="general" />
              )
            )}
            {/* PR-7: StatusIndicator for real-time agent progress */}
            {generalStreamingState.isStreaming && (
              <div className="flex items-start mb-4 md:mb-6">
                <div className="bg-lavender/30 px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-2xl rounded-bl-sm w-full max-w-md">
                  <StatusIndicator streamingState={generalStreamingState} />
                </div>
              </div>
            )}
            <div ref={generalMessagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="p-4 sm:p-5 md:p-6 border-t border-ivory flex gap-2 sm:gap-3 md:gap-4">
            <input
              type="text"
              placeholder="질문을 입력하세요..."
              value={generalInputValue}
              onChange={(e) => setGeneralInputValue(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleGeneralSend()}
              className="flex-1 px-4 sm:px-5 md:px-6 py-3 md:py-4 border-2 border-ivory rounded-full outline-none focus:border-mint-green transition-all text-sm sm:text-base"
              disabled={generalStreamingState.isStreaming}
            />
            <button
              onClick={handleGeneralSend}
              disabled={generalStreamingState.isStreaming}
              className="w-[44px] h-[44px] sm:w-[48px] sm:h-[48px] md:w-[50px] md:h-[50px] bg-mint-green text-white rounded-full flex items-center justify-center hover:bg-deep-teal hover:scale-105 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
            >
              <Send size={18} className="sm:w-5 sm:h-5" />
            </button>
          </div>
          </div>
        )}

      </div>
    </div>
  );
}
