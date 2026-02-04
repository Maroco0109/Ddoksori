import { useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAdminStore } from './admin.store';
import { apiClient } from '@/shared/api/client';

interface AdminGuardProps {
  children: React.ReactNode;
}

/**
 * 관리자 페이지 보호 컴포넌트
 *
 * SEC-34: 백엔드 토큰 검증을 통한 인증 확인
 * 프론트엔드 상태만으로 인증 여부를 판단하지 않고,
 * 백엔드 /api/admin/verify API를 호출하여 토큰 유효성을 확인합니다.
 */
export default function AdminGuard({ children }: AdminGuardProps) {
  const { isAdminAuthenticated, adminToken, adminLogout } = useAdminStore();
  const [isVerifying, setIsVerifying] = useState(true);
  const [isValid, setIsValid] = useState(false);

  useEffect(() => {
    const verifyToken = async () => {
      // 토큰이 없으면 즉시 무효 처리
      if (!adminToken) {
        setIsVerifying(false);
        setIsValid(false);
        return;
      }

      try {
        // SEC-34: 백엔드에서 토큰 유효성 검증
        await apiClient.get('/api/admin/verify', {
          headers: {
            Authorization: `Bearer ${adminToken}`,
          },
        });
        setIsValid(true);
      } catch {
        // 토큰이 유효하지 않으면 로그아웃 처리
        adminLogout();
        setIsValid(false);
      } finally {
        setIsVerifying(false);
      }
    };

    verifyToken();
  }, [adminToken, adminLogout]);

  // 검증 중일 때 로딩 표시
  if (isVerifying) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="text-gray-600">인증 확인 중...</div>
      </div>
    );
  }

  // 인증되지 않았거나 토큰이 유효하지 않으면 로그인 페이지로 리다이렉트
  if (!isAdminAuthenticated || !isValid) {
    return <Navigate to="/admin/login" replace />;
  }

  return <>{children}</>;
}
