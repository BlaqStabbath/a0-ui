import { JSDOM } from "jsdom";
import fs from "node:fs";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createTransport } from "../../a0_ui/web/js/transport.js";

const ROOT = path.resolve(import.meta.dirname, "../..");
const INDEX_HTML = path.join(ROOT, "a0_ui", "web", "index.html");

function inlineOnlyHtml() {
  return fs
    .readFileSync(INDEX_HTML, "utf8")
    .replace(/<script src="https:[\s\S]*?<\/script>/g, "")
    .replace(/<script src="\.\/js\/transport\.js"><\/script>/g, "");
}

async function bootUi({ withTransport = true, apiOverrides = {}, fetchImpl } = {}) {
  const sockets = [];
  const termWrites = [];
  const terminalOptions = [];
  const terminalInstances = [];

  class FakeWebSocket {
    static OPEN = 1;

    constructor(url) {
      this.url = url;
      this.readyState = 0;
      sockets.push(this);
    }

    close() {
      this.readyState = 3;
      this.onclose?.();
    }

    send(data) {
      this.sent = data;
    }
  }

  const dom = new JSDOM(inlineOnlyHtml(), {
    runScripts: "dangerously",
    url: "file:///a0_ui/web/index.html",
    beforeParse(window) {
      if (withTransport) window.a0Transport = { createTransport };
      const api = {
        get_status: async () => ({
          container: "agent-zero",
          webui_url: "http://127.0.0.1:5080",
          entry_cmd: "a0",
          ws_port: 12345,
          http_port: 23456,
        }),
        get_logs: async () => "logs",
        open_webui: async () => ({ ok: true }),
        restart_a0: async () => ({ ok: true }),
        restart_cli: async () => ({ ok: true }),
        check_a0_ready: async () => ({ ok: true, running: true, webui_ready: true }),
        ...apiOverrides,
      };
      window.pywebview = {
        api: {
          ...api,
        },
      };
      window.Terminal = class {
        constructor(options) {
          this.cols = 120;
          this.rows = 40;
          this.resizes = [];
          this.disposed = false;
          this._core = { _renderService: { dimensions: { css: { cell: { width: 10, height: 20 } } } } };
          terminalOptions.push(options);
          terminalInstances.push(this);
        }
        loadAddon() {}
        open() {}
        focus() {}
        write(data) {
          termWrites.push(data);
        }
        onData(callback) {
          this.onDataCallback = callback;
        }
        resize(cols, rows) {
          this.cols = cols;
          this.rows = rows;
          this.resizes.push({ cols, rows });
        }
        dispose() {
          this.disposed = true;
        }
      };
      window.FitAddon = { FitAddon: class { fit() {} } };
      window.WebSocket = FakeWebSocket;
      if (fetchImpl) window.fetch = fetchImpl;
      window.requestAnimationFrame = (callback) => callback();
    },
  });

  dom.window.dispatchEvent(new dom.window.Event("pywebviewready"));
  await Promise.resolve();
  await Promise.resolve();

  return { dom, sockets, termWrites, terminalOptions, terminalInstances };
}

async function openTerminal(dom) {
  dom.window.document.querySelector('[data-pane="cli-pane"]').click();
  await Promise.resolve();
  await Promise.resolve();
}

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

afterEach(() => {
  vi.useRealTimers();
});

describe("index.html terminal WebSocket lifecycle", () => {
  it("opens the terminal WebSocket with the pywebview status port", async () => {
    const { dom, sockets } = await bootUi();

    await openTerminal(dom);

    expect(sockets).toHaveLength(1);
    expect(sockets[0].url).toBe("ws://127.0.0.1:12345/");
  });

  it("initializes the Web UI iframe even if terminal transport script is missing", async () => {
    const { dom } = await bootUi({ withTransport: false });

    expect(dom.window.document.getElementById("webui").src).toBe("http://127.0.0.1:5080/");
    expect(dom.window.document.querySelector(".pane.active").id).toBe("webui-pane");
  });

  it("uses normal terminal font size and full-size terminal container", async () => {
    const { dom, terminalOptions } = await bootUi();

    await openTerminal(dom);

    expect(terminalOptions[0].fontSize).toBe(14);
    expect(dom.window.getComputedStyle(dom.window.document.getElementById("content")).width).toBe("100vw");
    expect(dom.window.getComputedStyle(dom.window.document.getElementById("content")).height).toBe("calc(100vh - var(--panel-h))");
    expect(dom.window.getComputedStyle(dom.window.document.getElementById("cli-pane")).height).toBe("100%");
    expect(dom.window.getComputedStyle(dom.window.document.getElementById("cli-pane")).width).toBe("100%");
    expect(dom.window.getComputedStyle(dom.window.document.getElementById("term")).height).toBe("100%");
    expect(dom.window.getComputedStyle(dom.window.document.getElementById("term")).width).toBe("100%");
  });

  it("manually resizes terminal to the content panel dimensions", async () => {
    const { dom, terminalInstances } = await bootUi();
    const termEl = dom.window.document.getElementById("term");
    termEl.getBoundingClientRect = () => ({ width: 1000, height: 600 });

    await openTerminal(dom);

    const terminal = terminalInstances[0];
    expect(terminal.resizes.at(-1)).toEqual({ cols: 100, rows: 30 });
  });

  it("sends terminal size to the PTY when the WebSocket opens", async () => {
    const { dom, sockets } = await bootUi();

    await openTerminal(dom);
    sockets[0].readyState = 1;
    sockets[0].onopen();

    expect(JSON.parse(sockets[0].sent)).toEqual({ type: "resize", cols: 120, rows: 40 });
  });

  it("does not count intentional retry teardown as another WebSocket failure", async () => {
    vi.useFakeTimers();
    const { dom, sockets, termWrites } = await bootUi();

    await openTerminal(dom);
    sockets[0].onclose();
    expect(termWrites.filter((w) => String(w).includes("connection lost"))).toHaveLength(1);

    await vi.runOnlyPendingTimersAsync();

    expect(sockets).toHaveLength(2);
    expect(termWrites.filter((w) => String(w).includes("connection lost"))).toHaveLength(1);
  });

  it("requires WebSocket and does not fall back to polling after retry exhaustion", async () => {
    vi.useFakeTimers();
    const { dom, sockets, termWrites } = await bootUi();

    await openTerminal(dom);
    for (let i = 0; i < 5; i++) {
      sockets.at(-1).onclose();
      await vi.runOnlyPendingTimersAsync();
    }

    expect(termWrites.some((w) => String(w).includes("polling fallback disabled"))).toBe(true);
    expect(dom.window.document.getElementById("status-dot").className).toBe("status-dot disconnected");
    expect(dom.window.document.getElementById("btn-reconnect").classList.contains("visible")).toBe(true);
    expect(sockets).toHaveLength(5);
  });

  it("uses backend readiness probe during restart instead of browser fetching the Web UI", async () => {
    vi.useFakeTimers();
    const restart_a0 = vi.fn(async () => ({ ok: true }));
    const check_a0_ready = vi.fn(async () => ({ ok: true, running: true, webui_ready: true }));
    const fetchImpl = vi.fn(async () => {
      throw new Error("browser fetch should not be used for restart readiness");
    });
    const { dom } = await bootUi({ apiOverrides: { restart_a0, check_a0_ready }, fetchImpl });

    dom.window.document.getElementById("btn-restart").click();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(2000);
    await Promise.resolve();

    expect(restart_a0).toHaveBeenCalledOnce();
    expect(check_a0_ready).toHaveBeenCalledOnce();
    expect(fetchImpl).not.toHaveBeenCalledWith("http://127.0.0.1:5080", expect.anything());
    expect(dom.window.document.getElementById("status").textContent).toBe("Container: agent-zero | WebUI: http://127.0.0.1:5080 | Shell: a0");
    expect(dom.window.document.getElementById("toast").textContent).toBe("Container is up. Reloading Web UI.");
    expect(dom.window.document.getElementById("toast").classList.contains("visible")).toBe(true);
    expect(dom.window.document.getElementById("webui").src).toBe("http://127.0.0.1:5080/");
    expect(dom.window.document.querySelector(".pane.active").id).toBe("webui-pane");
  });

  it("recreates the terminal session after a successful restart when the CLI is open", async () => {
    vi.useFakeTimers();
    const restart_cli = vi.fn(async () => ({ ok: true }));
    const { dom, sockets, terminalInstances } = await bootUi({ apiOverrides: { restart_cli } });

    await openTerminal(dom);
    expect(sockets).toHaveLength(1);
    expect(terminalInstances).toHaveLength(1);

    dom.window.document.getElementById("btn-restart").click();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(2000);
    await Promise.resolve();

    expect(sockets).toHaveLength(2);
    expect(restart_cli).toHaveBeenCalledOnce();
    expect(sockets[0].readyState).toBe(3);
    expect(sockets[1].url).toBe("ws://127.0.0.1:12345/");
    expect(terminalInstances).toHaveLength(2);
    expect(terminalInstances[0].disposed).toBe(true);
    expect(terminalInstances[1].disposed).toBe(false);
  });

  it("refreshes logs live only while the Logs tab is active", async () => {
    vi.useFakeTimers();
    let logCalls = 0;
    const get_logs = vi.fn(async () => `logs-${++logCalls}`);
    const { dom } = await bootUi({ apiOverrides: { get_logs } });

    dom.window.document.querySelector('[data-pane="logs-pane"]').click();
    await flushPromises();

    expect(get_logs).toHaveBeenCalledTimes(1);
    expect(dom.window.document.getElementById("logs").textContent).toBe("logs-1");

    await vi.advanceTimersByTimeAsync(2000);
    await flushPromises();
    expect(get_logs).toHaveBeenCalledTimes(2);
    expect(dom.window.document.getElementById("logs").textContent).toBe("logs-2");

    dom.window.document.querySelector('[data-pane="webui-pane"]').click();
    await vi.advanceTimersByTimeAsync(4000);
    await flushPromises();

    expect(get_logs).toHaveBeenCalledTimes(2);
  });
});
