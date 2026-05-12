/**
 * Manual mock — react-router-dom v7 has unusable `main` + subpath
 * exports for Jest. We re-export a minimal API surface that our
 * components and renderWithProviders use.
 */
const React = require('react');

function Link({ to, children, className, ...rest }) {
  return React.createElement('a', { href: typeof to === 'string' ? to : '#', className, ...rest }, children);
}

function MemoryRouter({ children }) {
  return React.createElement(React.Fragment, null, children);
}

function useNavigate() {
  return jest.fn();
}

function useParams() {
  return {};
}

function useLocation() {
  return { pathname: '/', search: '', hash: '', state: null };
}

function Routes({ children }) {
  return children;
}
function Route() {
  return null;
}

module.exports = {
  __esModule: true,
  Link,
  MemoryRouter,
  useNavigate,
  useParams,
  useLocation,
  Routes,
  Route,
  Navigate: ({ to }) => React.createElement('a', { href: to }),
  Outlet: () => null,
  NavLink: Link,
};
