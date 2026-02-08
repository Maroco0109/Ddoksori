import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Admin } from '@/shared/types/admin';
import { STORAGE_KEYS } from '@/shared/config/storage-keys';

interface AdminAuthState {
  admin: Admin | null;
  isAdminAuthenticated: boolean;
  adminToken: string | null;
  setAdmin: (admin: Admin | null) => void;
  setAdminToken: (token: string | null) => void;
  adminLogin: (admin: Admin, token: string) => void;
  adminLogout: () => void;
}

export const useAdminStore = create<AdminAuthState>()(
  persist(
    (set) => ({
      admin: null,
      isAdminAuthenticated: false,
      adminToken: null,
      setAdmin: (admin) => set({ admin, isAdminAuthenticated: !!admin }),
      setAdminToken: (token) => set({ adminToken: token }),
      adminLogin: (admin, token) => {
        set({ admin, adminToken: token, isAdminAuthenticated: true });
      },
      adminLogout: () => set({ admin: null, adminToken: null, isAdminAuthenticated: false }),
    }),
    {
      name: 'admin-auth-storage',
    }
  )
);
