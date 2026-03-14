# Browser Extension Specification

## Purpose

The browser extension provides deep media identification for web-based viewing. While ActivityWatch's web watcher gives us tab URLs and titles, our extension goes further: scraping structured metadata, parsing platform-specific page content, detecting video playback state, and sending enriched events to the media identification service.

## Architecture

The extension consists of three parts:

1. **Content Script:** Injected into every page. Scrapes metadata, detects video elements, monitors playback state.
2. **Background Service Worker:** Receives data from content scripts, filters for media-relevant events, posts to the local media identification service.
3. **Popup (minimal):** Status indicator (connected/disconnected), toggle on/off, link to main app UI.

## Content Script: Metadata Extraction

### Extraction Priority

For each page, extract metadata in this order (highest reliability first):

```javascript
function extractMediaMetadata() {
    const metadata = {};

    // 1. URL pattern matching (most reliable for known platforms)
    metadata.url = window.location.href;
    metadata.url_match = matchUrlPatterns(window.location.href);

    // 2. Schema.org structured data (VideoObject, TVEpisode)
    metadata.schema = extractSchemaOrg();

    // 3. Open Graph tags
    metadata.og = extractOpenGraph();

    // 4. Standard meta tags
    metadata.meta = extractMetaTags();

    // 5. Page title (fallback)
    metadata.title = document.title;

    // 6. Video element inspection
    metadata.video = inspectVideoElements();

    return metadata;
}
```

### Schema.org Extraction

Streaming sites and many content sites embed schema.org structured data (either as JSON-LD or microdata). This is the richest metadata source.

```javascript
function extractSchemaOrg() {
    const results = [];

    // JSON-LD (preferred format, used by YouTube, Netflix, many others)
    document.querySelectorAll('script[type="application/ld+json"]').forEach(script => {
        try {
            const data = JSON.parse(script.textContent);
            // Look for VideoObject, TVEpisode, TVSeries, Movie types
            if (data["@type"] && ["VideoObject", "TVEpisode", "TVSeries",
                                   "Movie", "Episode"].includes(data["@type"])) {
                results.push({
                    type: data["@type"],
                    name: data.name,
                    description: data.description,
                    duration: data.duration,          // ISO 8601 duration
                    episodeNumber: data.episodeNumber,
                    seasonNumber: data.partOfSeason?.seasonNumber,
                    seriesName: data.partOfSeries?.name,
                    datePublished: data.datePublished,
                });
            }
            // Handle nested @graph arrays
            if (Array.isArray(data["@graph"])) {
                // Recurse into graph entries
            }
        } catch (e) { /* malformed JSON-LD, skip */ }
    });

    return results;
}
```

### Open Graph Tags

```javascript
function extractOpenGraph() {
    const og = {};
    document.querySelectorAll('meta[property^="og:"]').forEach(meta => {
        const key = meta.getAttribute("property").replace("og:", "");
        og[key] = meta.getAttribute("content");
    });
    // Relevant fields: og:title, og:type (should be "video.episode" or "video.tv_show"),
    // og:video:series, og:video:tag
    return og;
}
```

### Video Element Inspection

Detect if a video is actually playing on the page:

```javascript
function inspectVideoElements() {
    const videos = document.querySelectorAll("video");
    const results = [];

    videos.forEach(video => {
        results.push({
            playing: !video.paused && !video.ended,
            currentTime: video.currentTime,
            duration: video.duration,
            src: video.src || video.querySelector("source")?.src,
            // Check for common player wrappers
            playerType: detectPlayerType(video),
        });
    });

    return results;
}

function detectPlayerType(videoElement) {
    // Walk up the DOM to identify the player framework
    let el = videoElement;
    for (let i = 0; i < 10; i++) {
        el = el.parentElement;
        if (!el) break;
        if (el.classList.contains("html5-video-player")) return "youtube";
        if (el.classList.contains("NFPlayer")) return "netflix";
        if (el.id === "vilos-player") return "crunchyroll";
        // Add more player signatures as discovered
    }
    return "unknown";
}
```

## Content Script: Playback Monitoring

The content script monitors video playback state and sends heartbeats while media is playing.

