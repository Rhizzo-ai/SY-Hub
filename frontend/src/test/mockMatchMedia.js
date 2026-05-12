/**
 * Standalone matchMedia helper — kept out of setupTests so individual
 * test files can import it without re-running setup.
 */
export function mockMatchMedia(desktop = true) {
  const mql = {
    matches: desktop,
    media: '',
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    onchange: null,
    dispatchEvent: () => true,
  };
  window.matchMedia = () => mql;
}
