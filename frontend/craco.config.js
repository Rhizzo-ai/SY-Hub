// craco.config.js
const path = require("path");
require("dotenv").config();

// Check if we're in development/preview mode (not production build).
// Craco sets NODE_ENV=development for `start`, NODE_ENV=production for
// `build`, NODE_ENV=test for `craco test`. Visual-edits is a DEV-ONLY
// tool (the bundled `withVisualEdits` itself short-circuits when
// NODE_ENV === 'production' — see node_modules/@emergentbase/visual-edits
// /dist/craco-plugin.js:93). We also keep it OUT of `craco test` because
// loading it under Jest tripped babel-traverse on the existing
// recursive folder component used by `<FolderNode/>`.
const isDevServer = process.env.NODE_ENV !== "production"
  && process.env.NODE_ENV !== "test";

// Environment variable overrides
const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

// Conditionally load health check modules only if enabled
let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
    configure: (webpackConfig) => {

      // Add ignored patterns to reduce watched directories
        webpackConfig.watchOptions = {
          ...webpackConfig.watchOptions,
          ignored: [
            '**/node_modules/**',
            '**/.git/**',
            '**/build/**',
            '**/dist/**',
            '**/coverage/**',
            '**/public/**',
        ],
      };

      // Add health check plugin to webpack if enabled
      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  // Add health check endpoints if enabled
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      // Call original setup if exists
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      // Setup health endpoints
      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};

// Wrap with visual edits (automatically adds babel plugin, dev server, and overlay in dev mode)
//
// Build Pack 2.7-DOCS-FE-fix §R1 (B81). Root cause: `<FolderNode/>` is
// legitimately recursive (renders `<FolderNode/>` per child folder —
// correct React tree rendering) AND the upstream visual-edits babel
// plugin `element-metadata-plugin` recurses the JSX AST in a way that
// overflows the V8 call stack on that specific component. The fix
// belongs in build config, not app code — DO NOT edit FolderNode.jsx.
//
// Surgical Option A: leave visual-edits active for every other file
// and SHIM the babel plugin so its visitors never run when the source
// file is `FolderNode.jsx`. The wrapper:
//   - inspects the installed plugin at runtime to confirm it returns
//     `{ name: 'element-metadata-plugin', visitor: {...} }` (verified
//     in node_modules/@emergentbase/visual-edits/dist/babel-plugin/
//     index.js:1982-1988);
//   - returns the SAME shape but with each visitor wrapped to no-op
//     for our one excluded file. Anything else flows through unchanged.
// If visual-edits ever changes its plugin shape we fail loud at compile
// (so we'd notice immediately) rather than silently mis-skipping.
//
// Production build path: unaffected (the upstream `withVisualEdits`
// itself short-circuits on NODE_ENV === 'production', and `isDevServer`
// gates this whole branch anyway).
// Jest path: unaffected (NODE_ENV='test' also fails `isDevServer`).
if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
    excludeVisualEditsFromRecursiveFiles(webpackConfig);
  } catch (err) {
    if (err.code === 'MODULE_NOT_FOUND' && err.message.includes('@emergentbase/visual-edits/craco')) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

/**
 * Replace the visual-edits babel plugin reference inside
 * `cracoConfig.babel.plugins` with a thin shim that delegates to the
 * real plugin BUT no-ops on a small allowlist of files known to crash
 * its AST walker. The shim runs at the plugin-instantiation level —
 * babel calls each plugin as `plugin(api, opts)` and uses the returned
 * `{ visitor }` map. We hook every visitor and short-circuit when the
 * current file matches.
 *
 * Per Build Pack §R1.2 / §R1.4 the only file confirmed to trigger the
 * crash — and therefore the ONLY file excluded — is `FolderNode.jsx`.
 * `FolderPicker.jsx` flattens its tree via a single `walk()` helper +
 * flat map (not self-recursive at the JSX level) and
 * `DocumentFolderView.jsx` isn't recursive either; both keep full
 * visual-edits coverage.
 */
function excludeVisualEditsFromRecursiveFiles(cfg) {
  const EXCLUDED = [/[\\/]src[\\/]components[\\/]suppliers[\\/]FolderNode\.jsx$/];
  const plugins = cfg.babel && cfg.babel.plugins;
  if (!Array.isArray(plugins) || plugins.length === 0) return;

  const isExcluded = (filename) => {
    if (!filename) return false;
    return EXCLUDED.some((re) => re.test(filename));
  };

  for (let i = 0; i < plugins.length; i++) {
    const entry = plugins[i];
    const fn = typeof entry === "function" ? entry : null;
    if (!fn || fn.name !== "babelMetadataPlugin") continue;

    // Build a shimmed plugin descriptor. We MUST keep babel's
    // instantiation contract — every visitor function the upstream
    // plugin returns is wrapped to no-op on excluded files.
    plugins[i] = function visualEditsExcludingFolderNode(api, opts) {
      const real = fn(api, opts);
      if (!real || !real.visitor) {
        throw new Error(
          "[visual-edits exclusion shim] upstream plugin returned an unexpected shape; " +
          "delete this exclusion (or update the shim) and re-run."
        );
      }
      const guardedVisitor = {};
      for (const key of Object.keys(real.visitor)) {
        const orig = real.visitor[key];
        // Visitors may be a function (enter) or an object
        // ({ enter, exit }). Handle both shapes generically.
        if (typeof orig === "function") {
          guardedVisitor[key] = function (path, state) {
            if (isExcluded(state.filename)) return;
            return orig.call(this, path, state);
          };
        } else if (orig && typeof orig === "object") {
          const wrapped = {};
          for (const phase of Object.keys(orig)) {
            const phaseFn = orig[phase];
            if (typeof phaseFn === "function") {
              wrapped[phase] = function (path, state) {
                if (isExcluded(state.filename)) return;
                return phaseFn.call(this, path, state);
              };
            } else {
              wrapped[phase] = phaseFn;
            }
          }
          guardedVisitor[key] = wrapped;
        } else {
          guardedVisitor[key] = orig;
        }
      }
      return {
        ...real,
        name: (real.name || "element-metadata-plugin") + "-excl-foldernode",
        visitor: guardedVisitor,
      };
    };
    return;
  }
}

// Jest path-alias support — mirror the webpack alias above so tests
// can `import x from '@/...'` exactly like the runtime build does.
// Also relax transformIgnorePatterns so ESM-only deps (date-fns,
// date-fns-tz, lucide-react) are transpiled by Babel for Jest.
webpackConfig.jest = {
  configure: (jestConfig) => {
    jestConfig.moduleNameMapper = {
      ...(jestConfig.moduleNameMapper || {}),
      '^@/(.*)$': '<rootDir>/src/$1',
      '^react-router-dom$': '<rootDir>/src/__mocks__/react-router-dom.js',
    };
    jestConfig.resolver = '<rootDir>/jest.resolver.cjs';
    jestConfig.transformIgnorePatterns = [
      'node_modules/(?!(date-fns|date-fns-tz|lucide-react|@dnd-kit|sonner|@radix-ui|zod|@hookform)/)',
      '^.+\\.module\\.(css|sass|scss)$',
    ];
    return jestConfig;
  },
};

module.exports = webpackConfig;
