/**
 * 똑소리 프로젝트 - API 클라이언트
 *
 * 백엔드 API와 통신하기 위한 클라이언트 함수들입니다.
 */

import type { ChatSession } from '../types';

const API_BASE_URL = '/';  // Vite proxy 사용

/**
 * 인증 헤더를 생성합니다.
 */
function getAuthHeaders(token: string | null): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  return headers;
}

/**
 * API 에러를 처리합니다.
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: '알 수 없는 오류' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// ============================================================
// 대화 세션 API
// ============================================================

export interface SessionListResponse {
  sessions: Array<{
    id: string;
    type: string;
    title: string;
    createdAt: string;
    lastMessageAt: string;
    turnCount: number;
  }>;
}

export interface SessionHistoryResponse {
  messages: Array<{
    id: number;
    type: 'user' | 'ai';
    content: string;
    timestamp: string;
  }>;
}

/**
 * 사용자의 대화 세션 목록을 조회합니다.
 */
export async function getUserSessions(
  token: string,
  limit: number = 20,
  offset: number = 0
): Promise<SessionListResponse> {
  const response = await fetch(
    `${API_BASE_URL}chat/sessions?limit=${limit}&offset=${offset}`,
    {
      headers: getAuthHeaders(token),
    }
  );

  return handleResponse<SessionListResponse>(response);
}

/**
 * 특정 세션의 대화 내역을 조회합니다.
 */
export async function getSessionHistory(
  token: string,
  sessionId: string,
  limit: number = 50
): Promise<SessionHistoryResponse> {
  const response = await fetch(
    `${API_BASE_URL}chat/sessions/${sessionId}/history?limit=${limit}`,
    {
      headers: getAuthHeaders(token),
    }
  );

  return handleResponse<SessionHistoryResponse>(response);
}

/**
 * 세션을 삭제합니다.
 */
export async function deleteSession(
  token: string,
  sessionId: string
): Promise<{ success: boolean; message: string }> {
  const response = await fetch(
    `${API_BASE_URL}chat/sessions/${sessionId}`,
    {
      method: 'DELETE',
      headers: getAuthHeaders(token),
    }
  );

  return handleResponse<{ success: boolean; message: string }>(response);
}

// ============================================================
// 게스트 세션 소유권 이전 API
// ============================================================

export interface ClaimSessionsResponse {
  claimed_count: number;
  claimed_session_ids: string[];
}

/**
 * 게스트 세션을 로그인한 사용자 계정으로 이전합니다.
 */
export async function claimGuestSessions(
  token: string,
  sessionIds: string[],
): Promise<ClaimSessionsResponse> {
  const response = await fetch(
    `${API_BASE_URL}chat/sessions/claim`,
    {
      method: 'POST',
      headers: getAuthHeaders(token),
      body: JSON.stringify({ session_ids: sessionIds }),
    }
  );

  return handleResponse<ClaimSessionsResponse>(response);
}

/**
 * 백엔드 세션을 ChatSession 형식으로 변환합니다.
 */
export function convertBackendSessionToLocal(
  backendSession: SessionListResponse['sessions'][0]
): Omit<ChatSession, 'messages'> {
  return {
    id: backendSession.id,
    type: backendSession.type as 'dispute' | 'general',
    title: backendSession.title,
    createdAt: new Date(backendSession.createdAt).getTime(),
    lastMessageAt: new Date(backendSession.lastMessageAt),
    lastUpdated: new Date(backendSession.lastMessageAt).getTime(),
    expiresAt: null,  // 로그인 사용자는 만료 없음
  };
}
