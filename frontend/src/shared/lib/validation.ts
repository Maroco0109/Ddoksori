export const validateEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
};

export const validateRequired = (value: string): boolean => {
  return value.trim().length > 0;
};

export const validateLength = (
  value: string,
  min: number,
  max: number
): boolean => {
  const length = value.trim().length;
  return length >= min && length <= max;
};

export const validatePostForm = (
  category: string,
  title: string,
  content: string
): { isValid: boolean; error?: string } => {
  if (!category) {
    return { isValid: false, error: '카테고리를 선택해주세요.' };
  }

  if (!validateRequired(title)) {
    return { isValid: false, error: '제목을 입력해주세요.' };
  }

  if (!validateLength(title, 1, 100)) {
    return { isValid: false, error: '제목은 1-100자 사이여야 합니다.' };
  }

  if (!validateRequired(content)) {
    return { isValid: false, error: '내용을 입력해주세요.' };
  }

  if (!validateLength(content, 1, 5000)) {
    return { isValid: false, error: '내용은 1-5000자 사이여야 합니다.' };
  }

  return { isValid: true };
};
