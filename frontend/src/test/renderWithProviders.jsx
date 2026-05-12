/**
 * Render helper — wraps a component in QueryClient + MemoryRouter so
 * components that call `useProjectBudgets`, `useNavigate`, `useAuth` etc
 * function without exploding.
 *
 * AuthContext is mocked per-test via `jest.mock('@/context/AuthContext')`.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { render } from '@testing-library/react';

export function renderWithProviders(ui, { route = '/' } = {}) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]}>
        {ui}
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
