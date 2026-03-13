/**
 * Show Tracker - Background Service Worker (Manifest V3)
 *
 * Receives media events from content scripts, enriches them with tab
 * metadata, and forwards them to the local media identification service.
 */

const MEDIA_SERVICE_URL = "http://localhost:7600/api/media-event";

// ---------------------------------------------------------------------------
// Connection status tracking
// ---------------------------------------------------------------------------

let connectionStatus = "unknown"; // "connected" | "disconnected" | "unknown"
let lastError = null;

function updateConnectionStatus(status, error) {
    connectionStatus = status;
    lastError = error || null;
    // Notify popup if open
    chrome.runtime.sendMessage({
        type: "connection-status",
        status: connectionStatus,
        error: lastError,
    }).catch(() => {
        // Popup not open — ignore
    });
}

// ---------------------------------------------------------------------------
// Message handling
// ---------------------------------------------------------------------------

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    // Handle popup requesting status
    if (message.type === "get-status") {
        chrome.storage.local.get(["trackingEnabled"], (result) => {
            sendResponse({
                connectionStatus,
                lastError,
                trackingEnabled: result.trackingEnabled !== false,
            });
        });
        return true; // async sendResponse
    }

    // Handle popup toggling tracking
    if (message.type === "toggle-tracking") {
        chrome.storage.local.set({ trackingEnabled: message.enabled });
        sendResponse({ ok: true });
        return false;
    }

    // Handle content script media events
    if (message.source === "show-tracker-content") {
        // Check if tracking is enabled
        chrome.storage.local.get(["trackingEnabled"], (result) => {
            if (result.trackingEnabled === false) {
                return; // Tracking disabled
            }

            // Enrich with tab info
            message.tab_url = sender.tab?.url || "";
            message.tab_id = sender.tab?.id || 0;

            // Forward to local media identification service
            fetch(MEDIA_SERVICE_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(message),
            })
                .then((resp) => {
                    if (resp.ok) {
                        updateConnectionStatus("connected", null);
                    } else {
                        updateConnectionStatus(
                            "disconnected",
                            `HTTP ${resp.status}`
                        );
                    }
                })
                .catch((err) => {
                    updateConnectionStatus("disconnected", err.message);
                    console.error("Show Tracker: media service unreachable:", err.message);
                });
        });
    }

    return false;
});

// ---------------------------------------------------------------------------
// Periodic connection check
// ---------------------------------------------------------------------------

async function checkConnection() {
    try {
        const resp = await fetch("http://localhost:7600/api/health", {
            method: "GET",
            signal: AbortSignal.timeout(5000),
        });
        if (resp.ok) {
            updateConnectionStatus("connected", null);
        } else {
            updateConnectionStatus("disconnected", `HTTP ${resp.status}`);
        }
    } catch (err) {
        updateConnectionStatus("disconnected", err.message);
    }
}

// Check connection on startup and then every 30 seconds
checkConnection();
setInterval(checkConnection, 30000);
