/**
 * Show Tracker - Extension Popup Script (Firefox)
 *
 * Manages the popup UI: connection status, tracking toggle,
 * and link to the main dashboard. Uses browser.* Promise-based APIs.
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
    browser.runtime.sendMessage({ type: "get-status" }).then((response) => {
        if (!response) {
            setStatus("disconnected", "Cannot reach background");
            return;
        }

        setStatus(response.connectionStatus, response.lastError);
        trackingToggle.checked = response.trackingEnabled !== false;
    }).catch(() => {
        setStatus("disconnected", "Cannot reach background");
    });

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
        const resp = await fetch(`${APP_URL}api/currently-watching`);
        if (!resp.ok) return;

        const data = await resp.json();
        if (data.is_watching && data.title) {
            trackingInfo.style.display = "block";
            trackingTitle.textContent = data.title;
        } else {
            trackingInfo.style.display = "none";
        }
    } catch (_) {
        trackingInfo.style.display = "none";
    }
}

// ---------------------------------------------------------------------------
// Event Handlers
// ---------------------------------------------------------------------------

trackingToggle.addEventListener("change", () => {
    browser.runtime.sendMessage({
        type: "toggle-tracking",
        enabled: trackingToggle.checked,
    });
});

openAppLink.addEventListener("click", (e) => {
    e.preventDefault();
    browser.tabs.create({ url: APP_URL });
    window.close();
});

browser.runtime.onMessage.addListener((message) => {
    if (message.type === "connection-status") {
        setStatus(message.status, message.error);
    }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

init();
