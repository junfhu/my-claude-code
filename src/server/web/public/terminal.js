/**
 * Claude Code — Terminal-in-Browser (xterm.js + WebSocket)
 */

const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const PING_INTERVAL_MS = 5000;

// DOM elements
const loadingOverlay = document.getElementById('loading-overlay');
const reconnectOverlay = document.getElementById('reconnect-overlay');
const reconnectSub = document.getElementById('reconnect-sub');
const statusDot = document.getElementById('status-dot');
const latencyEl = document.getElementById('latency');
const barBtn = document.getElementById('bar-btn');
const topBar = document.getElementById('top-bar');
const toggleBar = document.getElementById('toggle-bar');
const terminalContainer = document.getElementById('terminal-container');

// State
let ws = null;
let term = null;
let fitAddon = null;
let searchAddon = null;
let webglAddon = null;
let reconnectDelay = RECONNECT_BASE_MS;
let reconnectTimer = null;
let pingTimer = null;
let lastPingSent = 0;
let connected = false;

// ── Theme ──────────────────────────────────────────────────────────────

function getTheme() {
  const s = getComputedStyle(document.documentElement);
  const v = (prop) => s.getPropertyValue(prop).trim();
  return {
    background: v('--term-bg'),
    foreground: v('--term-fg'),
    cursor: v('--term-cursor'),
    selectionBackground: v('--term-selection'),
    black: v('--term-black'),
    red: v('--term-red'),
    green: v('--term-green'),
    yellow: v('--term-yellow'),
    blue: v('--term-blue'),
    magenta: v('--term-magenta'),
    cyan: v('--term-cyan'),
    white: v('--term-white'),
    brightBlack: v('--term-bright-black'),
    brightRed: v('--term-red'),
    brightGreen: v('--term-green'),
    brightYellow: v('--term-yellow'),
    brightBlue: v('--term-blue'),
    brightMagenta: v('--term-magenta'),
    brightCyan: v('--term-cyan'),
    brightWhite: v('--term-bright-white'),
  };
}

// ── Terminal Init ──────────────────────────────────────────────────────

function initTerminal() {
  term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block',
    fontFamily: "'Cascadia Code', 'Fira Code', 'JetBrains Mono', 'SF Mono', Menlo, Monaco, 'Courier New', monospace",
    fontSize: 14,
    lineHeight: 1.2,
    theme: getTheme(),
    allowProposedApi: true,
    scrollback: 10000,
    convertEol: true,
  });

  // Addons
  fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);

  const webLinksAddon = new WebLinksAddon.WebLinksAddon();
  term.loadAddon(webLinksAddon);

  searchAddon = new SearchAddon.SearchAddon();
  term.loadAddon(searchAddon);

  const unicode11Addon = new Unicode11Addon.Unicode11Addon();
  term.loadAddon(unicode11Addon);
  term.unicode.activeVersion = '11';

  // Open terminal
  term.open(terminalContainer);

  // Try WebGL renderer, fall back to canvas
  try {
    webglAddon = new WebglAddon.WebglAddon();
    webglAddon.onContextLoss(() => {
      webglAddon.dispose();
      webglAddon = null;
    });
    term.loadAddon(webglAddon);
  } catch (e) {
    console.warn('WebGL renderer unavailable, using default canvas renderer');
  }

  fitAddon.fit();

  // Resize handling
  const resizeObserver = new ResizeObserver(() => {
    if (fitAddon) {
      fitAddon.fit();
    }
  });
  resizeObserver.observe(terminalContainer);

  term.onResize(({ cols, rows }) => {
    sendJSON({ type: 'resize', cols, rows });
  });

  // Forward input to WebSocket
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data);
    }
  });

  // Binary data
  term.onBinary((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      const buf = new Uint8Array(data.length);
      for (let i = 0; i < data.length; i++) {
        buf[i] = data.charCodeAt(i) & 0xff;
      }
      ws.send(buf.buffer);
    }
  });

  // Keyboard intercepts
  term.attachCustomKeyEventHandler((ev) => {
    // Ctrl+Shift+F → search
    if (ev.ctrlKey && ev.shiftKey && ev.key === 'F') {
      if (ev.type === 'keydown') {
        const query = prompt('Search terminal:');
        if (query) searchAddon.findNext(query);
      }
      return false;
    }
    // Ctrl+Shift+C → copy (Linux)
    if (ev.ctrlKey && ev.shiftKey && ev.key === 'C') {
      if (ev.type === 'keydown') {
        const sel = term.getSelection();
        if (sel) navigator.clipboard.writeText(sel);
      }
      return false;
    }
    // Ctrl+Shift+V → paste (Linux)
    if (ev.ctrlKey && ev.shiftKey && ev.key === 'V') {
      if (ev.type === 'keydown') {
        navigator.clipboard.readText().then((text) => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(text);
          }
        });
      }
      return false;
    }
    return true;
  });

  // Theme change listener
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    term.options.theme = getTheme();
  });
}

