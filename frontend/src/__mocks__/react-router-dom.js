/**
 * Manual mock — react-router-dom v7 has unusable `main` + subpath
 * exports for Jest. We re-export a minimal API surface that our
 * components and renderWithProviders use.
 *
 * `useSearchParams` is wired against a module-level URLSearchParams
 * instance so tests can drive `?expanded=...` deep-links without a
 * real history stack. Tests reset via `__setSearchParams(...)`.
 */
const React = require('react');

let _currentParams = new URLSearchParams();
const _subscribers = new Set();
function _setCurrentParams(next) {
  _currentParams = new URLSearchParams(next);
  // Synchronous re-notify — keeps act() boundaries tight.
  _subscribers.forEach((cb) => cb());
}

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
  return { pathname: '/', search: `?${_currentParams.toString()}`, hash: '', state: null };
}

function useSearchParams() {
  // Tiny subscription so updates re-render the consumer. We don't
  // need React Router's full semantics for unit tests — just enough
  // for `setSearchParams` to drive a re-render and `replace` not to
  // grow a history stack.
  const [, forceTick] = React.useReducer((x) => x + 1, 0);
  React.useEffect(() => {
    _subscribers.add(forceTick);
    return () => { _subscribers.delete(forceTick); };
  }, []);
  const setSearchParams = React.useCallback((updater /* , opts */) => {
    const next = typeof updater === 'function'
      ? updater(new URLSearchParams(_currentParams))
      : updater;
    _setCurrentParams(next);
  }, []);
  return [_currentParams, setSearchParams];
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
  useSearchParams,
  Routes,
  Route,
  Navigate: ({ to }) => React.createElement('a', { href: to }),
  Outlet: () => null,
  NavLink: Link,
  // Test helpers (not part of the real react-router-dom API).
  __setSearchParams: _setCurrentParams,
  __resetSearchParams: () => _setCurrentParams(new URLSearchParams()),
};
