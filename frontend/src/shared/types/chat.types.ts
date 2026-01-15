/**
 * Chat API Types - Sprint 1 S1-4 Integration
 * Backend API contract interfaces for FastAPI /chat endpoint
 */

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
  createdAt: Date;
  lastMessageAt: Date;
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
