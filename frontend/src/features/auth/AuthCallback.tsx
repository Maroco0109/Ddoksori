import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from './auth.store';

export function AuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setUser, setToken } = useAuthStore();

  useEffect(() => {
    const token = searchParams.get('access_token');
    const error = searchParams.get('error');

    if (error) {
      console.error('OAuth error:', error);
      navigate('/');
      return;
    }

    if (!token) {
      console.error('No token received from OAuth');
      navigate('/');
      return;
    }

    // Decode JWT to get user info (basic info only, full info from /auth/me)
    try {
      const payload = JSON.parse(atob(token.split('.')[1]));

      // Store token
      setToken(token);

      // Fetch full user info from backend
      fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
        .then(res => {
          if (!res.ok) throw new Error('Failed to fetch user');
          return res.json();
        })
        .then(user => {
          setUser(user);
          navigate('/');
        })
        .catch(error => {
          console.error('Failed to fetch user info:', error);
          navigate('/');
        });
    } catch (error) {
      console.error('Invalid token:', error);
      navigate('/');
    }
  }, [searchParams, navigate, setUser, setToken]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-deep-teal mx-auto mb-4"></div>
        <p className="text-lg text-gray-600">로그인 중...</p>
      </div>
    </div>
  );
}
