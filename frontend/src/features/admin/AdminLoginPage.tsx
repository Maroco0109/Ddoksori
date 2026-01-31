import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAdminStore } from './admin.store';
import { apiClient } from '@/shared/api/client';
import type { AdminLoginCredentials, AdminAuthResponse } from '@/shared/types/admin';

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const adminLogin = useAdminStore((state) => state.adminLogin);

  const [credentials, setCredentials] = useState<AdminLoginCredentials>({
    username: '',
    password: '',
  });
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // 테스트 로그인 함수
  const handleTestLogin = () => {
    const testAdmin = {
      id: 'test-admin-id',
      username: 'admin',
      email: 'admin@test.com',
      role: 'admin' as const,
    };
    const testToken = 'test-token-1234';

    adminLogin(testAdmin, testToken);
    navigate('/admin/dashboard');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!credentials.username || !credentials.password) {
      setError('아이디와 비밀번호를 모두 입력해주세요.');
      return;
    }

    // 테스트 계정 체크
    if (credentials.username === 'admin' && credentials.password === 'test1234') {
      handleTestLogin();
      return;
    }

    setIsLoading(true);

    try {
      const response = await apiClient.post<AdminAuthResponse>('/api/admin/login', credentials);
      adminLogin(response.admin, response.token);
      navigate('/admin/dashboard');
    } catch (err) {
      setError('로그인에 실패했습니다. 아이디와 비밀번호를 확인해주세요.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-100">
      <div className="bg-white p-8 rounded-lg shadow-md w-full max-w-md">
        <h1 className="text-2xl font-bold text-center mb-6">관리자 로그인</h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
              아이디
            </label>
            <input
              id="username"
              type="text"
              value={credentials.username}
              onChange={(e) => setCredentials({ ...credentials, username: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-teal-500"
              placeholder="관리자 아이디를 입력하세요"
              disabled={isLoading}
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              비밀번호
            </label>
            <input
              id="password"
              type="password"
              value={credentials.password}
              onChange={(e) => setCredentials({ ...credentials, password: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-teal-500"
              placeholder="비밀번호를 입력하세요"
              disabled={isLoading}
            />
          </div>

          {error && (
            <div className="text-red-500 text-sm text-center">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-teal-600 text-white py-2 rounded-md hover:bg-teal-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? '로그인 중...' : '로그인'}
          </button>
        </form>

        <div className="mt-6 border-t pt-4">
          <button
            type="button"
            onClick={handleTestLogin}
            className="w-full bg-gray-600 text-white py-2 rounded-md hover:bg-gray-700 transition-colors"
          >
            테스트 계정으로 로그인
          </button>
          <p className="text-xs text-gray-500 text-center mt-2">
            테스트 ID: admin / PW: test1234
          </p>
        </div>

        <div className="mt-6 text-xs text-gray-500 text-center">
          <p>관리자 계정으로만 접근 가능합니다.</p>
          <p className="mt-1">인증 정보는 암호화되어 전송됩니다.</p>
        </div>
      </div>
    </div>
  );
}
