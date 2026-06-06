(function (root, factory) {
  const exported = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = exported;
  } else if (typeof root !== "undefined") {
    root.a0Transport = exported;
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  const MODE = { WS: "ws", DISCONNECTED: "disconnected", RETRYING: "retrying" };

  const MAX_ATTEMPTS = 5;
  const BACKOFF_BASE_MS = 100;
  const BACKOFF_CAP_MS = 5000;

  function createTransport() {
    let mode = MODE.WS;
    let attempts = 0;
    let pendingDelay = 0;

    function getMode() {
      return mode;
    }

    function getAttempts() {
      return attempts;
    }

    function getNextDelayMs() {
      return pendingDelay;
    }

    function onWsOpen() {
      attempts = 0;
      pendingDelay = 0;
      mode = MODE.WS;
    }

    function onWsClose() {
      attempts++;
      if (attempts >= MAX_ATTEMPTS) {
        mode = MODE.DISCONNECTED;
        pendingDelay = 0;
        return;
      }
      pendingDelay = Math.min(BACKOFF_BASE_MS * 2 ** (attempts - 1), BACKOFF_CAP_MS);
      mode = MODE.RETRYING;
    }

    function clearPending() {
      pendingDelay = 0;
    }

    return { getMode, getAttempts, getNextDelayMs, clearPending, onWsOpen, onWsClose, MODE };
  }

  return { createTransport, MODE };
});

