import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '@/shared/api/client';
import type { AdminUser, UserSearchParams } from '@/shared/types/admin';
import { useAdminStore } from '../admin.store';
import { getMockData } from '../mockData';

export default function AdminUsersPage() {
  const [searchParams] = useSearchParams();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);
  const adminToken = useAdminStore((state) => state.adminToken);

  const [searchFilters, setSearchFilters] = useState<UserSearchParams>({
    searchKeyword: '',
    status: undefined,
    provider: undefined,
    page: 1,
    limit: 20,
  });

  useEffect(() => {
    const statusParam = searchParams.get('status');
    if (statusParam) {
      setSearchFilters((prev) => ({ ...prev, status: statusParam as any }));
    }
  }, [searchParams]);

  useEffect(() => {
    fetchUsers();
  }, [searchFilters]);

  const fetchUsers = async () => {
    setIsLoading(true);
    try {
      // 테스트 모드인 경우 mock 데이터 사용
      if (adminToken === 'test-token-1234') {
        const data = getMockData('/api/admin/users', searchFilters);
        setUsers(data);
      } else {
        const data = await apiClient.get<AdminUser[]>('/api/admin/users', searchFilters);
        setUsers(data);
      }
    } catch (error) {
      console.error('회원 목록 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearch = () => {
    setSearchFilters({ ...searchFilters, page: 1 });
    fetchUsers();
  };

  const handleUpdateUserStatus = async (userId: string, newStatus: 'active' | 'suspended' | 'banned') => {
    const statusText = {
      active: '활성화',
      suspended: '정지',
      banned: '영구정지',
    };

    if (!confirm(`이 사용자를 ${statusText[newStatus]} 상태로 변경하시겠습니까?`)) {
      return;
    }

    try {
      // 테스트 모드에서는 시뮬레이션만
      if (adminToken === 'test-token-1234') {
        alert('사용자 상태가 변경되었습니다. (테스트 모드)');
        fetchUsers();
      } else {
        await apiClient.put(`/api/admin/users/${userId}/status`, { status: newStatus });
        alert('사용자 상태가 변경되었습니다.');
        fetchUsers();
      }
    } catch (error) {
      alert('상태 변경에 실패했습니다.');
    }
  };

  const handleViewUserDetail = async (userId: string) => {
    try {
      // 테스트 모드인 경우 mock 데이터 사용
      if (adminToken === 'test-token-1234') {
        const user = getMockData(`/api/admin/users/${userId}`);
        setSelectedUser(user);
      } else {
        const user = await apiClient.get<AdminUser>(`/api/admin/users/${userId}`);
        setSelectedUser(user);
      }
    } catch (error) {
      alert('사용자 정보를 불러올 수 없습니다.');
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">회원 관리</h1>

      {/* 검색 필터 */}
      <div className="bg-white p-4 rounded-lg shadow mb-6">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <input
            type="text"
            value={searchFilters.searchKeyword}
            onChange={(e) => setSearchFilters({ ...searchFilters, searchKeyword: e.target.value })}
            placeholder="이름 또는 이메일 검색"
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          />

          <select
            value={searchFilters.status || ''}
            onChange={(e) =>
              setSearchFilters({
                ...searchFilters,
                status: e.target.value === '' ? undefined : (e.target.value as any),
              })
            }
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">전체 상태</option>
            <option value="active">활성</option>
            <option value="suspended">정지</option>
            <option value="banned">영구정지</option>
          </select>

          <select
            value={searchFilters.provider || ''}
            onChange={(e) =>
              setSearchFilters({
                ...searchFilters,
                provider: e.target.value === '' ? undefined : (e.target.value as any),
              })
            }
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">전체 제공자</option>
            <option value="google">Google</option>
            <option value="naver">Naver</option>
          </select>

          <button
            onClick={handleSearch}
            className="px-4 py-2 bg-gray-800 text-white text-sm rounded-md hover:bg-gray-900"
          >
            검색
          </button>
        </div>
      </div>

      {/* 회원 목록 */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">로딩 중...</div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-24">ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-20">이름</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-52">이메일</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-20">가입경로</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-24">가입일</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-16">게시글</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-16">댓글</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-16">신고</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-24">상태</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-28">작업</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {users.map((user) => (
                <tr
                  key={user.id}
                  className={user.status === 'suspended' ? 'bg-yellow-50' : user.status === 'banned' ? 'bg-red-50' : ''}
                >
                  <td className="px-4 py-3 text-xs w-24">
                    <button
                      onClick={() => handleViewUserDetail(user.id)}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      {user.id.substring(0, 8)}...
                    </button>
                  </td>
                  <td className="px-4 py-3 text-xs w-20">{user.name}</td>
                  <td className="px-4 py-3 text-xs w-52">{user.email}</td>
                  <td className="px-4 py-3 text-xs w-20">
                    <span className="px-2 py-1 bg-gray-100 rounded text-xs">
                      {user.provider.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs w-24">{new Date(user.createdAt).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-xs w-16">{user.postCount}</td>
                  <td className="px-4 py-3 text-xs w-16">{user.commentCount}</td>
                  <td className="px-4 py-3 text-xs w-16">
                    {user.reportCount > 0 && (
                      <span className="text-red-600 font-medium">{user.reportCount}</span>
                    )}
                    {user.reportCount === 0 && '-'}
                  </td>
                  <td className="px-4 py-3 text-xs w-24">
                    <span
                      className={`px-2 py-1 rounded-full text-xs ${
                        user.status === 'active'
                          ? 'bg-green-100 text-green-800'
                          : user.status === 'suspended'
                          ? 'bg-yellow-100 text-yellow-800'
                          : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {user.status === 'active' ? '활성' : user.status === 'suspended' ? '정지' : '영구정지'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs w-28">
                    <select
                      value={user.status}
                      onChange={(e) => handleUpdateUserStatus(user.id, e.target.value as any)}
                      className="text-xs border border-gray-300 rounded px-2 py-1"
                    >
                      <option value="active">활성화</option>
                      <option value="suspended">정지</option>
                      <option value="banned">영구정지</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {users.length === 0 && (
            <div className="text-center py-12 text-gray-500">회원이 없습니다.</div>
          )}
        </div>
      )}

      {/* 회원 상세 모달 */}
      {selectedUser && (
        <UserDetailModal user={selectedUser} onClose={() => setSelectedUser(null)} />
      )}
    </div>
  );
}

interface UserDetailModalProps {
  user: AdminUser;
  onClose: () => void;
}

function UserDetailModal({ user, onClose }: UserDetailModalProps) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-2xl w-full">
        <div className="flex justify-between items-start mb-6">
          <h2 className="text-2xl font-bold">회원 상세 정보</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700">회원 ID</label>
              <p className="mt-1 text-sm text-gray-900">{user.id}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">이름</label>
              <p className="mt-1 text-sm text-gray-900">{user.name}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">이메일</label>
              <p className="mt-1 text-sm text-gray-900">{user.email}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">가입 경로</label>
              <p className="mt-1 text-sm text-gray-900">{user.provider.toUpperCase()}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">가입일</label>
              <p className="mt-1 text-sm text-gray-900">
                {new Date(user.createdAt).toLocaleString()}
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">최근 로그인</label>
              <p className="mt-1 text-sm text-gray-900">
                {new Date(user.lastLoginAt).toLocaleString()}
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700">상태</label>
              <p className="mt-1">
                <span
                  className={`px-2 py-1 rounded-full text-xs ${
                    user.status === 'active'
                      ? 'bg-green-100 text-green-800'
                      : user.status === 'suspended'
                      ? 'bg-yellow-100 text-yellow-800'
                      : 'bg-red-100 text-red-800'
                  }`}
                >
                  {user.status === 'active' ? '활성' : user.status === 'suspended' ? '정지' : '영구정지'}
                </span>
              </p>
            </div>
          </div>

          <div className="border-t pt-4">
            <h3 className="text-lg font-semibold mb-2">활동 내역</h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="bg-teal-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">작성한 게시글</p>
                <p className="text-2xl font-bold text-teal-600">{user.postCount}</p>
              </div>
              <div className="bg-green-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">작성한 댓글</p>
                <p className="text-2xl font-bold text-green-600">{user.commentCount}</p>
              </div>
              <div className="bg-red-50 p-4 rounded-lg">
                <p className="text-sm text-gray-600">신고 받은 횟수</p>
                <p className="text-2xl font-bold text-red-600">{user.reportCount}</p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end mt-6">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-800 text-white text-sm rounded-md hover:bg-gray-900"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
