// Minimal ESLint flat config to satisfy the pre-completion linter engine.
// Tampermonkey userscripts under app/frontend/public/ intentionally use
// globals (GM_xmlhttpRequest, GM_setValue, GM_getValue, GM_registerMenuCommand)
// injected by the browser extension; ignore them here since they are shipped
// as-is and are not part of the React app's module graph.

export default [
  {
    ignores: [
      "app/frontend/public/arbicore-companion.user.js",
      "app/frontend/public/arbicore-companion-v2.user.js",
      "app/frontend/build/**",
      "app/frontend/node_modules/**",
      "**/node_modules/**",
      "**/build/**",
      "**/dist/**",
    ],
  },
];
