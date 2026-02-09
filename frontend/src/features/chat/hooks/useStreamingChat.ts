/**
 * PR-5: SSE Streaming Chat Hook
 * Real-time progress updates using Server-Sent Events
 */

import { useState, useCallback, useRef } from 'react';
import { useChatStore } from '@/features/chat/chat.store';
import { useAuthStore } from '@/features/auth/auth.store';
import { API_BASE_URL } from '@/shared/api/client';
import type {
  ChatAPIRequest,
  SSEEvent,
  SSECompleteData,
  StreamingState,
  OnboardingAPIData,
} from '@/shared/types';

/**
 * Convert dispute form data to onboarding API format
 */
function convertDisputeFormToOnboarding(): OnboardingAPIData | undefined {
  const disputeFormData = useChatStore.getState().disputeFormData;
  if (!disputeFormData) return undefined;

  return {
    purchase_date: disputeFormData.purchaseDate || undefined,
    purchase_place: disputeFormData.purchasePlace || undefined,
    purchase_platform: disputeFormData.purchasePlatform || undefined,
    purchase_item: disputeFormData.purchaseItem || undefined,
    purchase_amount: disputeFormData.purchaseAmount || undefined,
    dispute_details: disputeFormData.disputeDetails || undefined,
  };
}

interface UseStreamingChatOptions {
  onStatusUpdate?: (status: string, progress: number, node: string) => void;
  onComplete?: (data: SSECompleteData) => void;
  onError?: (error: string) => void;
}

interface UseStreamingChatReturn {
  streamingState: StreamingState;
  startStream: (request: ChatAPIRequest) => Promise<SSECompleteData | null>;
  cancelStream: () => void;
}

/**
 * SSE-based streaming chat hook for real-time progress updates
 */
export function useStreamingChat(options: UseStreamingChatOptions = {}): UseStreamingChatReturn {
  const { onStatusUpdate, onComplete, onError } = options;
  const setBackendSessionId = useChatStore((state) => state.setBackendSessionId);

  const [streamingState, setStreamingState] = useState<StreamingState>({
    isStreaming: false,
    currentNode: null,
    status: '',
    progress: 0,
    error: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * Cancel ongoing stream
   */
  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setStreamingState((prev) => ({
      ...prev,
      isStreaming: false,
      error: 'Stream cancelled',
    }));
  }, []);

  /**
   * Start SSE stream to /chat/stream endpoint
   */
  const startStream = useCallback(
    async (request: ChatAPIRequest): Promise<SSECompleteData | null> => {
      // Cancel any existing stream
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      // Reset state
      setStreamingState({
        isStreaming: true,
        currentNode: null,
        status: '연결중...',
        progress: 0,
        error: null,
      });

      const backendSessionId = useChatStore.getState().backendSessionId;
      const onboarding = request.onboarding || convertDisputeFormToOnboarding();

      const enhancedRequest: ChatAPIRequest = {
        ...request,
        session_id: backendSessionId || undefined,
        chat_type: request.chat_type || 'dispute',
        onboarding: onboarding,
      };

      // Get JWT token from auth store for user identification
      const token = useAuthStore.getState().token;
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      };

      // Include Authorization header if user is logged in
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }

      try {
        const response = await fetch(`${API_BASE_URL}/chat/stream`, {
          method: 'POST',
          headers,
          body: JSON.stringify(enhancedRequest),
          signal: abortController.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('Response body is not readable');
        }

        const decoder = new TextDecoder();
        let buffer = '';
        let completeData: SSECompleteData | null = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Parse SSE events from buffer
          const lines = buffer.split('\n');
          buffer = lines.pop() || ''; // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const eventData = JSON.parse(line.slice(6)) as SSEEvent;

                if (eventData.type === 'status') {
                  const { node, status, progress } = eventData.data;
                  setStreamingState((prev) => ({
                    ...prev,
                    currentNode: node,
                    status,
                    progress,
                  }));
                  onStatusUpdate?.(status, progress, node);
                } else if (eventData.type === 'complete') {
                  completeData = eventData.data;
                  // 무조건 backendSessionId 업데이트
                  setBackendSessionId(completeData.session_id);
                  setStreamingState({
                    isStreaming: false,
                    currentNode: null,
                    status: '완료',
                    progress: 100,
                    error: null,
                  });
                  onComplete?.(completeData);
                } else if (eventData.type === 'error') {
                  const errorMsg = eventData.data.message;
                  setStreamingState((prev) => ({
                    ...prev,
                    isStreaming: false,
                    error: errorMsg,
                  }));
                  onError?.(errorMsg);
                }
              } catch (parseError) {
                console.warn('[useStreamingChat] Failed to parse SSE event:', line);
              }
            }
          }
        }

        return completeData;
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          return null;
        }

        const errorMsg = error instanceof Error ? error.message : 'Unknown error';
        setStreamingState({
          isStreaming: false,
          currentNode: null,
          status: '',
          progress: 0,
          error: errorMsg,
        });
        onError?.(errorMsg);
        return null;
      } finally {
        abortControllerRef.current = null;
      }
    },
    [onStatusUpdate, onComplete, onError, setBackendSessionId]
  );

  return {
    streamingState,
    startStream,
    cancelStream,
  };
}
