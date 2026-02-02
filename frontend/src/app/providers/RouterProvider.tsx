import { RouterProvider as ReactRouterProvider } from 'react-router-dom';
import { router } from '../routes';

export function AppRouter() {
  return <ReactRouterProvider router={router} />;
}
