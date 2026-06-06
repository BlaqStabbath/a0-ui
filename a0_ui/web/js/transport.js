(function (root, factory) {
  const exported = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = exported;
  } else if (typeof root !== "undefined") {
    root.a0Transport = exported;
  }
})(typeof window !== "undefined" ? window : globalThis, function () {
  const MODE = {
    WS: "ws",
    DISCONNECTED: "disconnected",
    RETRYING: "retrying",
    POLLING: "polling",
  };

  const MAX_ATTEMPTS = 5;
  const BACKOFF_BASE_MS = 100;
  const BACKOFF_CAP_MS = 5000;

  function createTransport() {
    let mode = MODE.WS;
    let attempts = 0;
    let pendingDelay = 0;
    let pollingInterval = 0;

    function getMode() {
      return mode;
    }

    function getAttempts() {
      return attempts;
    }

    function getNextDelayMs() {
      return pendingDelay;
    }

    function getPollingInterval() {
      return pollingInterval;
    }

    function onWsOpen() {
      attempts = 0;
      pendingDelay = 0;
      pollingInterval = 0;
      mode = MODE.WS;
    }

    function onWsClose() {
      // If we're in polling mode, the close is informational; polling
      // handles its own recovery. Don't change the mode.
      if (mode === MODE.POLLING) return;
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

    function startPolling(intervalMs) {
      pollingInterval = intervalMs;
      mode = MODE.POLLING;
    }

    function stopPolling() {
      pollingInterval = 0;
      if (mode === MODE.POLLING) mode = MODE.WS;
    }

    return {
      getMode,
      getAttempts,
      getNextDelayMs,
      getPollingInterval,
      clearPending,
      onWsOpen,
      onWsClose,
      startPolling,
      stopPolling,
      MODE,
    };
  }

  return { createTransport, MODE };
});

