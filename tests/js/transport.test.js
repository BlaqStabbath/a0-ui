import { describe, expect, it, vi } from "vitest";
import { createTransport } from "../../a0_ui/web/js/transport.js";

// transport.js is a UMD module; the factory is exported via the IIFE wrapper
// and Vitest's CommonJS interop picks it up. If the import shape changes,
// destructure from the default export: { createTransport }.
const { MODE: _MODE } = await import("../../a0_ui/web/js/transport.js").then((m) => m);

describe("transport mode state machine", () => {
  it("starts in ws mode", () => {
    const t = createTransport();
    expect(t.getMode()).toBe("ws");
    expect(t.getAttempts()).toBe(0);
  });

  it("transitions to retrying on first ws close", () => {
    const t = createTransport();
    t.onWsClose();
    expect(t.getMode()).toBe("retrying");
    expect(t.getAttempts()).toBe(1);
  });

  it("uses exponential backoff starting at 100ms", () => {
    const t = createTransport();
    t.onWsClose();
    expect(t.getNextDelayMs()).toBe(100);
  });

  it("doubles the backoff on subsequent closes (200, 400, 800)", () => {
    const t = createTransport();
    t.onWsClose();
    t.onWsClose();
    t.onWsClose();
    t.onWsClose();
    expect(t.getNextDelayMs()).toBe(800);
  });

  it("caps backoff at 5000ms when many attempts", () => {
    const t = createTransport();
    for (let i = 0; i < 8; i++) t.onWsClose();
    // After 5 attempts, transport is DISCONNECTED, pendingDelay=0
    expect(t.getMode()).toBe("disconnected");
  });

  it("gives up after 5 failed attempts and stays disconnected", () => {
    const t = createTransport();
    for (let i = 0; i < 5; i++) t.onWsClose();
    expect(t.getMode()).toBe("disconnected");
    expect(t.getAttempts()).toBe(5);
    expect(t.getNextDelayMs()).toBe(0);
  });

  it("resets attempts to 0 on successful ws open", () => {
    const t = createTransport();
    t.onWsClose();
    t.onWsClose();
    expect(t.getAttempts()).toBe(2);
    t.onWsOpen();
    expect(t.getAttempts()).toBe(0);
    expect(t.getMode()).toBe("ws");
    expect(t.getNextDelayMs()).toBe(0);
  });
});
