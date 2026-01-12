/**
 * useChatMutation - React Query hook for chat API
 * Sprint 1 S1-4 Integration
 */

import { useMutation } from '@tanstack/react-query';
import { chatService } from '@/shared/api/chat.service';
import type { ChatAPIRequest, ChatAPIResponse } from '@/shared/types';

/**
 * React Query mutation hook for sending chat messages
 *
 * @example
 * const chatMutation = useChatMutation();
 *
 * // Send message
 * const response = await chatMutation.mutateAsync({
 *   message: "내 문제를 해결해주세요",
 *   top_k: 5
 * });
 *
 * // Check loading state
 * if (chatMutation.isPending) { ... }
 *
 * // Handle errors
 * if (chatMutation.isError) { console.error(chatMutation.error); }
 */
export function useChatMutation() {
  return useMutation<ChatAPIResponse, Error, ChatAPIRequest>({
    mutationFn: (request: ChatAPIRequest) => chatService.sendMessage(request),
    onError: (error) => {
      console.error('Chat API error:', error);
    },
  });
}
