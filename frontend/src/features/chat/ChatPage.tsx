import { useState, useRef, useEffect } from 'react';
import type { ChangeEvent, FormEvent, RefObject } from 'react';
import type { ChatType, DisputeForm, DisputeFormData, MessageWithCitations } from '@/shared/types';
import { Send } from 'lucide-react';
import { useChatStore } from '@/features/chat/chat.store';
import { useAuthStore } from '@/features/auth/auth.store';
import { useStreamingChat } from './hooks/useStreamingChat';
import { extractCitations } from '@/shared/lib/citation';
import { getSessionHistory } from '@/shared/lib/api-client';
import { MessageBubble } from './components/MessageBubble';
import { SafetyWarning } from './components/SafetyWarning';
import { StatusIndicator } from './components/StatusIndicator';
import { VariantSelector } from './components/VariantSelector';

interface ChatPageProps {
  currentSessionId?: string | null;
}

export default function ChatPage({ currentSessionId = null }: ChatPageProps) {
  const storeSessionId = useChatStore((state) => state.currentSessionId);
  const storeActiveChatType = useChatStore((state) => state.activeChatType);
  const setStoreSessionId = useChatStore((state) => state.setCurrentSessionId);
  const setStoreChatType = useChatStore((state) => state.setActiveChatType);
  const saveChatSessionToStore = useChatStore((state) => state.saveChatSession);
  const setDisputeFormData = useChatStore((state) => state.setDisputeFormData);
  const setBackendSessionId = useChatStore((state) => state.setBackendSessionId);
  const resolvedSessionId = currentSessionId ?? storeSessionId;

  // PR-7: SSE Streaming hook for real-time agent status
  const { streamingState: disputeStreamingState, startStream: startDisputeStream } = useStreamingChat();
  const { streamingState: generalStreamingState, startStream: startGeneralStream } = useStreamingChat();

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
  const authToken = useAuthStore((state) => state.token);

  const disputeMessagesEndRef = useRef<HTMLDivElement | null>(null);
  const generalMessagesEndRef = useRef<HTMLDivElement | null>(null);
  const pageTopRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = (ref: RefObject<HTMLDivElement | null>) => {
    ref.current?.scrollIntoView({ behavior: 'smooth' });
  };

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
  }, []);

  // 세션 불러오기
  useEffect(() => {
    if (resolvedSessionId) {
      if (storeSessionId !== resolvedSessionId) {
        setStoreSessionId(resolvedSessionId);
      }

      if (isLoggedIn && authToken) {
        // 로그인 사용자: DB에서 세션 메시지 조회
        setBackendSessionId(resolvedSessionId);
        getSessionHistory(authToken, resolvedSessionId, 50)
          .then((historyResponse) => {
            const messages: MessageWithCitations[] = historyResponse.messages
              .map(msg => ({
                id: msg.id,
                type: msg.type,
                content: msg.content,
                timestamp: new Date(msg.timestamp),
              }))
              .reverse(); // 백엔드는 최신순(DESC) → 시간순으로 변환

            if (messages.length === 0) return;

            // chatType 판별: 첫 user 메시지가 [분쟁 정보]로 시작하면 dispute
            const firstUserMsg = messages.find(m => m.type === 'user');
            const chatType: ChatType = firstUserMsg?.content.startsWith('[분쟁 정보]')
              ? 'dispute'
              : (storeActiveChatType || 'general');

            const greetingPlusMessages: MessageWithCitations[] = [
              {
                id: 0,
                type: 'ai',
                content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
                timestamp: new Date(messages[0]?.timestamp || new Date()),
              },
              ...messages,
            ];

            if (chatType === 'dispute') {
              setDisputeMessages(greetingPlusMessages);
              setGeneralMessages([{
                id: 1, type: 'ai',
                content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
                timestamp: new Date()
              }]);
              setActiveChatType('dispute');
              setIsFormSubmitted(true);
              setStoreChatType('dispute');
              setTimeout(() => {
                disputeMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
              }, 200);
            } else {
              setGeneralMessages(greetingPlusMessages);
              setDisputeMessages([{
                id: 1, type: 'ai',
                content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
                timestamp: new Date()
              }]);
              setActiveChatType('general');
              setStoreChatType('general');
              setTimeout(() => {
                generalMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
              }, 200);
            }
          })
          .catch((error) => {
            console.error('[ChatPage] Failed to load session history:', error);
          });
      } else {
        // 비로그인 사용자: store의 chatSessions에서 세션 찾기
        const currentSessions = useChatStore.getState().chatSessions;
        const session = currentSessions.find(s => s.id === resolvedSessionId);

        if (session) {
          setBackendSessionId(session.id);
          const restoredMessages = session.messages
            .map(msg => ({
              ...msg,
              timestamp: msg.timestamp instanceof Date ? msg.timestamp : new Date(msg.timestamp)
            }))
            .sort((a, b) => a.id - b.id);

          const chatType = storeActiveChatType || session.type;

          if (chatType === 'dispute') {
            setDisputeMessages(restoredMessages);
            setGeneralMessages([{
              id: 1, type: 'ai',
              content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
              timestamp: new Date()
            }]);
            setActiveChatType('dispute');
            setIsFormSubmitted(true);
            setStoreChatType('dispute');
            setTimeout(() => {
              disputeMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }, 200);
          } else {
            setGeneralMessages(restoredMessages);
            setDisputeMessages([{
              id: 1, type: 'ai',
              content: '안녕하세요! 똑소리 AI 상담입니다. 무엇을 도와드릴까요?',
              timestamp: new Date()
            }]);
            setActiveChatType('general');
            setStoreChatType('general');
            setTimeout(() => {
              generalMessagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
            }, 200);
          }
        } else if (storeActiveChatType) {
          setActiveChatType(storeActiveChatType);
          if (storeActiveChatType === 'dispute') {
            setIsFormSubmitted(false);
          }
        }
      }
    } else {
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
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedSessionId]);

  // 분쟁 메시지 변경 시: 스크롤 + 저장
  useEffect(() => {
    if (disputeMessages.length > 1) {
      scrollToBottom(disputeMessagesEndRef);
    }
    const hasUserMessage = disputeMessages.some(m => m.type === 'user');
    if (disputeMessages.length > 1 && hasUserMessage) {
      saveChatSessionToStore('dispute', disputeMessages, isLoggedIn);
    }
  }, [disputeMessages, saveChatSessionToStore, isLoggedIn]);

  // 일반 메시지 변경 시: 스크롤 + 저장
  useEffect(() => {
    if (generalMessages.length > 1) {
      scrollToBottom(generalMessagesEndRef);
    }
    const hasUserMessage = generalMessages.some(m => m.type === 'user');
    if (generalMessages.length > 1 && hasUserMessage) {
      saveChatSessionToStore('general', generalMessages, isLoggedIn);
    }
  }, [generalMessages, saveChatSessionToStore, isLoggedIn]);

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

    setDisputeMessages(prev => [...prev, formMessage]);
    setIsFormSubmitted(true);
    setStoreChatType('dispute');
    setActiveChatType('dispute');

    const aiMessageId = disputeMessages.length + 2;

    try {
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
   */
  const cleanUserInput = (input: string): string => {
    const text = input.trim();

    const answerHeaders = [
      '[답변 요약]',
      '[규정]',
      '[유사 사례]',
      '[주의 사항]',
      '[출처]',
      '[이전 대화]',
    ];

    const startsWithTemplate = answerHeaders.some(header => text.startsWith(header));

    if (!startsWithTemplate) {
      return text;
    }

    const lines = text.split('\n');

    for (let i = lines.length - 1; i >= 0; i--) {
      const line = lines[i].trim();

      if (!line) continue;
      if (line.startsWith('#') || line.startsWith('-') || line.startsWith('●')) continue;
      if (line.startsWith('[') && line.endsWith(']')) continue;
      if (/^\d+\./.test(line)) continue;
      if (line.startsWith('*') || line.startsWith('¹') || line.startsWith('²')) continue;

      if (line.length >= 5) {
        return line;
      }
    }

    return text;
  };

  // 분쟁 상담 메시지 전송 핸들러
  const handleDisputeSend = async () => {
    if (!disputeInputValue.trim() || disputeStreamingState.isStreaming) return;

    const cleanedInput = cleanUserInput(disputeInputValue);

    const newMessage: MessageWithCitations = {
      id: disputeMessages.length + 1,
      type: 'user' as const,
      content: cleanedInput,
      timestamp: new Date()
    };

    setDisputeMessages(prev => [...prev, newMessage]);
    setDisputeInputValue('');

    const aiMessageId = disputeMessages.length + 2;

    try {
      const response = await startDisputeStream({
        message: cleanedInput,
        chat_type: 'dispute',
        top_k: 5,
      });

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

  // 일반 상담 메시지 전송 핸들러
  const handleGeneralSend = async () => {
    if (!generalInputValue.trim() || generalStreamingState.isStreaming) return;

    const cleanedInput = cleanUserInput(generalInputValue);

    const newMessage: MessageWithCitations = {
      id: generalMessages.length + 1,
      type: 'user' as const,
      content: cleanedInput,
      timestamp: new Date()
    };

    setGeneralMessages(prev => [...prev, newMessage]);
    setGeneralInputValue('');
    setActiveChatType('general');
    setStoreChatType('general');

    const aiMessageId = generalMessages.length + 2;

    try {
      const response = await startGeneralStream({
        message: cleanedInput,
        chat_type: 'general',
        top_k: 5,
      });

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
          <div className="bg-deep-teal text-white px-4 sm:px-6 py-3 sm:py-4 flex items-center justify-between gap-3">
            <h2 className="text-lg sm:text-xl font-bold">분쟁 상담</h2>
            <VariantSelector />
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
