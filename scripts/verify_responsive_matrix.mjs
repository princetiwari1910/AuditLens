#!/usr/bin/env node

import { spawn } from 'child_process';
import { existsSync } from 'fs';

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://127.0.0.1:5173';
const DEBUG_PORT = '9260';

const CHROME_PATHS = [
  process.env.CHROME_BIN,
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome',
  '/usr/bin/chromium-browser',
  '/usr/bin/chromium',
].filter(Boolean);

const chromeBin = CHROME_PATHS.find((p) => p && existsSync(p));
if (!chromeBin) {
  console.error('[matrix] ERROR: Google Chrome executable not found.');
  process.exit(1);
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function main() {
  console.log('[matrix] Spawning headless Chrome on port ' + DEBUG_PORT);
  const chrome = spawn(chromeBin, [
    '--headless=new',
    `--remote-debugging-port=${DEBUG_PORT}`,
    '--no-first-run',
    '--no-default-browser-check',
    'about:blank',
  ]);

  let isCleanedUp = false;
  function cleanup() {
    if (isCleanedUp) return;
    isCleanedUp = true;
    try {
      chrome.kill('SIGTERM');
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

  // Wait for CDP
  let wsUrl = null;
  for (let i = 0; i < 30; i++) {
    await sleep(200);
    try {
      const res = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json`);
      if (res.ok) {
        const targets = await res.json();
        const pageTarget = targets.find((t) => t.type === 'page' && t.webSocketDebuggerUrl) || targets[0];
        if (pageTarget && pageTarget.webSocketDebuggerUrl) {
          wsUrl = pageTarget.webSocketDebuggerUrl;
          break;
        }
      }
    } catch {}
  }

  if (!wsUrl) {
    console.error('[matrix] Failed to connect to Chrome DevTools Protocol.');
    cleanup();
    process.exit(1);
  }

  const ws = new WebSocket(wsUrl);
  await new Promise((resolve) => (ws.onopen = resolve));

  let msgId = 1;
  const pending = new Map();
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.id && pending.has(data.id)) {
      const { resolve, reject } = pending.get(data.id);
      pending.delete(data.id);
      if (data.error) reject(new Error(data.error.message || JSON.stringify(data.error)));
      else resolve(data.result);
    }
  };

  function sendCdp(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = msgId++;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  await sendCdp('Page.enable');
  await sendCdp('Runtime.enable');

  // Fetch or create a demo audit
  let auditId = '';
  try {
    const demoRes = await fetch(`${BACKEND_URL}/api/audits/demo?template_id=campus_fire_exit_core`, {
      method: 'POST',
    });
    const demo = await demoRes.json();
    auditId = demo.id;
    console.log('[matrix] Created demo audit ID: ' + auditId);
    for (let i = 0; i < 30; i++) {
      const aRes = await fetch(`${BACKEND_URL}/api/audits/${auditId}`);
      if (aRes.ok) {
        const a = await aRes.json();
        if (a.status === 'completed' || a.status === 'failed') break;
      }
      await sleep(300);
    }
  } catch (err) {
    console.error('[matrix] Error setting up demo audit:', err);
    cleanup();
    process.exit(1);
  }

  // Create share link
  let shareToken = '';
  try {
    const sRes = await fetch(`${BACKEND_URL}/api/audits/${auditId}/share`, { method: 'POST' });
    const sData = await sRes.json();
    shareToken = sData.token;
    console.log('[matrix] Created share token: ' + shareToken);
  } catch (err) {
    console.error('[matrix] Error creating share link:', err);
  }

  const routes = [
    { name: 'Home (/)', path: '/' },
    { name: `Report (/audits/${auditId})`, path: `/audits/${auditId}` },
    { name: `Trace (/audits/${auditId}/trace)`, path: `/audits/${auditId}/trace` },
    { name: 'Sites (/sites)', path: '/sites' },
    { name: 'Eval (/eval)', path: '/eval' },
    { name: `Compare (/compare?before=${auditId})`, path: `/compare?before=${auditId}` },
    { name: `Share (/share/${shareToken})`, path: `/share/${shareToken}` },
  ];

  const widths = [375, 390, 430, 768, 1024, 1440];
  const matrixResults = [];
  let totalTests = 0;
  let totalPass = 0;
  let totalFail = 0;

  for (const r of routes) {
    const row = { Route: r.name };
    for (const w of widths) {
      totalTests++;
      await sendCdp('Emulation.setDeviceMetricsOverride', {
        width: w,
        height: 844,
        deviceScaleFactor: 1,
        mobile: w <= 768,
      });

      await sendCdp('Page.navigate', { url: `${FRONTEND_URL}${r.path}` });
      await sleep(700);

      const evalRes = await sendCdp('Runtime.evaluate', {
        expression: `(() => {
          const docScroll = document.documentElement ? document.documentElement.scrollWidth : 0;
          const bodyScroll = document.body ? document.body.scrollWidth : 0;
          const maxScroll = Math.max(docScroll, bodyScroll);
          const isOverflow = maxScroll > ${w};
          return { maxScroll, isOverflow };
        })()`,
        returnByValue: true,
      });

      const { maxScroll, isOverflow } = evalRes?.result?.value || { maxScroll: 0, isOverflow: false };
      if (isOverflow) {
        totalFail++;
        row[`${w}px`] = `❌ ${maxScroll}px`;
        console.error(`[matrix] OVERFLOW FAIL: ${r.name} @ ${w}px (maxScroll=${maxScroll}px > ${w}px)`);
      } else {
        totalPass++;
        row[`${w}px`] = `✅ ${maxScroll}px`;
      }
    }
    matrixResults.push(row);
  }

  console.log('\n======================================================');
  console.log('       RESPONSIVE VIEWPORT OVERFLOW MATRIX RESULTS    ');
  console.log('======================================================');
  console.table(matrixResults);
  console.log(`\nSummary: ${totalPass} passed / ${totalTests} total tests across 6 viewports.`);

  cleanup();
  if (totalFail > 0) {
    process.exit(1);
  }
  process.exit(0);
}

main().catch((err) => {
  console.error('[matrix] Fatal error:', err);
  process.exit(1);
});
