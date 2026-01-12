/**
 * 비로그인 사용자를 위한 세션 ID 생성
 * IP 기반으로 고유한 세션 ID를 생성합니다 (브라우저 fingerprint 활용)
 */
export const generateGuestSessionId = async (): Promise<string> => {
  // 브라우저 fingerprint 생성
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (ctx) {
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillText('guest-session', 0, 0);
  }

  const fingerprint = [
    navigator.userAgent,
    navigator.language,
    screen.colorDepth,
    screen.width + 'x' + screen.height,
    new Date().getTimezoneOffset(),
    canvas.toDataURL(),
  ].join('|');

  // Simple hash function
  let hash = 0;
  for (let i = 0; i < fingerprint.length; i++) {
    const char = fingerprint.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }

  return `guest_${Math.abs(hash).toString(36)}_${Date.now()}`;
};

/**
 * 세션 만료까지 남은 시간 포맷 (예: "23시간 45분")
 */
export const formatTimeRemaining = (expiresAt: number): string => {
  const now = Date.now();
  const remaining = expiresAt - now;

  if (remaining <= 0) return '만료됨';

  const hours = Math.floor(remaining / (1000 * 60 * 60));
  const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));

  if (hours > 0) {
    return `${hours}시간 ${minutes}분`;
  }
  return `${minutes}분`;
};
