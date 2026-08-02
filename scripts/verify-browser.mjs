#!/usr/bin/env node
// =============================================================================
//  ArbiCore X — Browser verification helper (Playwright)
//  File: scripts/verify-browser.mjs
// =============================================================================
//
//  Runs the two verification categories that require a real browser:
//
//    [5] Browser runtime  - login page renders, no uncaught JS exceptions
//    [8] Dashboard render - authenticated navigation to '/' mounts Dashboard
//
//  Called by scripts/verify-deployment.sh. Writes a JSON result file the
//  parent script consumes; exits non-zero if Playwright itself cannot start.
//  The shell script decides PASS/FAIL from the JSON contents.
//
//  Prerequisites (run once on the VPS or CI host):
//      cd $REPO_ROOT/scripts
//      npm init -y                 # if package.json missing
//      npm install playwright
//      npx playwright install chromium
//
//  Usage:
//      node verify-browser.mjs --domain https://arbicore.example.com \
//                              [--admin-user admin --admin-pass 's3cr3t'] \
//                              --out /tmp/verify_browser.json
// =============================================================================

import { writeFileSync } from 'node:fs';
import { argv, exit } from 'node:process';

// ---------- CLI parsing (minimal, no deps) ----------------------------------
function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--domain')     args.domain     = argv[++i];
    else if (k === '--admin-user') args.adminUser = argv[++i];
    else if (k === '--admin-pass') args.adminPass = argv[++i];
    else if (k === '--out')   args.out        = argv[++i];
    else if (k === '--help' || k === '-h') {
      console.log('usage: verify-browser.mjs --domain URL [--admin-user U --admin-pass P] --out FILE');
      exit(0);
    }
  }
  return args;
}

const args = parseArgs(argv);
if (!args.domain || !args.out) {
  console.error('error: --domain and --out are required');
  exit(2);
}

// Trim trailing slash for consistency with the shell script
args.domain = args.domain.replace(/\/+$/, '');

// ---------- Result skeleton -------------------------------------------------
const result = {
  timestamp: new Date().toISOString(),
  domain: args.domain,
  login_page_rendered: false,
  js_exceptions: [],
  console_errors: [],
  login_attempted: false,
  login_succeeded: null,
  dashboard_mounted: null,
  notes: [],
};

// ---------- Dynamic Playwright import (fail gracefully if missing) ----------
let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch (e) {
  console.error('Playwright is not installed. Install it with:');
  console.error('  npm install --prefix ' + import.meta.dirname + ' playwright');
  console.error('  npx --prefix ' + import.meta.dirname + ' playwright install chromium');
  console.error('Underlying error:', e.message);
  writeFileSync(args.out, JSON.stringify({
    ...result,
    error: 'playwright_not_installed',
  }, null, 2));
  exit(2);
}

// ---------- Run the checks --------------------------------------------------
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  ignoreHTTPSErrors: true,
  userAgent: 'ArbiCoreX-DeployVerify/1.0.2',
});
const page = await context.newPage();

// Collect uncaught exceptions + console errors
page.on('pageerror', (err) => {
  result.js_exceptions.push({
    message: err.message,
    stack: (err.stack || '').split('\n').slice(0, 5).join('\n'),
  });
});
page.on('console', (msg) => {
  if (msg.type() === 'error') {
    result.console_errors.push(msg.text().slice(0, 400));
  }
});

try {
  // ---------------- [5] Load login page and verify render ------------------
  const resp = await page.goto(args.domain + '/', {
    waitUntil: 'domcontentloaded',
    timeout: 20_000,
  });
  if (!resp || resp.status() !== 200) {
    result.notes.push(`initial GET ${args.domain}/ returned ${resp ? resp.status() : 'no-response'}`);
  }

  // Wait for either the login form OR the authenticated header to appear.
  // We don't fail on timeout here — we record what actually rendered.
  await page.waitForLoadState('networkidle', { timeout: 8_000 }).catch(() => {});

  // Give React up to 3 more seconds to mount if needed
  await page.waitForTimeout(1_500);

  // Look for well-known test IDs (defined in App.js / Login.jsx)
  const loginFormExists = await page.locator('[data-testid="login-form"], form input[name="username"], form input[type="password"]').count();
  const appHeaderExists = await page.locator('[data-testid="app-header"], .brand-name').count();

  result.login_page_rendered = loginFormExists > 0 || appHeaderExists > 0;

  if (!result.login_page_rendered) {
    // Deeper diagnosis: is the DOM completely empty under #root?
    const rootHtml = await page.evaluate(() => {
      const el = document.getElementById('root');
      return el ? el.innerHTML.slice(0, 500) : '(no #root element)';
    });
    result.notes.push('root innerHTML sample: ' + rootHtml);
  }

  // ---------------- [8] Optional: authenticated dashboard render -----------
  if (args.adminUser && args.adminPass && result.login_page_rendered) {
    result.login_attempted = true;
    try {
      // Fill and submit the login form.
      // Selectors are tolerant to naming variation in Login.jsx.
      const userField = page.locator([
        '[data-testid="login-username-input"]',
        'input[name="username"]',
        'input[type="text"]',
      ].join(', ')).first();

      const passField = page.locator([
        '[data-testid="login-password-input"]',
        'input[name="password"]',
        'input[type="password"]',
      ].join(', ')).first();

      const submitBtn = page.locator([
        '[data-testid="login-submit-btn"]',
        'button[type="submit"]',
        'form button',
      ].join(', ')).first();

      await userField.fill(args.adminUser, { timeout: 5_000 });
      await passField.fill(args.adminPass, { timeout: 5_000 });
      await submitBtn.click({ timeout: 5_000 });

      // Wait for URL to change away from /login (or terminal header to appear)
      await Promise.race([
        page.waitForURL((url) => !/\/login\b/.test(url.toString()), { timeout: 10_000 }),
        page.waitForSelector('[data-testid="main-nav"], [data-testid="nav-terminal"]', { timeout: 10_000 }),
      ]).catch(() => {});

      // Verify the authenticated Dashboard mounted
      const dashboardMounted = await page.locator([
        '[data-testid="patient-dashboard"]',
        '[data-testid="main-nav"]',
        '[data-testid="nav-terminal"]',
        '[data-testid="header-username"]',
      ].join(', ')).count();

      result.dashboard_mounted = dashboardMounted > 0;
      result.login_succeeded = dashboardMounted > 0;

      if (!result.login_succeeded) {
        const currentUrl = page.url();
        result.notes.push(`after login, current URL: ${currentUrl}`);
      }
    } catch (e) {
      result.login_succeeded = false;
      result.dashboard_mounted = false;
      result.notes.push('login flow error: ' + e.message.slice(0, 200));
    }
  }
} catch (e) {
  result.notes.push('top-level error: ' + e.message.slice(0, 400));
} finally {
  await context.close();
  await browser.close();
  writeFileSync(args.out, JSON.stringify(result, null, 2));
}

// Exit 0 always — the shell script decides PASS/FAIL from the JSON.
// Non-zero exit is reserved for "Playwright itself failed to run".
exit(0);
