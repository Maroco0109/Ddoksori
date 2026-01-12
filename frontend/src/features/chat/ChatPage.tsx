import { useState, useRef, useEffect } from 'react';
import type { ChangeEvent, FormEvent, RefObject } from 'react';
import type { ChatSession, ChatType, DisputeForm, MessageWithCitations } from '@/shared/types';
import { Send } from 'lucide-react';
import { useChatStore } from '@/features/chat/chat.store';
import { useChatMutation } from './hooks/useChatMutation';
import { extractCitations } from '@/shared/lib/citation';
import { simulateStreaming } from '@/shared/lib/streaming';
import { MessageBubble } from './components/MessageBubble';
import { SafetyWarning } from './components/SafetyWarning';

interface ChatPageProps {
  currentSessionId?: string | null;
  onSessionCreate?: (sessionId: string) => void;
}

export default function ChatPage({ currentSessionId = null, onSessionCreate }: ChatPageProps) {
  const storeSessionId = useChatStore((state) => state.currentSessionId);
  const setStoreSessionId = useChatStore((state) => state.setCurrentSessionId);
  const setStoreChatType = useChatStore((state) => state.setActiveChatType);
  const setChatSessions = useChatStore((state) => state.setChatSessions);
  const resolvedSessionId = currentSessionId ?? storeSessionId;

  // 현재 세션 ID
  const [sessionId, setSessionId] = useState<string | null>(resolvedSessionId);

  // React Query mutation for API calls
  const chatMutation = useChatMutation();

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
  const isLoggedIn = localStorage.getItem('isLoggedIn') === 'true';

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
    if (resolvedSessionId) {
      setSessionId(resolvedSessionId);

      if (storeSessionId !== resolvedSessionId) {
        setStoreSessionId(resolvedSessionId);
      }

      const storage = isLoggedIn ? localStorage : sessionStorage;
      const storageKey = isLoggedIn ? 'chatSessions' : 'tempChatSessions';

      try {
        const sessions = JSON.parse(storage.getItem(storageKey) || '[]');
        const session = sessions.find(s => s.id === resolvedSessionId);

        if (session) {
          const restoredMessages = session.messages.map(msg => ({
            ...msg,
            timestamp: new Date(msg.timestamp)
          }));

          if (session.type === 'dispute') {
            setDisputeMessages(restoredMessages);
            setActiveChatType('dispute');
            setIsFormSubmitted(true);
            setStoreChatType('dispute');
            // 기존 상담 불러올 때 스크롤을 아래로 이동 (RootLayout 스크롤 처리 이후 실행)
            setTimeout(() => {
              disputeMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }, 200);
          } else {
            setGeneralMessages(restoredMessages);
            setActiveChatType('general');
            setStoreChatType('general');
            // 기존 상담 불러올 때 스크롤을 아래로 이동 (RootLayout 스크롤 처리 이후 실행)
            setTimeout(() => {
              generalMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }, 200);
          }
        }
      } catch (e) {
        console.error('Failed to load session:', e);
      }
    } else {
      // 새 채팅 시작 - 초기 상태로 리셋
      setSessionId(null);
      setActiveChatType(null);
      setIsFormSubmitted(false);
      setStoreSessionId(null);
      setStoreChatType(null);
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
      // 새 상담 시작 시 스크롤은 RootLayout에서 처리
    }
  }, [resolvedSessionId, isLoggedIn, setStoreChatType, setStoreSessionId, storeSessionId]);

  // 채팅 세션 저장 함수
  const saveChatSession = (type: ChatType, messages: Message[]) => {
    const storage = isLoggedIn ? localStorage : sessionStorage;
    const storageKey = isLoggedIn ? 'chatSessions' : 'tempChatSessions';

    let sessions: ChatSession[] = [];
    try {
      sessions = JSON.parse(storage.getItem(storageKey) || '[]');
    } catch (e) {
      sessions = [];
    }

    const newSessionId = sessionId || Date.now().toString();

    // 첫 사용자 메시지로 타이틀 생성
    const userMessage = messages.find(msg => msg.type === 'user');
    const title = userMessage
      ? userMessage.content.substring(0, 30) + (userMessage.content.length > 30 ? '...' : '')
      : type === 'dispute' ? '분쟁 상담' : '일반 상담';

    const sessionIndex = sessions.findIndex(s => s.id === newSessionId);
    const now = Date.now();

    // 비로그인 사용자는 1일(86400000ms) 만료 시간 설정
    const expiresAt = !isLoggedIn ? now + 86400000 : null;

    const sessionData = {
      id: newSessionId,
      type,
      title,
      createdAt: sessionIndex >= 0 ? sessions[sessionIndex].createdAt : now,
      expiresAt: sessionIndex >= 0 ? sessions[sessionIndex].expiresAt : expiresAt,
      lastUpdated: now,
      messages: messages.map(msg => ({
        ...msg,
        timestamp: msg.timestamp instanceof Date ? msg.timestamp.getTime() : msg.timestamp
      }))
    };

    if (sessionIndex >= 0) {
      sessions[sessionIndex] = sessionData;
    } else {
      sessions.unshift(sessionData);
    }

    storage.setItem(storageKey, JSON.stringify(sessions));
    setChatSessions(sessions);

    if (!sessionId) {
      setSessionId(newSessionId);
      setStoreSessionId(newSessionId);
      setStoreChatType(type);
      if (onSessionCreate) {
        onSessionCreate(newSessionId);
      }
    }
  };

  const disputeMessagesEndRef = useRef<HTMLDivElement | null>(null);
  const generalMessagesEndRef = useRef<HTMLDivElement | null>(null);
  const pageTopRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = (ref: RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    // 메시지가 2개 이상일 때만 스크롤 (초기 상태에서는 스크롤하지 않음)
    if (disputeMessages.length > 1) {
      scrollToBottom(disputeMessagesEndRef);
      saveChatSession('dispute', disputeMessages);
    }
  }, [disputeMessages]);

  useEffect(() => {
    // 메시지가 2개 이상일 때만 스크롤 (초기 상태에서는 스크롤하지 않음)
    if (generalMessages.length > 1) {
      scrollToBottom(generalMessagesEndRef);
      saveChatSession('general', generalMessages);
    }
  }, [generalMessages]);

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

    // 폼 데이터를 메시지로 변환
    const platformInfo = disputeForm.platform ? `\n플랫폼: ${disputeForm.platform}` : '';
    const formMessage: MessageWithCitations = {
      id: disputeMessages.length + 1,
      type: 'user' as const,
      content: `[분쟁 정보]\n구매일자: ${disputeForm.purchaseDate}\n구매처: ${disputeForm.purchasePlace}${platformInfo}\n구매품목: ${disputeForm.purchaseItem}\n구매금액: ${disputeForm.purchaseAmount}원\n분쟁 상세: ${disputeForm.disputeDetail}`,
      timestamp: new Date()
    };

    setDisputeMessages([...disputeMessages, formMessage]);
    setIsFormSubmitted(true);
    setStoreChatType('dispute');
    setActiveChatType('dispute');
    setIsDisputeLoading(true);

    // Create placeholder AI message for streaming
    const aiMessageId = disputeMessages.length + 2;
    const placeholderAI: MessageWithCitations = {
      id: aiMessageId,
      type: 'ai' as const,
      content: '',
      timestamp: new Date(),
    };
    setDisputeMessages((prev) => [...prev, placeholderAI]);

    try {
      // Call backend API
      const response = await chatMutation.mutateAsync({
        message: formMessage.content,
        top_k: 5,
      });

      // Simulate streaming for better UX
      let streamedText = '';
      await simulateStreaming(response.answer, (chunk) => {
        streamedText += chunk;
        setDisputeMessages((prev) =>
          prev.map((msg) =>
            msg.id === aiMessageId ? { ...msg, content: streamedText } : msg
          )
        );
      });

      // After streaming, extract citations
      const citations = extractCitations(response.answer, response.sources);
      setDisputeMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? { ...msg, content: response.answer, citations }
            : msg
        )
      );

      // Handle safety guardrails
      if (!response.has_sufficient_evidence && response.clarifying_questions.length > 0) {
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
    } catch (error) {
      console.error('Chat API error:', error);
      setDisputeMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? {
                ...msg,
                content:
                  '죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
              }
            : msg
        )
      );
    } finally {
      setIsDisputeLoading(false);
    }
  };

  // 분쟁 상담 메시지 전송 핸들러
  const handleDisputeSend = async () => {
    if (!disputeInputValue.trim() || isDisputeLoading) return;

    const newMessage: MessageWithCitations = {
      id: disputeMessages.length + 1,
      type: 'user' as const,
      content: disputeInputValue,
      timestamp: new Date()
    };

    setDisputeMessages([...disputeMessages, newMessage]);
    setDisputeInputValue('');
    setIsDisputeLoading(true);

    // Create placeholder AI message for streaming
    const aiMessageId = disputeMessages.length + 2;
    const placeholderAI: MessageWithCitations = {
      id: aiMessageId,
      type: 'ai' as const,
      content: '',
      timestamp: new Date(),
    };
    setDisputeMessages((prev) => [...prev, placeholderAI]);

    try {
      // Call backend API
      const response = await chatMutation.mutateAsync({
        message: newMessage.content,
        top_k: 5,
      });

      // Simulate streaming for better UX
      let streamedText = '';
      await simulateStreaming(response.answer, (chunk) => {
        streamedText += chunk;
        setDisputeMessages((prev) =>
          prev.map((msg) =>
            msg.id === aiMessageId ? { ...msg, content: streamedText } : msg
          )
        );
      });

      // After streaming, extract citations
      const citations = extractCitations(response.answer, response.sources);
      setDisputeMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? { ...msg, content: response.answer, citations }
            : msg
        )
      );

      // Handle safety guardrails
      if (!response.has_sufficient_evidence && response.clarifying_questions.length > 0) {
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
    } catch (error) {
      console.error('Chat API error:', error);
      setDisputeMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? {
                ...msg,
                content:
                  '죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
              }
            : msg
        )
      );
    } finally {
      setIsDisputeLoading(false);
    }
  };

  // 일반 상담 메시지 전송 핸들러
  const handleGeneralSend = async () => {
    if (!generalInputValue.trim() || isGeneralLoading) return;

    const newMessage: MessageWithCitations = {
      id: generalMessages.length + 1,
      type: 'user' as const,
      content: generalInputValue,
      timestamp: new Date()
    };

    setGeneralMessages([...generalMessages, newMessage]);
    setGeneralInputValue('');
    setActiveChatType('general');
    setStoreChatType('general');
    setIsGeneralLoading(true);

    // Create placeholder AI message for streaming
    const aiMessageId = generalMessages.length + 2;
    const placeholderAI: MessageWithCitations = {
      id: aiMessageId,
      type: 'ai' as const,
      content: '',
      timestamp: new Date(),
    };
    setGeneralMessages((prev) => [...prev, placeholderAI]);

    try {
      // Call backend API
      const response = await chatMutation.mutateAsync({
        message: newMessage.content,
        top_k: 5,
      });

      // Simulate streaming for better UX
      let streamedText = '';
      await simulateStreaming(response.answer, (chunk) => {
        streamedText += chunk;
        setGeneralMessages((prev) =>
          prev.map((msg) =>
            msg.id === aiMessageId ? { ...msg, content: streamedText } : msg
          )
        );
      });

      // After streaming, extract citations
      const citations = extractCitations(response.answer, response.sources);
      setGeneralMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? { ...msg, content: response.answer, citations }
            : msg
        )
      );

      // Handle safety guardrails
      if (!response.has_sufficient_evidence && response.clarifying_questions.length > 0) {
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
    } catch (error) {
      console.error('Chat API error:', error);
      setGeneralMessages((prev) =>
        prev.map((msg) =>
          msg.id === aiMessageId
            ? {
                ...msg,
                content:
                  '죄송합니다. 답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
              }
            : msg
        )
      );
    } finally {
      setIsGeneralLoading(false);
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
                {isDisputeLoading && (
                  <div className="flex items-start mb-4 md:mb-6">
                    <div className="bg-lavender/30 px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-2xl rounded-bl-sm">
                      <div className="flex gap-2">
                        <div className="w-2 h-2 bg-gray-purple rounded-full animate-bounce"></div>
                        <div className="w-2 h-2 bg-gray-purple rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                        <div className="w-2 h-2 bg-gray-purple rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                      </div>
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
                  disabled={isDisputeLoading}
                />
                <button
                  onClick={handleDisputeSend}
                  disabled={isDisputeLoading}
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
            {isGeneralLoading && (
              <div className="flex items-start mb-4 md:mb-6">
                <div className="bg-lavender/30 px-4 sm:px-5 md:px-6 py-3 md:py-4 rounded-2xl rounded-bl-sm">
                  <div className="flex gap-2">
                    <div className="w-2 h-2 bg-gray-purple rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-gray-purple rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                    <div className="w-2 h-2 bg-gray-purple rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                  </div>
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
              disabled={isGeneralLoading}
            />
            <button
              onClick={handleGeneralSend}
              disabled={isGeneralLoading}
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
