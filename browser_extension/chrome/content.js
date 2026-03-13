/**
 * Show Tracker - Content Script
 *
 * Injected into every page. Extracts media metadata from the DOM,
 * monitors video playback, and sends events to the background service worker.
 */

// ---------------------------------------------------------------------------
// Metadata Extraction
// ---------------------------------------------------------------------------

/**
 * Extract all available media metadata from the current page.
 * Uses a priority-ordered approach: URL patterns > schema.org > OG > meta > title.
 */
function extractMediaMetadata() {
    const metadata = {};

    // 1. URL + URL pattern matching
    metadata.url = window.location.href;
    metadata.url_match = matchUrlPatterns(window.location.href);

    // 2. Schema.org structured data
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

// ---------------------------------------------------------------------------
// URL Pattern Matching
// ---------------------------------------------------------------------------

const URL_PATTERNS = [
    {
        name: "youtube",
        pattern: /(?:youtube\.com\/watch\?.*v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/,
        extract: (match, url) => {
            const params = new URL(url).searchParams;
            return {
                platform: "youtube",
                content_id: match[1],
                extra: {
                    list: params.get("list"),
                    index: params.get("index"),
                },
            };
        },
    },
    {
        name: "netflix",
        pattern: /netflix\.com\/watch\/(\d+)/,
        extract: (match) => ({
            platform: "netflix",
            content_id: match[1],
            extra: {},
        }),
    },
    {
        name: "crunchyroll",
        pattern: /crunchyroll\.com\/(?:\w{2}\/)?watch\/([a-zA-Z0-9]+)/,
        extract: (match) => ({
            platform: "crunchyroll",
            content_id: match[1],
            extra: {},
        }),
    },
    {
        name: "disneyplus",
        pattern: /disneyplus\.com\/video\/([a-f0-9-]+)/,
        extract: (match) => ({
            platform: "disneyplus",
            content_id: match[1],
            extra: {},
        }),
    },
    {
        name: "hulu",
        pattern: /hulu\.com\/watch\/([a-f0-9-]+)/,
        extract: (match) => ({
            platform: "hulu",
            content_id: match[1],
            extra: {},
        }),
    },
    {
        name: "primevideo",
        pattern: /(?:primevideo|amazon)\.com\/.*\/([A-Z0-9]+)/,
        extract: (match) => ({
            platform: "primevideo",
            content_id: match[1],
            extra: {},
        }),
    },
    {
        // Generic: season/episode in URL slug
        name: "generic_episode",
        pattern: /[/-]s(\d{1,2})e(\d{1,3})/i,
        extract: (match) => ({
            platform: "generic",
            content_id: null,
            extra: {
                season: parseInt(match[1], 10),
                episode: parseInt(match[2], 10),
            },
        }),
    },
];

function matchUrlPatterns(url) {
    for (const { pattern, extract } of URL_PATTERNS) {
        const match = url.match(pattern);
        if (match) {
            return extract(match, url);
        }
    }
    return null;
}

// ---------------------------------------------------------------------------
// Schema.org Extraction (JSON-LD)
// ---------------------------------------------------------------------------

function extractSchemaOrg() {
    const results = [];
    const MEDIA_TYPES = [
        "VideoObject",
        "TVEpisode",
        "TVSeries",
        "Movie",
        "Episode",
    ];

    document
        .querySelectorAll('script[type="application/ld+json"]')
        .forEach((script) => {
            try {
                const data = JSON.parse(script.textContent);
                processSchemaNode(data, results, MEDIA_TYPES);
            } catch (_) {
                // Malformed JSON-LD — skip
            }
        });

    return results;
}

function processSchemaNode(data, results, types) {
    if (!data || typeof data !== "object") return;

    if (data["@type"] && types.includes(data["@type"])) {
        results.push({
            type: data["@type"],
            name: data.name || null,
            description: data.description || null,
            duration: data.duration || null,
            episodeNumber: data.episodeNumber || null,
            seasonNumber:
                data.partOfSeason?.seasonNumber ||
                data.seasonNumber ||
                null,
            seriesName: data.partOfSeries?.name || null,
            datePublished: data.datePublished || null,
        });
    }

    // Handle @graph arrays
    if (Array.isArray(data["@graph"])) {
        data["@graph"].forEach((node) =>
            processSchemaNode(node, results, types)
        );
    }
}

// ---------------------------------------------------------------------------
// Open Graph Tags
// ---------------------------------------------------------------------------

function extractOpenGraph() {
    const og = {};
    document.querySelectorAll('meta[property^="og:"]').forEach((meta) => {
        const key = meta.getAttribute("property").replace("og:", "");
        og[key] = meta.getAttribute("content");
    });
    return og;
}

// ---------------------------------------------------------------------------
// Standard Meta Tags
// ---------------------------------------------------------------------------

function extractMetaTags() {
    const meta = {};
    const RELEVANT = [
        "description",
        "keywords",
        "title",
        "author",
        "video:series",
        "video:tag",
    ];
    RELEVANT.forEach((name) => {
        const el =
            document.querySelector(`meta[name="${name}"]`) ||
            document.querySelector(`meta[property="${name}"]`);
        if (el) {
            meta[name] = el.getAttribute("content");
        }
    });
    return meta;
}

// ---------------------------------------------------------------------------
// Video Element Inspection
// ---------------------------------------------------------------------------

function inspectVideoElements() {
    const videos = document.querySelectorAll("video");
    const results = [];

    videos.forEach((video) => {
        results.push({
            playing: !video.paused && !video.ended,
            currentTime: video.currentTime || 0,
            duration: video.duration || 0,
            src: video.src || video.querySelector("source")?.src || null,
            playerType: detectPlayerType(video),
        });
    });

    return results;
}

function detectPlayerType(videoElement) {
    let el = videoElement;
    for (let i = 0; i < 10; i++) {
        el = el.parentElement;
        if (!el) break;
        if (el.classList.contains("html5-video-player")) return "youtube";
        if (el.classList.contains("NFPlayer")) return "netflix";
        if (el.id === "vilos-player") return "crunchyroll";
        if (el.classList.contains("bitmovinplayer")) return "hulu";
        if (el.classList.contains("atvwebplayersdk-overlays-container"))
            return "primevideo";
    }
    return "unknown";
}

// ---------------------------------------------------------------------------
// Event Sending
// ---------------------------------------------------------------------------

function sendToService(eventData) {
    eventData.source = "show-tracker-content";
    try {
        chrome.runtime.sendMessage(eventData);
    } catch (_) {
        // Extension context invalidated — ignore
    }
}

// ---------------------------------------------------------------------------
// Playback Monitoring
// ---------------------------------------------------------------------------

let heartbeatInterval = null;
let lastMediaEvent = null;

function startPlaybackMonitoring() {
    // Observe DOM for dynamically created video elements
    const observer = new MutationObserver(() => {
        document.querySelectorAll("video").forEach(attachVideoListeners);
    });

    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    }

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
                timestamp: Date.now(),
            });
        }
    }, 30000);
}

function onPlaybackPause(video) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
    sendToService({
        type: "pause",
        metadata: lastMediaEvent?.metadata || extractMediaMetadata(),
        position: video.currentTime,
        duration: video.duration,
        timestamp: Date.now(),
    });
}

function onPlaybackEnd(video) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
    sendToService({
        type: "ended",
        metadata: lastMediaEvent?.metadata || extractMediaMetadata(),
        position: video.currentTime,
        duration: video.duration,
        timestamp: Date.now(),
    });
    lastMediaEvent = null;
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

// Start monitoring on load
startPlaybackMonitoring();

// Also send a page_load event if the page looks media-related
(function () {
    const metadata = extractMediaMetadata();
    const hasVideo = metadata.video && metadata.video.length > 0;
    const hasSchema = metadata.schema && metadata.schema.length > 0;
    const urlMatch = metadata.url_match !== null;

    if (hasVideo || hasSchema || urlMatch) {
        sendToService({
            type: "page_load",
            metadata,
            timestamp: Date.now(),
        });
    }
})();
