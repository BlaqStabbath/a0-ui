// @vitest-environment node

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import crypto from "node:crypto";
import { spawn } from "node:child_process";

const ROOT = path.resolve(import.meta.dirname, "../..");
const INDEX_HTML = path.join(ROOT, "a0_ui", "web", "index.html");
const TRANSPORT_JS = path.join(ROOT, "a0_ui", "web", "js", "transport.js");
const CHROMIUM = process.env.CHROMIUM_BIN || "/usr/bin/chromium";

function textFrame(text) {
  const payload = Buffer.from(text);
  return Buffer.concat([Buffer.from([0x81, payload.length]), payload]);
}

function decodeClientFrame(buffer) {
  if (buffer.length < 6) return "";
  const len = buffer[1] & 0x7f;
  const mask = buffer.subarray(2, 6);
  const payload = buffer.subarray(6, 6 + len);
  return Buffer.from(payload.map((byte, index) => byte ^ mask[index % 4])).toString();
}

async function startTerminalWsServer() {
  const messages = [];
  const server = http.createServer();
  server.on("upgrade", (req, socket) => {
    const key = req.headers["sec-websocket-key"];
    const accept = crypto
      .createHash("sha1")
      .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
      .digest("base64");
    socket.write(
      [
        "HTTP/1.1 101 Switching Protocols",
        "Upgrade: websocket",
        "Connection: Upgrade",
        `Sec-WebSocket-Accept: ${accept}`,
        "",
        "",
      ].join("\r\n"),
    );
    socket.write(textFrame("browser-ws-ready"));
    socket.on("data", (chunk) => messages.push(decodeClientFrame(chunk)));
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return { server, port: server.address().port, messages };
}

function makeHarness(wsPort) {
  const html = fs.readFileSync(INDEX_HTML, "utf8");
  const transport = fs.readFileSync(TRANSPORT_JS, "utf8");
  return html
    .replace(/<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/xterm@[\s\S]*?<\/script>/, "<script>window.__termWrites=[]; window.Terminal=class{constructor(){this.cols=101;this.rows=33} loadAddon(){} open(){} focus(){} write(data){window.__termWrites.push(String(data))} onData(cb){this._onData=cb}}</script>")
    .replace(/<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/xterm-addon-fit@[\s\S]*?<\/script>/, "<script>window.FitAddon={FitAddon:class{fit(){}}}</script>")
    .replace('<script src="./js/transport.js"></script>', `<script>${transport}</script>`)
    .replace("<script>\nconst createTransport", `<script>\nwindow.pywebview={api:{get_status:async()=>({container:"agent-zero",webui_url:"http://localhost:5080",entry_cmd:"a0",ws_port:${wsPort},http_port:9}),get_logs:async()=>"",open_webui:async()=>({ok:true}),restart_a0:async()=>({ok:true})}};\nconst createTransport`);
}

async function launchChromium() {
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "a0-ui-chrome-"));
  const proc = spawn(CHROMIUM, [
    "--headless=new",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--remote-allow-origins=*",
    "--remote-debugging-port=0",
    `--user-data-dir=${userDataDir}`,
    "about:blank",
  ], { stdio: ["ignore", "pipe", "pipe"] });

  const endpoint = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("Timed out waiting for Chromium DevTools endpoint")), 10000);
    proc.stderr.on("data", (chunk) => {
      const match = String(chunk).match(/DevTools listening on (ws:\/\/.*)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1].trim());
      }
    });
    proc.on("exit", (code) => reject(new Error(`Chromium exited before DevTools endpoint: ${code}`)));
  });
  return { proc, endpoint, userDataDir };
}

class CdpClient {
  constructor(url) {
    this.url = url;
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
  }

  async connect() {
    this.ws = new WebSocket(this.url);
    this.ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.pending.has(msg.id)) {
        this.pending.get(msg.id)(msg);
        this.pending.delete(msg.id);
      } else {
        this.events.push(msg);
      }
    });
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", () => reject(new Error(`CDP WebSocket failed: ${this.url}`)), { once: true });
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve) => this.pending.set(id, resolve));
  }

  close() {
    this.ws.close();
  }
}

async function waitFor(fn, timeoutMs = 5000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const value = await fn();
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("Timed out waiting for condition");
}

describe("Chromium terminal WebSocket E2E", () => {
  it("connects by WebSocket without polling fallback and captures browser diagnostics", async () => {
    const wsServer = await startTerminalWsServer();
    const harnessPath = path.join(os.tmpdir(), `a0-ui-harness-${process.pid}.html`);
    fs.writeFileSync(harnessPath, makeHarness(wsServer.port));
    const browser = await launchChromium();
    const browserCdp = new CdpClient(browser.endpoint);
    await browserCdp.connect();

    try {
      const target = await browserCdp.send("Target.createTarget", { url: `file://${harnessPath}` });
      const { webSocketDebuggerUrl } = await fetch(`http://127.0.0.1:${new URL(browser.endpoint).port}/json/list`)
        .then((r) => r.json())
        .then((targets) => targets.find((t) => t.id === target.result.targetId));
      const page = new CdpClient(webSocketDebuggerUrl);
      await page.connect();
      await page.send("Runtime.enable");
      await page.send("Log.enable");
      await page.send("Network.enable");
      await page.send("Page.enable");
      await waitFor(() => page.send("Runtime.evaluate", { expression: "document.readyState === 'complete'", returnByValue: true }).then((r) => r.result.result.value));
      await page.send("Runtime.evaluate", {
        expression: "window.dispatchEvent(new Event('pywebviewready'))",
        returnByValue: true,
      });
      await waitFor(() => page.send("Runtime.evaluate", {
        expression: "document.getElementById('webui').src === 'http://localhost:5080/'",
        returnByValue: true,
      }).then((r) => r.result.result.value));

      await page.send("Runtime.evaluate", {
        expression: "document.querySelector('[data-pane=\"cli-pane\"]').click()",
        returnByValue: true,
      });

      await waitFor(() => page.send("Runtime.evaluate", {
        expression: "window.__termWrites && window.__termWrites.join('\\n').includes('browser-ws-ready')",
        returnByValue: true,
      }).then((r) => r.result.result.value));

      const mode = await page.send("Runtime.evaluate", {
        expression: "document.getElementById('status-dot').className",
        returnByValue: true,
      });
      const consoleAndNetworkProblems = page.events.filter((event) => (
        event.method === "Runtime.exceptionThrown"
        || event.method === "Log.entryAdded"
        || event.method === "Network.loadingFailed"
      ));

      expect(mode.result.result.value).toBe("status-dot ws");
      expect(wsServer.messages.some((msg) => msg.includes('"type":"resize"'))).toBe(true);
      expect(consoleAndNetworkProblems).toEqual([]);
    } finally {
      browserCdp.close();
      browser.proc.kill();
      wsServer.server.close();
      fs.rmSync(browser.userDataDir, { recursive: true, force: true });
      fs.rmSync(harnessPath, { force: true });
    }
  }, 20000);
});
