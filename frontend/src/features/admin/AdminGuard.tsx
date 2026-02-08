import { Navigate } from 'react-router-dom';
import { useAdminStore } from './admin.store';

interface AdminGuardProps {
  children: React.ReactNode;
}

export default function AdminGuard({ children }: AdminGuardProps) {
  const isAdminAuthenticated = useAdminStore((state) => state.isAdminAuthenticated);

  if (!isAdminAuthenticated) {
    return <Navigate to="/admin/login" replace />;
  }

  return <>{children}</>;
}
