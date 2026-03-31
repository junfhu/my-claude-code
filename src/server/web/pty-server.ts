import express from "express";
import { createServer } from "http";
import path from "path";
import { spawn } from "node-pty";
import { WebSocketServer } from "ws";
import { ConnectionRateLimiter, validateAuthToken } from "./auth.js";
import { SessionManager } from "./session-manager.js";

// Configuration from environment
const PORT = parseInt(process.env.PORT ?? "3000", 10);
const HOST = process.env.HOST ?? "0.0.0.0";
const MAX_SESSIONS = parseInt(process.env.MAX_SESSIONS ?? "10", 10);
const ALLOWED_ORIGINS = process.env.ALLOWED_ORIGINS?.split(",") ?? [];
const SHELL = process.env.SHELL ?? "bash";

// Resolve the claude CLI binary
const CLAUDE_BIN = process.env.CLAUDE_BIN ?? "claude";

const app = express();
const server = createServer(app);

// --- HTTP routes ---

app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    activeSessions: sessionManager.activeCount,
    maxSessions: MAX_SESSIONS,
  });
});

// Serve static frontend
const publicDir = path.join(import.meta.dirname, "public");
app.use(express.static(publicDir));

app.get("/", (_req, res) => {
  res.sendFile(path.join(publicDir, "index.html"));
});

// --- Session Manager ---

const sessionManager = new SessionManager(MAX_SESSIONS, (cols, rows) =>
  spawn(CLAUDE_BIN, [], {
    name: "xterm-256color",
    cols,
    rows,
    cwd: process.env.WORK_DIR ?? process.cwd(),
    env: {
      ...process.env,
      TERM: "xterm-256color",
      COLORTERM: "truecolor",
    },
  }),
);

// --- WebSocket server ---

const rateLimiter = new ConnectionRateLimiter();

// Clean up rate limiter every 5 minutes
const rateLimiterCleanup = setInterval(() => rateLimiter.cleanup(), 5 * 60_000);

const wss = new WebSocketServer({
  server,
  path: "/ws",
  verifyClient: ({ req, origin }, callback) => {
    // Origin check
    if (ALLOWED_ORIGINS.length > 0 && !ALLOWED_ORIGINS.includes(origin)) {
      console.warn(`Rejected connection from origin: ${origin}`);
      callback(false, 403, "Forbidden origin");
      return;
    }

    // Auth token check
    if (!validateAuthToken(req)) {
      console.warn("Rejected connection: invalid auth token");
      callback(false, 401, "Unauthorized");
      return;
    }

    // Rate limit check
    const ip =
      (req.headers["x-forwarded-for"] as string)?.split(",")[0]?.trim() ??
      req.socket.remoteAddress ??
      "unknown";
    if (!rateLimiter.allow(ip)) {
      console.warn(`Rate limited connection from ${ip}`);
      callback(false, 429, "Too many connections");
      return;
    }

    callback(true);
  },
});

wss.on("connection", (ws, req) => {
  const ip =
    (req.headers["x-forwarded-for"] as string)?.split(",")[0]?.trim() ??
    req.socket.remoteAddress ??
    "unknown";
  console.log(`New WebSocket connection from ${ip}`);

  if (sessionManager.isFull) {
    ws.send(
      JSON.stringify({
        type: "error",
        message: "Max sessions reached. Try again later.",
      }),
    );
    ws.close(1013, "Max sessions reached");
    return;
  }

  // Parse initial size from query params
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  const cols = parseInt(url.searchParams.get("cols") ?? "80", 10);
  const rows = parseInt(url.searchParams.get("rows") ?? "24", 10);

  const session = sessionManager.create(ws, cols, rows);
  if (session) {
    ws.send(JSON.stringify({ type: "connected", sessionId: session.id }));
  }
});

// --- Graceful shutdown ---

function shutdown() {
  console.log("Shutting down...");
  clearInterval(rateLimiterCleanup);
  sessionManager.destroyAll();
  wss.close(() => {
    server.close(() => {
      console.log("Server closed.");
      process.exit(0);
    });
  });

  // Force exit after 10 seconds
  setTimeout(() => {
    console.error("Forced shutdown after timeout");
    process.exit(1);
  }, 10_000);
}

process.on("SIGTERM", shutdown);
process.on("SIGINT", shutdown);

// --- Start ---

server.listen(PORT, HOST, () => {
  console.log(`PTY server listening on http://${HOST}:${PORT}`);
  console.log(`  WebSocket: ws://${HOST}:${PORT}/ws`);
  console.log(`  Max sessions: ${MAX_SESSIONS}`);
  if (process.env.AUTH_TOKEN) {
    console.log("  Auth: token required");
  }
});

export { app, server, sessionManager, wss };
