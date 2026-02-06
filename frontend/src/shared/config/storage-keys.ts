export const STORAGE_KEYS = {
  IS_LOGGED_IN: 'isLoggedIn',
  CHAT_SESSIONS: 'chatSessions',
  TEMP_CHAT_SESSIONS: 'tempChatSessions',
  HIDDEN_SESSIONS: 'hiddenSessions',
  AUTH_TOKEN: 'authToken',
  USER_DATA: 'userData',
} as const;

/**
 * 사용자별 채팅 세션 storage key를 생성합니다.
 *
 * @param userId - 사용자 ID (예: "google:118444439259838722473")
 * @returns 사용자별 storage key (예: "chatSessions-google:118444439259838722473")
 */
export function getUserChatSessionsKey(userId: string | null): string {
  if (!userId) {
    return STORAGE_KEYS.CHAT_SESSIONS;
  }
  // 사용자별 고유 key 생성
  return `${STORAGE_KEYS.CHAT_SESSIONS}-${userId}`;
}

/**
 * 사용자별 숨긴 세션 목록 storage key를 생성합니다.
 *
 * @param userId - 사용자 ID (예: "google:118444439259838722473")
 * @returns 사용자별 storage key (예: "hiddenSessions-google:118444439259838722473")
 */
export function getUserHiddenSessionsKey(userId: string | null): string {
  if (!userId) {
    return STORAGE_KEYS.HIDDEN_SESSIONS;
  }
  return `${STORAGE_KEYS.HIDDEN_SESSIONS}-${userId}`;
}
