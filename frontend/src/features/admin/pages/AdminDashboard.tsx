import { useState, useEffect } from 'react';
import { apiClient } from '@/shared/api/client';
import type { AdminStats } from '@/shared/types/admin';
import { useAdminStore } from '../admin.store';
import { getMockData } from '../mockData';

export default function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const adminToken = useAdminStore((state) => state.adminToken);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    try {
      // 테스트 모드인 경우 mock 데이터 사용
      if (adminToken === 'test-token-1234') {
        const data = getMockData('/api/admin/stats');
        setStats(data);
      } else {
        const data = await apiClient.get<AdminStats>('/api/admin/stats');
        setStats(data);
      }
    } catch (error) {
      console.error('통계 데이터 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">로딩 중...</div>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">대시보드</h1>

      {/* 통계 카드 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="전체 회원"
          value={stats?.totalUsers || 0}
          change={`+${stats?.todayNewUsers || 0} 오늘`}
          icon="🧑‍🤝‍🧑"
          color="blue"
        />
        <StatCard
          title="전체 게시글"
          value={stats?.totalPosts || 0}
          change={`+${stats?.todayNewPosts || 0} 오늘`}
          icon="📝"
          color="green"
        />
        <StatCard
          title="전체 댓글"
          value={stats?.totalComments || 0}
          change={`+${stats?.todayNewComments || 0} 오늘`}
          icon="💬"
          color="blue"
        />
        <StatCard
          title="대기 중인 신고"
          value={stats?.pendingReports || 0}
          change={stats?.pendingReports ? '처리 필요' : ''}
          icon="⚠️"
          color="red"
        />
      </div>

      {/* 최근 활동 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-xl font-semibold mb-4">빠른 작업</h2>
          <div className="space-y-3">
            <QuickActionButton
              href="/admin/posts?action=write-notice"
              label="공지사항 작성"
              icon="📢"
            />
            <QuickActionButton
              href="/admin/reports?status=pending"
              label="신고 처리하기"
              icon="⚠️"
            />
            <QuickActionButton
              href="/admin/users?status=suspended"
              label="정지된 계정 관리"
              icon="🔒"
            />
          </div>
        </div>

        <div className="bg-white p-6 rounded-lg shadow">
          <h2 className="text-xl font-semibold mb-4">시스템 알림</h2>
          <div className="space-y-3 text-sm text-gray-600">
            {stats?.pendingReports && stats.pendingReports > 0 && (
              <div className="p-3 bg-red-50 border-l-4 border-red-500 rounded">
                <p className="font-medium text-red-700">
                  처리 대기 중인 신고가 {stats.pendingReports}건 있습니다.
                </p>
              </div>
            )}
            {stats?.suspendedUsers && stats.suspendedUsers > 0 && (
              <div className="p-3 bg-yellow-50 border-l-4 border-yellow-500 rounded">
                <p className="font-medium text-yellow-700">
                  현재 {stats.suspendedUsers}명의 사용자가 정지 상태입니다.
                </p>
              </div>
            )}
            {(!stats?.pendingReports || stats.pendingReports === 0) &&
              (!stats?.suspendedUsers || stats.suspendedUsers === 0) && (
              <div className="p-3 bg-green-50 border-l-4 border-green-500 rounded">
                <p className="font-medium text-green-700">
                  처리가 필요한 항목이 없습니다.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: number;
  change?: string;
  icon: string;
  color: 'blue' | 'green' | 'purple' | 'orange' | 'red';
}

function StatCard({ title, value, change, icon }: StatCardProps) {
  return (
    <div className="bg-white p-6 rounded-lg shadow">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-gray-600 text-sm font-medium">{title}</h3>
        <span className="text-3xl">{icon}</span>
      </div>
      <div className="text-2xl font-bold text-gray-900">{value.toLocaleString()}</div>
      {change && <p className="text-sm text-gray-500 mt-2">{change}</p>}
    </div>
  );
}

interface QuickActionButtonProps {
  href: string;
  label: string;
  icon: string;
}

function QuickActionButton({ href, label, icon }: QuickActionButtonProps) {
  return (
    <a
      href={href}
      className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors"
    >
      <span className="text-xl">{icon}</span>
      <span className="font-medium">{label}</span>
    </a>
  );
}