```javascript
let heartbeatInterval = null;
let lastMediaEvent = null;

function startPlaybackMonitoring() {
    // Observe all video elements (including dynamically created ones)
    const observer = new MutationObserver(() => {
        document.querySelectorAll("video").forEach(attachVideoListeners);
    });
    observer.observe(document.body, { childList: true, subtree: true });

    // Attach to existing videos
    document.querySelectorAll("video").forEach(attachVideoListeners);
}

function attachVideoListeners(video) {
    if (video._showTrackerAttached) return;
    video._showTrackerAttached = true;

    video.addEventListener("play", () => onPlaybackStart(video));
    video.addEventListener("pause", () => onPlaybackPause(video));
    video.addEventListener("ended", () => onPlaybackEnd(video));
}

function onPlaybackStart(video) {
    const metadata = extractMediaMetadata();
    lastMediaEvent = { type: "play", metadata, timestamp: Date.now() };
    sendToService(lastMediaEvent);

    // Start heartbeat — send current state every 30 seconds
    clearInterval(heartbeatInterval);
    heartbeatInterval = setInterval(() => {
        if (!video.paused && !video.ended) {
            sendToService({
                type: "heartbeat",
                metadata: extractMediaMetadata(),
                position: video.currentTime,
                duration: video.duration,
                timestamp: Date.now()
            });
        }
    }, 30000);
}

function onPlaybackPause(video) {
    clearInterval(heartbeatInterval);
    sendToService({ type: "pause", metadata: lastMediaEvent?.metadata, timestamp: Date.now() });
}

function onPlaybackEnd(video) {
    clearInterval(heartbeatInterval);
    sendToService({ type: "ended", metadata: lastMediaEvent?.metadata, timestamp: Date.now() });
}
```

## Background Service Worker

Receives events from content scripts and forwards them to the media identification service.

```javascript
// background.js (Manifest V3 service worker)

const MEDIA_SERVICE_URL = "http://localhost:7600/api/media-event";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.source === "show-tracker-content") {
        // Add tab info
        message.tab_url = sender.tab?.url;
        message.tab_id = sender.tab?.id;

        // Forward to local media identification service
        fetch(MEDIA_SERVICE_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(message)
        }).catch(err => {
            console.error("Media service unreachable:", err);
        });
    }
});
```

## Platform-Specific Scraping Notes

### YouTube

YouTube is the best-supported platform. The YouTube Data API (called from the media identification service, not the extension) provides full video metadata given a video ID extracted from the URL. The extension only needs to extract the video ID from the URL — the service handles the rest.

However, for YouTube series/playlists, the extension should also extract:
- Playlist ID (from URL parameter `list=`)
- Video index in playlist (from URL parameter `index=`)

### Netflix

Netflix renders most content dynamically via JavaScript. The extension can extract:
- Content ID from URL (`/watch/<id>`)
- Page title (usually includes show name)
- Netflix uses Cadmium player — video element is present but metadata is sparse in the DOM

The media identification service will need a Netflix-to-TMDb mapping. The Netflix content ID can be cross-referenced via the TMDb API's `find` endpoint using `external_source=netflix_id` (limited support) or by searching TMDb with the extracted title.

### Pirate Sites (Generic)

These sites vary enormously in structure but share common patterns:
- Episode info in URL slugs (most common, most reliable)
- Episode info in page title
- Video hosted on third-party players (often in iframes)
- Minimal or no structured metadata

For iframe-hosted video players, the content script in the parent frame can still detect the iframe and extract its `src` URL, which sometimes contains episode identifiers. Direct inspection of the iframe content is blocked by same-origin policy unless the extension has explicit host permissions.

**Manifest permissions strategy:** Request `<all_urls>` permission (or use `activeTab` with user gesture) to enable scraping across arbitrary sites. This is necessary for pirate site support but requires justification in extension store reviews.

## Manifest Configuration

```json
{
    "manifest_version": 3,
    "name": "Show Tracker",
    "version": "0.1.0",
    "description": "Automatic episode tracking across all streaming sites",
    "permissions": [
        "activeTab",
        "tabs",
        "storage"
    ],
    "host_permissions": [
        "<all_urls>"
    ],
    "background": {
        "service_worker": "background.js"
    },
    "content_scripts": [
        {
            "matches": ["<all_urls>"],
            "js": ["content.js"],
            "run_at": "document_idle"
        }
    ],
    "action": {
        "default_popup": "popup.html",
        "default_icon": "icon.png"
    }
}
```

### Extension Store Considerations

- Chrome Web Store and Firefox Add-ons will review the `<all_urls>` permission closely. Justify it in the store listing as necessary for cross-site media tracking.
- The extension must have a clear privacy policy explaining what data is collected and that it stays local.
- Content scripts should be lightweight — avoid injecting heavy libraries. All parsing and identification happens in the local service, not in the extension.

## Communication Protocol

Events sent from extension to media identification service follow this schema:

```typescript
interface MediaEvent {
    type: "play" | "pause" | "ended" | "heartbeat" | "page_load";
    timestamp: number;          // Unix ms
    tab_url: string;
    tab_id: number;
    metadata: {
        url: string;
        url_match: UrlMatchResult | null;
        schema: SchemaOrgData[];
        og: Record<string, string>;
        title: string;
        video: VideoElementInfo[];
    };
    position?: number;          // Current playback position in seconds
    duration?: number;          // Total video duration in seconds
}
```
