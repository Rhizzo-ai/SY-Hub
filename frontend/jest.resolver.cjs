/**
 * Custom Jest resolver — honours package.json `exports` field.
 *
 * react-router-dom v7 / react-router v7 ship only `exports` maps —
 * their `main` field points to files that don't exist. Jest's default
 * resolver doesn't read `exports`, so we delegate to its enhanced API
 * with `conditions: ['node', 'require', 'default']`.
 */
module.exports = (request, options) =>
  options.defaultResolver(request, {
    ...options,
    packageFilter: (pkg) => {
      // For react-router-dom v7: force main → the CJS entry pointed at
      // by exports['.'].node.default
      if (pkg.name === 'react-router-dom' && pkg.exports?.['.']?.node?.default) {
        pkg.main = pkg.exports['.'].node.default;
      } else if (pkg.name === 'react-router' && pkg.exports?.['.']?.node?.default) {
        pkg.main = pkg.exports['.'].node.default;
      }
      return pkg;
    },
  });
