import { AppRouter } from './providers/RouterProvider';
import { QueryProvider } from './providers/QueryProvider';

export default function App() {
  return (
    <QueryProvider>
      <AppRouter />
    </QueryProvider>
  );
}
