/**
 * Show Tracker - Extension Popup Script
 *
 * Manages the popup UI: connection status, tracking toggle,
 * and link to the main dashboard.
 */

const APP_URL = "http://localhost:7600/";

const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const trackingToggle = document.getElementById("trackingToggle");
const trackingInfo = document.getElementById("trackingInfo");
const trackingTitle = document.getElementById("trackingTitle");
const openAppLink = document.getElementById("openAppLink");

// ---------------------------------------------------------------------------
// Initialise
// ---------------------------------------------------------------------------

function init() {
    // Request current status from background
    chrome.runtime.sendMessage({ type: "get-status" }, (response) => {
        if (chrome.runtime.lastError || !response) {
            setStatus("disconnected", "Cannot reach background");
            return;
        }

        setStatus(response.connectionStatus, response.lastError);
        trackingToggle.checked = response.trackingEnabled !== false;
    });

    // Fetch currently-watching info from the API
    fetchCurrentlyWatching();
}

// ---------------------------------------------------------------------------
// Status Display
// ---------------------------------------------------------------------------

function setStatus(status, error) {
    statusDot.className = "status-dot";

    if (status === "connected") {
        statusDot.classList.add("connected");
        statusText.textContent = "Connected to service";
    } else if (status === "disconnected") {
        statusDot.classList.add("disconnected");
        statusText.textContent = error
            ? `Disconnected: ${error}`
            : "Service unreachable";
    } else {
        statusText.textContent = "Checking...";
    }
}

// ---------------------------------------------------------------------------
// Currently Watching
// ---------------------------------------------------------------------------

async function fetchCurrentlyWatching() {
    try {
        const resp = await fetch(`${APP_URL}api/currently-watching`, {
            signal: AbortSignal.timeout(3000),
        });
        if (!resp.ok) return;

        const data = await resp.json();
        if (data.is_watching && data.title) {
            trackingInfo.style.display = "block";
            trackingTitle.textContent = data.title;
        } else {
            trackingInfo.style.display = "none";
        }
    } catch (_) {
        // Service unavailable — hide tracking info
        trackingInfo.style.display = "none";
    }
}

// ---------------------------------------------------------------------------
// Event Handlers
// ---------------------------------------------------------------------------

trackingToggle.addEventListener("change", () => {
    chrome.runtime.sendMessage({
        type: "toggle-tracking",
        enabled: trackingToggle.checked,
    });
});

openAppLink.addEventListener("click", (e) => {
    e.preventDefault();
    chrome.tabs.create({ url: APP_URL });
    window.close();
});

// Listen for status updates from background
chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "connection-status") {
        setStatus(message.status, message.error);
    }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

init();
