import {spawn, type ChildProcess} from "node:child_process";
import {existsSync} from "node:fs";
import path from "node:path";
import {createInterface} from "node:readline";
import {fileURLToPath} from "node:url";

export type BridgeEvent = Record<string, unknown>;

const THIS_DIR = path.dirname(fileURLToPath(import.meta.url));
const TERMINAL_ROOT = path.resolve(THIS_DIR, "..");
const REPO_ROOT = path.resolve(TERMINAL_ROOT, "..");

function resolvePython(): string {
  const configured = process.env.DHARMA_PYTHON?.trim();
  if (configured) {
    return configured;
  }

  const venvPython = path.join(REPO_ROOT, ".venv", "bin", "python");
  if (existsSync(venvPython)) {
    return venvPython;
  }

  return "python3";
}

export class DharmaBridge {
  private child: ChildProcess;
  private nextId = 1;
  private alive = false;
  private readonly onEvent: (event: BridgeEvent) => void;

  constructor(onEvent: (event: BridgeEvent) => void) {
    this.onEvent = onEvent;
    this.child = this.spawnChild();
  }

  private spawnChild(): ChildProcess {
    const child = spawn(resolvePython(), ["-m", "dharma_swarm.terminal_bridge", "stdio"], {
      cwd: REPO_ROOT,
      env: process.env,
      stdio: ["pipe", "pipe", "inherit"],
    });
    this.alive = true;

    if (!child.stdout || !child.stdin) {
      throw new Error("bridge child process streams are unavailable");
    }

    const reader = createInterface({input: child.stdout});
    reader.on("line", (line) => {
      const trimmed = line.trim();
      if (!trimmed) {
        return;
      }
      try {
        this.onEvent(JSON.parse(trimmed) as BridgeEvent);
      } catch {
        this.onEvent({
          type: "bridge.error",
          code: "invalid_bridge_json",
          message: trimmed,
        });
      }
    });
    child.on("exit", (code, signal) => {
      this.alive = false;
      this.onEvent({
        type: "bridge.error",
        code: "bridge_exit",
        message: `bridge exited (${code ?? "null"}${signal ? `, ${signal}` : ""})`,
      });
    });
    child.on("error", (error) => {
      this.alive = false;
      this.onEvent({
        type: "bridge.error",
        code: "bridge_spawn_error",
        message: error.message,
      });
    });
    return child;
  }

  private ensureChild(): void {
    if (this.alive && this.child.stdin && !this.child.stdin.destroyed) {
      return;
    }
    this.child = this.spawnChild();
  }

  send(type: string, payload: Record<string, unknown> = {}): string {
    const id = String(this.nextId++);
    const request = {id, type, ...payload};
    this.ensureChild();
    if (!this.child.stdin || this.child.stdin.destroyed) {
      this.onEvent({
        type: "bridge.error",
        code: "bridge_stdin_unavailable",
        message: "bridge stdin is unavailable",
      });
      return id;
    }
    try {
      this.child.stdin.write(`${JSON.stringify(request)}\n`);
    } catch (error) {
      this.alive = false;
      const message = error instanceof Error ? error.message : String(error);
      this.onEvent({
        type: "bridge.error",
        code: "bridge_send_failed",
        message,
      });
    }
    return id;
  }

  close(): void {
    this.alive = false;
    this.child.kill("SIGTERM");
  }
}
