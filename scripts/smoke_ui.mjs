#!/usr/bin/env node

import { spawn } from 'child_process';
import { existsSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:5173';
const DEBUG_PORT = process.env.CHROME_DEBUG_PORT || '9224';

const CHROME_PATHS = [
  process.env.CHROME_BIN,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium-browser',
  '/usr/bin/chromium',
].filter(Boolean);

let chromeBin = CHROME_PATHS.find((p) => p && existsSync(p));
if (!chromeBin) {
  console.error('[smoke-ui] ERROR: Google Chrome or Chromium executable not found.');
  process.exit(1);
}

const tmpUserDataDir = join(tmpdir(), `auditlens_smoke_ui_${Date.now()}`);

console.log(`[smoke-ui] Using Chrome binary: ${chromeBin}`);
console.log(`[smoke-ui] Target Frontend: ${FRONTEND_URL}`);
console.log(`[smoke-ui] Target Backend: ${BACKEND_URL}`);

const chrome = spawn(chromeBin, [
  '--headless=new',
  `--remote-debugging-port=${DEBUG_PORT}`,
  '--no-first-run',
  '--no-default-browser-check',
  `--user-data-dir=${tmpUserDataDir}`,
  'about:blank',
]);

let isCleanedUp = false;
function cleanup() {
  if (isCleanedUp) return;
  isCleanedUp = true;
  try {
    chrome.kill('SIGTERM');
  } catch {}
  try {
    rmSync(tmpUserDataDir, { recursive: true, force: true });
  } catch {}
}

process.on('exit', cleanup);
process.on('SIGINT', () => {
  cleanup();
  process.exit(1);
});
process.on('SIGTERM', () => {
  cleanup();
  process.exit(1);
});

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function waitForCdp() {
  for (let i = 0; i < 30; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json`);
      if (res.ok) {
        const pages = await res.json();
        const page = pages.find((p) => p.type === 'page' && p.webSocketDebuggerUrl);
        if (page) return page;
      }
    } catch {}
    await sleep(400);
  }
  throw new Error(`Failed to connect to Chrome CDP on port ${DEBUG_PORT}`);
}

async function main() {
  // 1. Verify Dev Servers
  try {
    const healthRes = await fetch(`${BACKEND_URL}/api/health`);
    if (!healthRes.ok) throw new Error(`Backend returned status ${healthRes.status}`);
    console.log('[smoke-ui] ✅ Backend health check passed.');
  } catch (err) {
    console.error(`[smoke-ui] ❌ Backend not reachable at ${BACKEND_URL}:`, err.message);
    process.exit(1);
  }

  try {
    const feRes = await fetch(`${FRONTEND_URL}/`);
    if (!feRes.ok) throw new Error(`Frontend returned status ${feRes.status}`);
    console.log('[smoke-ui] ✅ Frontend check passed.');
  } catch (err) {
    console.error(`[smoke-ui] ❌ Frontend not reachable at ${FRONTEND_URL}:`, err.message);
    process.exit(1);
  }

  // 2. Connect to Chrome
  const targetPage = await waitForCdp();
  console.log(`[smoke-ui] Connected to Chrome Page WebSocket: ${targetPage.webSocketDebuggerUrl}`);

  const ws = new WebSocket(targetPage.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.onopen = res;
    ws.onerror = rej;
  });

  let nextId = 1;
  const pendingRequests = new Map();
  const consoleErrors = [];
  const uncaughtExceptions = [];
  const networkErrors = [];

  function sendCdp(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = nextId++;
      pendingRequests.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pendingRequests.has(msg.id)) {
      const { resolve, reject } = pendingRequests.get(msg.id);
      pendingRequests.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
      else resolve(msg.result);
    }

    if (msg.method === 'Runtime.consoleAPICalled') {
      const { type, args } = msg.params;
      const text = (args || [])
        .map((a) => (a.value !== undefined ? a.value : a.description || ''))
        .join(' ');
      if (type === 'error') {
        console.error(`[Browser console.error]: ${text}`);
        consoleErrors.push(text);
      }
    }

    if (msg.method === 'Runtime.exceptionThrown') {
      const desc =
        msg.params?.exceptionDetails?.exception?.description ||
        msg.params?.exceptionDetails?.text ||
        'Unknown runtime exception';
      console.error(`[Browser Uncaught Exception]: ${desc}`);
      uncaughtExceptions.push(desc);
    }

    if (msg.method === 'Network.responseReceived') {
      const { response } = msg.params;
      if (response && response.status >= 400) {
        networkErrors.push({ url: response.url, status: response.status });
      }
    }
  };

  await sendCdp('Runtime.enable');
  await sendCdp('Page.enable');
  await sendCdp('Network.enable');

  async function evaluate(expression) {
    const res = await sendCdp('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    return res?.result?.value;
  }

  async function navigateAndVerify(url, routeName, validator) {
    console.log(`\n[smoke-ui] ---> Testing ${routeName} (${url})`);
    const initialErrCount = consoleErrors.length;
    const initialExcCount = uncaughtExceptions.length;

    await sendCdp('Page.navigate', { url });

    let bodyText = '';
    let isBlank = true;
    let customSuccess = false;
    let customErr = null;

    // Poll for render and validation
    for (let i = 0; i < 40; i++) {
      await sleep(300);

      bodyText = (await evaluate('document.body ? document.body.innerText : ""')) || '';
      const readyState = await evaluate('document.readyState');

      if (bodyText.length > 30) {
        isBlank = false;
      }

      if (!isBlank && readyState === 'complete') {
        try {
          const ok = await validator(bodyText, evaluate);
          if (ok) {
            customSuccess = true;
            break;
          }
        } catch (err) {
          customErr = err;
        }
      }
    }

    if (isBlank) {
      throw new Error(`Route ${routeName} resulted in a BLANK PAGE.`);
    }

    if (bodyText.includes('Something went wrong in AuditLens') || bodyText.includes('An unexpected client error occurred')) {
      throw new Error(`Route ${routeName} triggered the app ErrorBoundary! Body: ${bodyText.slice(0, 300)}`);
    }

    if (!customSuccess) {
      throw new Error(
        `Route ${routeName} failed validation assertions: ${customErr?.message || 'Condition not met'}. Body text preview:\n${bodyText.slice(0, 400)}`
      );
    }

    const newErrors = consoleErrors.slice(initialErrCount);
    if (newErrors.length > 0) {
      throw new Error(`Route ${routeName} logged console errors:\n${newErrors.join('\n')}`);
    }

    const newExceptions = uncaughtExceptions.slice(initialExcCount);
    if (newExceptions.length > 0) {
      throw new Error(`Route ${routeName} threw runtime exceptions:\n${newExceptions.join('\n')}`);
    }

    console.log(`[smoke-ui] ✅ ${routeName} passed successfully.`);
  }

  // 1. Test Home route /
  await navigateAndVerify(`${FRONTEND_URL}/`, 'Home Route (/)', (body) => {
    return body.includes('AuditLens') && (body.includes('New Audit') || body.includes('Load Demo') || body.includes('Walkthrough'));
  });

  // 2. Create Demo Audit
  console.log('\n[smoke-ui] Creating demo audit via backend API...');
  const demoRes = await fetch(`${BACKEND_URL}/api/audits/demo?template_id=campus_fire_exit_core`, {
    method: 'POST',
  });
  if (!demoRes.ok) {
    throw new Error(`Failed to create demo audit: HTTP ${demoRes.status}`);
  }
  const demoData = await demoRes.json();
  const auditId = demoData.id;
  console.log(`[smoke-ui] Created demo audit ID: ${auditId}`);

  // Wait briefly for demo processing to complete
  for (let i = 0; i < 30; i++) {
    const aRes = await fetch(`${BACKEND_URL}/api/audits/${auditId}`);
    if (aRes.ok) {
      const aData = await aRes.json();
      if (aData.status === 'completed') {
        console.log('[smoke-ui] Demo audit completed processing.');
        break;
      }
    }
    await sleep(400);
  }

  // 3. Test /audits/<id>
  await navigateAndVerify(`${FRONTEND_URL}/audits/${auditId}`, `/audits/${auditId}`, (body) => {
    return (
      (body.includes('SCORE') || body.includes('Score') || body.includes('/100')) &&
      (body.includes('CAMPUS FIRE EXIT') || body.includes('Findings') || body.includes('passed') || body.includes('Walkthrough'))
    );
  });

  // 4. Test /audits/<id>/trace
  await navigateAndVerify(`${FRONTEND_URL}/audits/${auditId}/trace`, `/audits/${auditId}/trace`, (body) => {
    return (
      body.includes('Execution Trace') ||
      body.includes('Trace Timeline') ||
      body.includes('Trace') ||
      body.includes('Span') ||
      body.includes('campus_fire_exit_core')
    );
  });

  // 5. Test /sites
  await navigateAndVerify(`${FRONTEND_URL}/sites`, '/sites', (body) => {
    return (
      (body.includes('Trend History') || body.includes('Sites') || body.includes('Facilities') || body.includes('Building A')) &&
      (body.includes('Score') || body.includes('pass') || body.includes('Deficiencies'))
    );
  });

  // 6. Test /eval
  await navigateAndVerify(`${FRONTEND_URL}/eval`, '/eval', (body) => {
    return (
      body.includes('Evaluation') ||
      body.includes('Benchmark') ||
      body.includes('Precision') ||
      body.includes('Metrics')
    );
  });

  // 7. Test /share/<token>
  console.log('\n[smoke-ui] Generating share token...');
  const shareRes = await fetch(`${BACKEND_URL}/api/audits/${auditId}/share`, {
    method: 'POST',
  });
  if (!shareRes.ok) {
    throw new Error(`Failed to generate share token: HTTP ${shareRes.status}`);
  }
  const shareData = await shareRes.json();
  const token = shareData.token;
  console.log(`[smoke-ui] Share token generated: ${token}`);

  await navigateAndVerify(`${FRONTEND_URL}/share/${token}`, `/share/${token}`, (body) => {
    const isReadOnly = body.includes('Read-Only') || body.includes('Shared Report') || body.includes('AuditLens');
    const hasAuditInfo = body.includes('Score') || body.includes('/100') || body.includes('Findings');
    const noEditControls = !body.includes('Override') && !body.includes('Mark Passed');
    return isReadOnly && hasAuditInfo && noEditControls;
  });

  // 8. Negative test: /share/<auditId> must NOT work and show not found
  console.log('\n[smoke-ui] Testing invalid share route /share/<auditId>...');
  await sendCdp('Page.navigate', { url: `${FRONTEND_URL}/share/${auditId}` });
  await sleep(1500);
  const invalidShareBody = (await evaluate('document.body ? document.body.innerText : ""')) || '';
  if (
    !invalidShareBody.includes('Invalid or Expired Share Link') &&
    !invalidShareBody.toLowerCase().includes('not found')
  ) {
    throw new Error(
      `Accessing /share/<auditId> did not show not-found/invalid message! Body: ${invalidShareBody.slice(0, 300)}`
    );
  }
  console.log('[smoke-ui] ✅ Invalid share route correctly refused.');

  console.log('\n======================================================');
  console.log('🎉 ALL HEADLESS CHROME SMOKE UI TESTS PASSED CLEANLY! 🎉');
  console.log('======================================================\n');

  cleanup();
  process.exit(0);
}

main().catch((err) => {
  console.error('\n[smoke-ui] ❌ FATAL ERROR:', err.message);
  cleanup();
  process.exit(1);
});
