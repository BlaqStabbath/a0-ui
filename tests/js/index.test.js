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

async function bootUi({ withTransport = true } = {}) {
  const sockets = [];
  const termWrites = [];
  const terminalOptions = [];

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
      window.pywebview = {
        api: {
          get_status: async () => ({
            container: "agent-zero",
            webui_url: "http://localhost:5080",
            entry_cmd: "a0",
            ws_port: 12345,
            http_port: 23456,
          }),
          get_logs: async () => "logs",
          open_webui: async () => ({ ok: true }),
          restart_a0: async () => ({ ok: true }),
        },
      };
      window.Terminal = class {
        constructor(options) {
          this.cols = 120;
          this.rows = 40;
          terminalOptions.push(options);
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
      };
      window.FitAddon = { FitAddon: class { fit() {} } };
      window.WebSocket = FakeWebSocket;
      window.requestAnimationFrame = (callback) => callback();
    },
  });

  dom.window.dispatchEvent(new dom.window.Event("pywebviewready"));
  await Promise.resolve();
  await Promise.resolve();

  return { dom, sockets, termWrites, terminalOptions };
}

afterEach(() => {
  vi.useRealTimers();
});

describe("index.html terminal WebSocket lifecycle", () => {
  it("opens the terminal WebSocket with the pywebview status port", async () => {
    const { dom, sockets } = await bootUi();

    dom.window.document.querySelector('[data-pane="cli-pane"]').click();

    expect(sockets).toHaveLength(1);
    expect(sockets[0].url).toBe("ws://127.0.0.1:12345/");
  });

  it("initializes the Web UI iframe even if terminal transport script is missing", async () => {
    const { dom } = await bootUi({ withTransport: false });

    expect(dom.window.document.getElementById("webui").src).toBe("http://localhost:5080/");
    expect(dom.window.document.querySelector(".pane.active").id).toBe("webui-pane");
  });

  it("uses normal terminal font size and full-size terminal container", async () => {
    const { dom, terminalOptions } = await bootUi();

    dom.window.document.querySelector('[data-pane="cli-pane"]').click();

    expect(terminalOptions[0].fontSize).toBe(14);
    expect(dom.window.getComputedStyle(dom.window.document.getElementById("term")).height).toBe("100%");
    expect(dom.window.getComputedStyle(dom.window.document.getElementById("term")).width).toBe("100%");
  });

  it("sends terminal size to the PTY when the WebSocket opens", async () => {
    const { dom, sockets } = await bootUi();

    dom.window.document.querySelector('[data-pane="cli-pane"]').click();
    sockets[0].readyState = 1;
    sockets[0].onopen();

    expect(JSON.parse(sockets[0].sent)).toEqual({ type: "resize", cols: 120, rows: 40 });
  });

  it("does not count intentional retry teardown as another WebSocket failure", async () => {
    vi.useFakeTimers();
    const { dom, sockets, termWrites } = await bootUi();

    dom.window.document.querySelector('[data-pane="cli-pane"]').click();
    sockets[0].onclose();
    expect(termWrites.filter((w) => String(w).includes("connection lost"))).toHaveLength(1);

    await vi.runOnlyPendingTimersAsync();

    expect(sockets).toHaveLength(2);
    expect(termWrites.filter((w) => String(w).includes("connection lost"))).toHaveLength(1);
  });
});
