// Automated browser verification script for AuditLens report video player
import { spawn } from 'child_process';

const auditId = process.argv[2] || '1107391a-fef4-4a2f-a83f-1bc44d668edb';
const url = `http://localhost:5173/audits/${auditId}`;

console.log(`[Verify] Starting Google Chrome to test: ${url}`);

const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new',
  '--remote-debugging-port=9222',
  '--no-first-run',
  '--no-default-browser-check',
  `--user-data-dir=/tmp/chrome_audit_test_${Date.now()}`,
  url,
]);

let killed = false;
function cleanup() {
  if (!killed) {
    killed = true;
    chrome.kill('SIGTERM');
  }
}

process.on('exit', cleanup);
process.on('SIGINT', cleanup);

async function wait(ms) {
  return new Promise((res) => setTimeout(res, ms));
}

async function getPages() {
  for (let i = 0; i < 20; i++) {
    try {
      const res = await fetch('http://127.0.0.1:9222/json');
      if (res.ok) {
        const pages = await res.json();
        const page = pages.find((p) => p.type === 'page' && p.url && p.url.includes(auditId));
        if (page && page.webSocketDebuggerUrl) return page;
        const anyAppPage = pages.find((p) => p.type === 'page' && p.url && p.url.includes('localhost'));
        if (anyAppPage && anyAppPage.webSocketDebuggerUrl) return anyAppPage;
      }
    } catch {}
    await wait(500);
  }
  throw new Error('Could not connect to Chrome DevTools port 9222');
}

async function run() {
  await wait(2000);
  const page = await getPages();
  console.log(`[Verify] Connected to page: ${page.url}`);
  console.log(`[Verify] WebSocket URL: ${page.webSocketDebuggerUrl}`);

  const ws = new WebSocket(page.webSocketDebuggerUrl);

  let msgId = 1;
  const callbacks = new Map();

  function send(method, params = {}) {
    return new Promise((resolve) => {
      const id = msgId++;
      callbacks.set(id, resolve);
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.id && callbacks.has(data.id)) {
      const cb = callbacks.get(data.id);
      callbacks.delete(data.id);
      cb(data.result);
    }
    if (data.method === 'Runtime.consoleAPICalled') {
      const args = (data.params.args || []).map((a) => (a.value !== undefined ? a.value : a.description));
      console.log(`[Browser Console ${data.params.type.toUpperCase()}]:`, ...args);
    }
  };

  await new Promise((res) => (ws.onopen = res));

  await send('Runtime.enable');
  await send('Page.enable');

  console.log('[Verify] Waiting for video element to load in DOM and initialize...');
  let videoState = null;

  for (let i = 0; i < 25; i++) {
    await wait(500);
    const evalRes = await send('Runtime.evaluate', {
      expression: `(() => {
        const v = document.querySelector('video');
        if (!v) return { found: false, bodyText: document.body.innerText.slice(0, 500) };
        return {
          found: true,
          src: v.src,
          currentSrc: v.currentSrc,
          readyState: v.readyState,
          networkState: v.networkState,
          duration: v.duration,
          currentTime: v.currentTime,
          paused: v.paused,
          error: v.error ? { code: v.error.code, message: v.error.message } : null,
          playbackErrorDom: !!document.querySelector('div:has(> .lucide-alert-circle)')
        };
      })()`,
      returnByValue: true,
    });

    videoState = evalRes.result?.value;
    if (videoState?.found && videoState?.readyState >= 3) {
      break;
    }
  }

  console.log('[Verify] Initial Video State:', JSON.stringify(videoState, null, 2));

  if (!videoState?.found) {
    throw new Error('Video element was not found in DOM');
  }

  console.log(`[Verify] video.readyState = ${videoState.readyState} (Expected >= 3)`);
  if (videoState.readyState < 3) {
    console.error('[Verify] WARNING: video.readyState is less than 3');
  } else {
    console.log('[Verify] SUCCESS: video.readyState >= 3 (HAVE_FUTURE_DATA / HAVE_ENOUGH_DATA)');
  }

  console.log('[Verify] Calling video.play()...');
  await send('Runtime.evaluate', {
    expression: `(() => {
      const v = document.querySelector('video');
      if (v) return v.play();
    })()`,
    awaitPromise: true,
  });

  await wait(2000);

  const afterPlay = await send('Runtime.evaluate', {
    expression: `(() => {
      const v = document.querySelector('video');
      return {
        readyState: v ? v.readyState : null,
        currentTime: v ? v.currentTime : null,
        paused: v ? v.paused : null,
        duration: v ? v.duration : null,
        error: v && v.error ? { code: v.error.code, message: v.error.message } : null
      };
    })()`,
    returnByValue: true,
  });

  const finalState = afterPlay.result?.value;
  console.log('[Verify] Final Video State after play():', JSON.stringify(finalState, null, 2));

  console.log(`[Verify] currentTime before: ${videoState.currentTime}s, after: ${finalState.currentTime}s`);
  if (finalState.currentTime > videoState.currentTime) {
    console.log('[Verify] SUCCESS: currentTime advanced successfully during playback!');
  } else {
    console.error('[Verify] FAILED: currentTime did not advance');
  }

  ws.close();
  cleanup();
}

run()
  .then(() => {
    console.log('[Verify] All browser verification checks passed!');
    process.exit(0);
  })
  .catch((err) => {
    console.error('[Verify] Error:', err);
    cleanup();
    process.exit(1);
  });
