export const storage = {
  get: <T,>(key: string, isSession = false): T | null => {
    try {
      const store = isSession ? sessionStorage : localStorage;
      const item = store.getItem(key);
      return item ? JSON.parse(item) : null;
    } catch {
      return null;
    }
  },

  set: <T,>(key: string, value: T, isSession = false): void => {
    try {
      const store = isSession ? sessionStorage : localStorage;
      store.setItem(key, JSON.stringify(value));
    } catch (error) {
      console.error('Storage set error:', error);
    }
  },

  remove: (key: string, isSession = false): void => {
    try {
      const store = isSession ? sessionStorage : localStorage;
      store.removeItem(key);
    } catch (error) {
      console.error('Storage remove error:', error);
    }
  },

  clear: (isSession = false): void => {
    try {
      const store = isSession ? sessionStorage : localStorage;
      store.clear();
    } catch (error) {
      console.error('Storage clear error:', error);
    }
  },
};
