export type ChatType = 'dispute' | 'general';

export interface Message {
  id: number;
  type: 'ai' | 'user';
  content: string;
  timestamp: Date;
}

export interface DisputeForm {
  purchaseDate: string;
  purchasePlace: string;
  platform: string;
  purchaseItem: string;
  purchaseAmount: string;
  disputeDetail: string;
}

export interface ChatSession {
  id: string;
  type: ChatType;
  title: string;
  createdAt: number;
  lastUpdated: number;
  expiresAt: number | null;
  messages: Array<{
    id: number;
    type: 'ai' | 'user';
    content: string;
    timestamp: number;
  }>;
}

export interface ChatState {
  activeChatType: ChatType | null;
  currentSessionId: string | null;
  chatSessions: ChatSession[];
  disputeMessages: Message[];
  generalMessages: Message[];
  isDisputeLoading: boolean;
  isGeneralLoading: boolean;
  isFormSubmitted: boolean;
}
