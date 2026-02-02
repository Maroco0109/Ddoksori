import { Outlet, Link, useNavigate, useLocation } from 'react-router-dom';
import { useAdminStore } from './admin.store';

export default function AdminLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { admin, adminLogout } = useAdminStore();

  const handleLogout = () => {
    adminLogout();
    navigate('/admin/login');
  };

  const menuItems = [
    { path: '/admin/dashboard', label: '대시보드', icon: '📊' },
    { path: '/admin/posts', label: '게시글 관리', icon: '📝' },
    { path: '/admin/users', label: '회원 관리', icon: '🧑‍🤝‍🧑' },
    { path: '/admin/reports', label: '신고 관리', icon: '⚠️' },
  ];

  return (
    <div className="flex h-screen bg-gray-100">
      {/* 사이드바 */}
      <aside className="w-56 bg-gray-800 text-white">
        <div className="p-4 border-b border-gray-700">
          <h1 className="text-xl font-bold">관리자 페이지</h1>
          <p className="text-sm text-gray-400 mt-1">{admin?.username}</p>
        </div>

        <nav className="p-4">
          <ul className="space-y-2">
            {menuItems.map((item) => (
              <li key={item.path}>
                <Link
                  to={item.path}
                  className={`flex items-center gap-3 px-4 py-2 rounded-md transition-colors ${
                    location.pathname === item.path
                      ? 'bg-teal-600 text-white'
                      : 'text-gray-300 hover:bg-gray-700'
                  }`}
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="absolute bottom-0 w-56 p-4 border-t border-gray-700">
          <button
            onClick={handleLogout}
            className="w-full px-4 py-2 bg-teal-600 text-white rounded-full hover:bg-teal-700 transition-colors"
          >
            로그아웃
          </button>
        </div>
      </aside>

      {/* 메인 콘텐츠 */}
      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
