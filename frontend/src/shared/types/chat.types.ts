/**
 * Chat API Types - Sprint 1 S1-4 Integration
 * Backend API contract interfaces for FastAPI /chat endpoint
 */

// Core Chat Types
export type ChatType = 'dispute' | 'general';

export interface DisputeForm {
  purchaseDate: string;
  purchasePlace: string;
  platform: string;
  purchaseItem: string;
  purchaseAmount: string;
  disputeDetail: string;
}

// ============================================================================
// Backend API Request/Response Types
// ============================================================================

/**
 * Onboarding data for backend API (snake_case)
 * Maps from frontend DisputeFormData (camelCase) to backend format
 */
export interface OnboardingAPIData {
  purchase_date?: string;
  purchase_place?: string;
  purchase_platform?: string;
  purchase_item?: string;
  purchase_amount?: string;
  dispute_details?: string;
}

/**
 * Backend request payload for /chat endpoint
 */
export interface ChatAPIRequest {
  message: string;
  session_id?: string;
  chat_type?: 'dispute' | 'general';
  onboarding?: OnboardingAPIData;
  top_k?: number;
  chunk_types?: string[];
  agencies?: string[];
}

/**
 * Source metadata from backend citation system (S1-1)
 */
export interface SourceMetadata {
  doc_id: string;
  chunk_id: string;
  chunk_type: string;
  source_org: string;
  url: string | null;
  decision_date: string | null;
  collected_at: string | null;
  doc_title: string;
  similarity: number;
}

export interface AgencyInfo {
  name: string;
  full_name: string;
  description: string;
  url: string;
  is_restricted?: boolean;
  restriction_reason?: string;
}

export interface ChatAPIResponse {
  session_id: string;
  answer: string;
  chunks_used: number;
  model: string;
  sources: SourceMetadata[];
  has_sufficient_evidence: boolean;
  clarifying_questions: string[];
  followup_questions?: string[];
  is_restricted?: boolean;
  agency_code?: string;
  agency_info?: AgencyInfo;
}

// ============================================================================
// Frontend Citation Types
// ============================================================================

/**
 * Frontend citation object linking [N] in text to source metadata
 */
export interface Citation {
  id: number;              // Citation number [1], [2], [3]
  sourceIndex: number;     // Index into sources array
  source: SourceMetadata;  // Full source metadata
}

// ============================================================================
// Enhanced Message Types
// ============================================================================

/**
 * Base message interface (existing in frontend)
 */
export interface Message {
  id: number;
  type: 'ai' | 'user';
  content: string;
  timestamp: Date;
}

export interface MessageWithCitations extends Message {
  citations?: Citation[];
  hasSafetyWarning?: boolean;
  clarifyingQuestions?: string[];
  followupQuestions?: string[];
  isRestricted?: boolean;
  agencyCode?: string;
  agencyInfo?: AgencyInfo;
}

// ============================================================================
// Chat Session Types
// ============================================================================

/**
 * Chat session metadata for persistence
 */
export interface ChatSession {
  id: string;
  type: 'dispute' | 'general';
  title: string;
  messages: MessageWithCitations[];
  createdAt: Date | number;
  lastMessageAt?: Date;
  // Legacy compatibility (from chat.ts)
  expiresAt?: number | null;
  lastUpdated?: number;
}

/**
 * Onboarding form data for dispute consultation
 */
export interface DisputeFormData {
  purchaseDate: string;
  purchasePlace: string;
  purchasePlatform: string;
  purchaseItem: string;
  purchaseAmount: string;
  disputeDetails: string;
}

// ============================================================================
// PR-5: SSE Streaming Types
// ============================================================================

/**
 * SSE Event Types from /chat/stream endpoint
 */
export type SSEEventType = 'status' | 'complete' | 'error';

/**
 * SSE Status Event - Node progress update
 */
export interface SSEStatusData {
  node: string;
  status: string;
  progress: number;
}

/**
 * SSE Source info for complete event
 */
export interface SSESourceInfo {
  type: 'dispute' | 'law' | 'counsel' | 'criteria';
  title: string;
  source_org?: string;
  similarity: number;
  content?: string;
  // dispute-specific
  case_uid?: string;
  product_name?: string;
  // law-specific
  law_name?: string;
  article?: string;
}

// Restricted domain agency recommendation from backend
export interface AgencyRecommendation {
  agency: string;                              // domain code: "finance", "medical" 등
  agency_info: {
    name: string;                              // 기관명: "금융분쟁조정위원회"
    organization: string;                      // 소속: "금융감독원"
    url: string;
    phone: string;
  };
  dispute_type: string;
  reason: string;
  confidence: number;
  is_restricted: boolean;
  full_name?: string;
  description?: string;
  url?: string;
  agency_code?: string;
  restriction_reason?: string;
}

export interface SimilarCases {
  disputes: Array<{ doc_title?: string; source_org?: string; similarity: number }>;
  counsels: Array<{ doc_title?: string; source_org?: string; similarity: number }>;
}

export interface LawReference {
  law_name?: string;
  article?: string;
  full_path?: string;
  similarity: number;
}

export interface CriteriaReference {
  title?: string;
  category?: string;
  similarity: number;
}

/**
 * SSE Complete Event - Final result
 */
export interface SSECompleteData {
  session_id: string;
  answer: string;
  sources: SSESourceInfo[];
  clarifying_questions: string[];
  followup_questions?: string[];
  has_sufficient_evidence?: boolean;
  domain?: AgencyRecommendation;
  similar_cases?: SimilarCases;
  related_laws?: LawReference[];
  related_criteria?: CriteriaReference[];
}

/**
 * SSE Error Event
 */
export interface SSEErrorData {
  message: string;
}

/**
 * SSE Token Event - Individual token from LLM streaming
 */
export interface SSETokenData {
  content: string;  // 개별 토큰
  model: string;    // 현재 사용중인 모델
}

/**
 * SSE Fallback Event - Model switching notification
 */
export interface SSEFallbackData {
  model: string;    // 전환할 모델
  message: string;  // 알림 메시지
}

/**
 * SSE Event Union Type
 */
export type SSEEvent =
  | { type: 'status'; data: SSEStatusData }
  | { type: 'token'; data: SSETokenData }
  | { type: 'fallback'; data: SSEFallbackData }
  | { type: 'complete'; data: SSECompleteData }
  | { type: 'error'; data: SSEErrorData };

/**
 * Streaming state for UI
 */
export interface StreamingState {
  isStreaming: boolean;
  currentNode: string | null;
  status: string;
  progress: number;
  error: string | null;
}
