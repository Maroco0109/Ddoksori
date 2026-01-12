export const formatDate = (date: Date | string | number): string => {
  const d = new Date(date);
  return d.toLocaleDateString('ko-KR').replace(/\. /g, '.').slice(0, -1);
};

export const formatTime = (date: Date | string | number): string => {
  const d = new Date(date);
  return d.toLocaleTimeString('ko-KR', {
    hour: '2-digit',
    minute: '2-digit',
  });
};

export const formatDateTime = (date: Date | string | number): string => {
  return `${formatDate(date)} ${formatTime(date)}`;
};

export const getRemainingTime = (
  expiresAt: number
): { value: number; unit: string } | null => {
  if (!expiresAt) return null;
  const now = Date.now();
  const remaining = expiresAt - now;
  if (remaining <= 0) return { value: 0, unit: '시간' };

  const hours = Math.floor(remaining / 3600000);
  const minutes = Math.ceil((remaining % 3600000) / 60000);

  if (hours > 0) {
    return { value: hours, unit: '시간' };
  } else {
    return { value: minutes, unit: '분' };
  }
};
