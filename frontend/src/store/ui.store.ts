import { create } from 'zustand';

interface UIState {
  isSidebarOpen: boolean;
  isAuthModalOpen: boolean;
  isChatHistoryOpen: boolean;
  setIsSidebarOpen: (isOpen: boolean) => void;
  toggleSidebar: () => void;
  setIsAuthModalOpen: (isOpen: boolean) => void;
  setIsChatHistoryOpen: (isOpen: boolean) => void;
  toggleChatHistory: () => void;
}

export const useUIStore = create<UIState>((set) => ({
  isSidebarOpen: false,
  isAuthModalOpen: false,
  isChatHistoryOpen: false,
  setIsSidebarOpen: (isOpen) => set({ isSidebarOpen: isOpen }),
  toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
  setIsAuthModalOpen: (isOpen) => set({ isAuthModalOpen: isOpen }),
  setIsChatHistoryOpen: (isOpen) => set({ isChatHistoryOpen: isOpen }),
  toggleChatHistory: () => set((state) => ({ isChatHistoryOpen: !state.isChatHistoryOpen })),
}));
