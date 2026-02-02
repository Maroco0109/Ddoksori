import { describe, it, expect, beforeEach } from 'vitest';
import { useAdminStore } from '../admin.store';
import type { Admin } from '@/shared/types/admin';

describe('Admin Store', () => {
  beforeEach(() => {
    // Reset store state before each test
    useAdminStore.setState({
      admin: null,
      isAdminAuthenticated: false,
      adminToken: null,
    });
  });

  it('should start with null admin and unauthenticated state', () => {
    const state = useAdminStore.getState();
    expect(state.admin).toBeNull();
    expect(state.isAdminAuthenticated).toBe(false);
    expect(state.adminToken).toBeNull();
  });

  describe('adminLogin', () => {
    it('should login admin with token', () => {
      const admin: Admin = {
        id: '1',
        username: 'admin',
        email: 'admin@test.com',
        role: 'admin',
      };
      useAdminStore.getState().adminLogin(admin, 'test-token');

      const state = useAdminStore.getState();
      expect(state.admin).toEqual(admin);
      expect(state.isAdminAuthenticated).toBe(true);
      expect(state.adminToken).toBe('test-token');
    });

    it('should login super_admin with token', () => {
      const admin: Admin = {
        id: '2',
        username: 'superadmin',
        email: 'superadmin@test.com',
        role: 'super_admin',
      };
      useAdminStore.getState().adminLogin(admin, 'super-token');

      const state = useAdminStore.getState();
      expect(state.admin).toEqual(admin);
      expect(state.isAdminAuthenticated).toBe(true);
      expect(state.adminToken).toBe('super-token');
    });
  });

  describe('adminLogout', () => {
    it('should logout admin and clear state', () => {
      const admin: Admin = {
        id: '1',
        username: 'admin',
        email: 'admin@test.com',
        role: 'admin',
      };
      useAdminStore.getState().adminLogin(admin, 'test-token');
      useAdminStore.getState().adminLogout();

      const state = useAdminStore.getState();
      expect(state.admin).toBeNull();
      expect(state.isAdminAuthenticated).toBe(false);
      expect(state.adminToken).toBeNull();
    });

    it('should handle logout when already logged out', () => {
      useAdminStore.getState().adminLogout();

      const state = useAdminStore.getState();
      expect(state.admin).toBeNull();
      expect(state.isAdminAuthenticated).toBe(false);
      expect(state.adminToken).toBeNull();
    });
  });

  describe('setAdmin', () => {
    it('should set admin and update authentication status', () => {
      const admin: Admin = {
        id: '1',
        username: 'admin',
        email: 'admin@test.com',
        role: 'admin',
      };
      useAdminStore.getState().setAdmin(admin);

      const state = useAdminStore.getState();
      expect(state.admin).toEqual(admin);
      expect(state.isAdminAuthenticated).toBe(true);
    });

    it('should clear admin when set to null', () => {
      const admin: Admin = {
        id: '1',
        username: 'admin',
        email: 'admin@test.com',
        role: 'admin',
      };
      useAdminStore.getState().setAdmin(admin);
      useAdminStore.getState().setAdmin(null);

      const state = useAdminStore.getState();
      expect(state.admin).toBeNull();
      expect(state.isAdminAuthenticated).toBe(false);
    });
  });

  describe('setAdminToken', () => {
    it('should set admin token', () => {
      useAdminStore.getState().setAdminToken('new-token');

      const state = useAdminStore.getState();
      expect(state.adminToken).toBe('new-token');
    });

    it('should clear admin token when set to null', () => {
      useAdminStore.getState().setAdminToken('test-token');
      useAdminStore.getState().setAdminToken(null);

      const state = useAdminStore.getState();
      expect(state.adminToken).toBeNull();
    });
  });
});
