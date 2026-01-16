/**
 * Chat Service - Sprint 1 S1-4 Integration
 * API service layer for backend /chat endpoint
 */

import { apiClient } from './client';
import type { ChatAPIRequest, ChatAPIResponse } from '@/shared/types';

export const chatService = {
  /**
   * Send message to RAG chatbot backend
   * @param request - Chat request with message and optional filters
   * @returns Promise<ChatAPIResponse> - Answer with citations and safety guardrails
   */
  sendMessage: async (request: ChatAPIRequest): Promise<ChatAPIResponse> => {
    console.log('[ChatService] Sending request to /chat:', request);
    const response = await apiClient.post<ChatAPIResponse>('/chat', request);
    console.log('[ChatService] Received response:', response);
    return response;
  },

  /**
   * Health check endpoint
   * @returns Promise<{ status: string; database: string }>
   */
  healthCheck: async (): Promise<{ status: string; database: string }> => {
    return apiClient.get<{ status: string; database: string }>('/health');
  },
};
