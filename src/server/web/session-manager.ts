import type { IPty } from "node-pty";
import type { WebSocket } from "ws";

export type Session = {
  id: string;
  ws: WebSocket;
  pty: IPty;
  createdAt: number;
};

export class SessionManager {
  private sessions = new Map<string, Session>();
  private maxSessions: number;
  private spawnPty: (cols: number, rows: number) => IPty;

  constructor(
    maxSessions: number,
    spawnPty: (cols: number, rows: number) => IPty,
  ) {
    this.maxSessions = maxSessions;
    this.spawnPty = spawnPty;
  }

  get activeCount(): number {
    return this.sessions.size;
  }

  get isFull(): boolean {
    return this.sessions.size >= this.maxSessions;
  }

  getSession(id: string): Session | undefined {
    return this.sessions.get(id);
  }

  /**
   * Creates a new PTY session bound to the given WebSocket.
   * Returns the session or null if at capacity.
   */
  create(ws: WebSocket, cols = 80, rows = 24): Session | null {
    if (this.isFull) {
      return null;
    }

    const id = crypto.randomUUID();
    let pty: IPty;

    try {
      pty = this.spawnPty(cols, rows);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Unknown PTY spawn error";
      ws.send(
        JSON.stringify({ type: "error", message: `PTY spawn failed: ${message}` }),
      );
      ws.close(1011, "PTY spawn failure");
      return null;
    }

    const session: Session = { id, ws, pty, createdAt: Date.now() };
    this.sessions.set(id, session);

    // PTY output -> WebSocket
    pty.onData((data: string) => {
      if (ws.readyState === ws.OPEN) {
        ws.send(data);
      }
    });

    // PTY exit -> clean up
    pty.onExit(({ exitCode, signal }) => {
      console.log(
        `[session ${id}] PTY exited: code=${exitCode}, signal=${signal}`,
      );
      this.sessions.delete(id);
      if (ws.readyState === ws.OPEN) {
        ws.send(
          JSON.stringify({
            type: "exit",
            exitCode,
            signal,
          }),
        );
        ws.close(1000, "PTY exited");
      }
    });

    // WebSocket messages -> PTY stdin (or resize)
    ws.on("message", (data: Buffer | string) => {
      const str = data.toString();

      // Try to parse as JSON for control messages
      if (str.startsWith("{")) {
        try {
          const msg = JSON.parse(str) as Record<string, unknown>;
          if (
            msg.type === "resize" &&
            typeof msg.cols === "number" &&
            typeof msg.rows === "number"
          ) {
            pty.resize(msg.cols as number, msg.rows as number);
            return;
          }
          if (msg.type === "ping") {
            if (ws.readyState === ws.OPEN) {
              ws.send(JSON.stringify({ type: "pong" }));
            }
            return;
          }
        } catch {
          // Not JSON, treat as terminal input
        }
      }

      pty.write(str);
    });

    // WebSocket close -> kill PTY
    ws.on("close", () => {
      console.log(`[session ${id}] WebSocket closed`);
      this.destroySession(id);
    });

    ws.on("error", (err) => {
      console.error(`[session ${id}] WebSocket error:`, err.message);
      this.destroySession(id);
    });

    console.log(
      `[session ${id}] Created (active: ${this.sessions.size}/${this.maxSessions})`,
    );
    return session;
  }

  /**
   * Gracefully destroys a session: SIGHUP, then SIGKILL after timeout.
   */
  destroySession(id: string): void {
    const session = this.sessions.get(id);
    if (!session) return;

    this.sessions.delete(id);
    const { pty, ws } = session;

    try {
      pty.kill("SIGHUP");
    } catch {
      // PTY may already be dead
    }

    // Force kill after 5 seconds if still alive
    const killTimer = setTimeout(() => {
      try {
        pty.kill("SIGKILL");
      } catch {
        // Already dead
      }
    }, 5000);

    // If PTY exits before the timer, clear it
    pty.onExit(() => clearTimeout(killTimer));

    if (ws.readyState === ws.OPEN || ws.readyState === ws.CONNECTING) {
      ws.close(1000, "Session destroyed");
    }
  }

  /**
   * Destroys all sessions. Used during server shutdown.
   */
  destroyAll(): void {
    for (const id of [...this.sessions.keys()]) {
      this.destroySession(id);
    }
  }
}
