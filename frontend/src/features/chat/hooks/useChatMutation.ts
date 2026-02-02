import { useMutation } from '@tanstack/react-query';
import { chatService } from '@/shared/api/chat.service';
import { useChatStore } from '@/features/chat/chat.store';
import type { ChatAPIRequest, ChatAPIResponse, OnboardingAPIData } from '@/shared/types';

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

export function useChatMutation() {
  const setBackendSessionId = useChatStore((state) => state.setBackendSessionId);

  return useMutation<ChatAPIResponse, Error, ChatAPIRequest>({
    mutationFn: async (request: ChatAPIRequest) => {
      const backendSessionId = useChatStore.getState().backendSessionId;
      // Use onboarding from request if provided, otherwise try to get from store
      const onboarding = request.onboarding || convertDisputeFormToOnboarding();
      
      const enhancedRequest: ChatAPIRequest = {
        ...request,
        session_id: backendSessionId || undefined,
        chat_type: request.chat_type || 'dispute',
        onboarding: onboarding,
      };
      
      return chatService.sendMessage(enhancedRequest);
    },
    onSuccess: (response) => {
      setBackendSessionId(response.session_id);
    },
    onError: (error) => {
      console.error('Chat API error:', error);
    },
  });
}