// ── WebSocket ──────────────────────────────────────────────────────────

function getWSUrl() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = new URL(`${proto}//${location.host}/ws`);
  // Auth token from URL param or localStorage
  const params = new URLSearchParams(location.search);
  const token = params.get('token') || localStorage.getItem('claude-terminal-token');
  if (token) {
    url.searchParams.set('token', token);
    // Persist for reconnection
    localStorage.setItem('claude-terminal-token', token);
  }
  return url.toString();
}

function sendJSON(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

function connect() {
  setStatus('connecting');

  ws = new WebSocket(getWSUrl());
  ws.binaryType = 'arraybuffer';

  ws.addEventListener('open', () => {
    connected = true;
    reconnectDelay = RECONNECT_BASE_MS;
    setStatus('connected');
    hideLoading();
    hideReconnect();

    // Send initial size
    if (fitAddon) {
      fitAddon.fit();
      sendJSON({ type: 'resize', cols: term.cols, rows: term.rows });
    }

    // Start ping
    startPing();
  });

  ws.addEventListener('message', (ev) => {
    if (ev.data instanceof ArrayBuffer) {
      term.write(new Uint8Array(ev.data));
    } else if (typeof ev.data === 'string') {
      // Could be JSON control message or plain text
      try {
        const msg = JSON.parse(ev.data);
        handleControlMessage(msg);
      } catch {
        term.write(ev.data);
      }
    }
  });

  ws.addEventListener('close', () => {
    onDisconnect();
  });

  ws.addEventListener('error', () => {
    // error fires before close, let close handle reconnect
  });
}

function handleControlMessage(msg) {
  if (msg.type === 'pong') {
    const latency = Date.now() - lastPingSent;
    latencyEl.textContent = `${latency}ms`;
  }
}

function onDisconnect() {
  connected = false;
  setStatus('disconnected');
  stopPing();

  if (ws) {
    ws = null;
  }

  showReconnect();
  scheduleReconnect();
}

function scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectSub.textContent = `Retrying in ${Math.round(reconnectDelay / 1000)}s...`;
  reconnectTimer = setTimeout(() => {
    connect();
  }, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
}

function manualReconnect() {
  clearTimeout(reconnectTimer);
  reconnectDelay = RECONNECT_BASE_MS;
  if (ws) {
    ws.close();
    ws = null;
  }
  // Clear terminal for fresh session
  if (term) term.clear();
  connect();
}

// ── Ping ───────────────────────────────────────────────────────────────

function startPing() {
  stopPing();
  pingTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      lastPingSent = Date.now();
      sendJSON({ type: 'ping' });
    }
  }, PING_INTERVAL_MS);
}

function stopPing() {
  clearInterval(pingTimer);
  latencyEl.textContent = '--';
}

// ── UI Helpers ─────────────────────────────────────────────────────────

function setStatus(state) {
  statusDot.className = 'status-dot';
  if (state === 'disconnected') statusDot.classList.add('disconnected');
  if (state === 'connecting') statusDot.classList.add('connecting');

  barBtn.textContent = connected ? 'Disconnect' : 'Reconnect';
}

function hideLoading() {
  loadingOverlay.classList.add('hidden');
}

function showReconnect() {
  reconnectOverlay.classList.add('visible');
}

function hideReconnect() {
  reconnectOverlay.classList.remove('visible');
}

// ── Top Bar Toggle ─────────────────────────────────────────────────────

function setupBarToggle() {
  const isCollapsed = localStorage.getItem('claude-bar-collapsed') === 'true';
  if (isCollapsed) topBar.classList.add('collapsed');

  toggleBar.addEventListener('click', () => {
    topBar.classList.remove('collapsed');
    localStorage.setItem('claude-bar-collapsed', 'false');
    if (fitAddon) setTimeout(() => fitAddon.fit(), 200);
  });

  // Double-click top bar to collapse
  topBar.addEventListener('dblclick', () => {
    topBar.classList.add('collapsed');
    localStorage.setItem('claude-bar-collapsed', 'true');
    if (fitAddon) setTimeout(() => fitAddon.fit(), 200);
  });

  barBtn.addEventListener('click', () => {
    if (connected) {
      if (ws) ws.close();
    } else {
      manualReconnect();
    }
  });
}

// ── Boot ───────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initTerminal();
  setupBarToggle();
  connect();

  // Focus terminal on click anywhere
  document.addEventListener('click', () => term.focus());
  term.focus();
});
