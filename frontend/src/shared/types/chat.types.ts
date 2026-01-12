/**
 * Chat API Types - Sprint 1 S1-4 Integration
 * Backend API contract interfaces for FastAPI /chat endpoint
 */

// ============================================================================
// Backend API Request/Response Types
// ============================================================================

/**
 * Backend request payload for /chat endpoint
 */
export interface ChatAPIRequest {
  message: string;
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

/**
 * Backend response payload from /chat endpoint
 */
export interface ChatAPIResponse {
  answer: string;
  chunks_used: number;
  model: string;
  sources: SourceMetadata[];
  has_sufficient_evidence: boolean;
  clarifying_questions: string[];
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

/**
 * Enhanced message with citation support and safety warnings
 * Extends base Message with API-specific fields
 */
export interface MessageWithCitations extends Message {
  citations?: Citation[];           // Extracted citations from answer
  hasSafetyWarning?: boolean;       // true if this is a safety warning message
  clarifyingQuestions?: string[];   // Questions to display in warning
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
