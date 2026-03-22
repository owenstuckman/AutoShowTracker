/**
 * AutoShowTracker — Frontend Application
 *
 * Vanilla JS single-page application with hash-based routing.
 * No build step, no external dependencies.
 */

// ===========================================================================
// API Client
// ===========================================================================

const API = {
    base: "",

    async _fetch(path, options = {}) {
        try {
            const resp = await fetch(`${this.base}${path}`, {
                headers: { "Content-Type": "application/json" },
                ...options,
            });
            if (!resp.ok) {
                const text = await resp.text();
                throw new Error(`HTTP ${resp.status}: ${text}`);
            }
            return await resp.json();
        } catch (err) {
            console.error(`API error: ${path}`, err);
            throw err;
        }
    },

    // Health
    health() {
        return this._fetch("/api/health");
    },

    // Media
    currentlyWatching() {
        return this._fetch("/api/currently-watching");
    },

    // History
    recentHistory(limit = 50) {
        return this._fetch(`/api/history/recent?limit=${limit}`);
    },
    shows() {
        return this._fetch("/api/history/shows");
    },
    showDetail(showId) {
        return this._fetch(`/api/history/shows/${showId}`);
    },
    showProgress(showId) {
        return this._fetch(`/api/history/shows/${showId}/progress`);
    },
    nextToWatch() {
        return this._fetch("/api/history/next-to-watch");
    },
    stats() {
        return this._fetch("/api/history/stats");
    },

    // Unresolved
    unresolved() {
        return this._fetch("/api/unresolved");
    },
    resolveEvent(id, body) {
        return this._fetch(`/api/unresolved/${id}/resolve`, {
            method: "POST",
            body: JSON.stringify(body),
        });
    },
    dismissEvent(id) {
        return this._fetch(`/api/unresolved/${id}/dismiss`, {
            method: "POST",
        });
    },
    searchTmdb(id, query) {
        return this._fetch(`/api/unresolved/${id}/search`, {
            method: "POST",
            body: JSON.stringify({ query }),
        });
    },

    // Settings
    settings() {
        return this._fetch("/api/settings");
    },
    updateSetting(key, value) {
        return this._fetch(`/api/settings/${key}`, {
            method: "PUT",
            body: JSON.stringify({ value }),
        });
    },

    // Stats (advanced analytics)
    dailyStats(days = 30) {
        return this._fetch(`/api/stats/daily?days=${days}`);
    },
    weeklyStats(weeks = 12) {
        return this._fetch(`/api/stats/weekly?weeks=${weeks}`);
    },
    monthlyStats(months = 12) {
        return this._fetch(`/api/stats/monthly?months=${months}`);
    },
    bingeSessions(minEpisodes = 3) {
        return this._fetch(`/api/stats/binge-sessions?min_episodes=${minEpisodes}`);
    },
    viewingPatterns() {
        return this._fetch("/api/stats/patterns");
    },

    // YouTube
    youtubeRecent(limit = 50) {
        return this._fetch(`/api/youtube/recent?limit=${limit}`);
    },
    youtubeStats() {
        return this._fetch("/api/youtube/stats");
    },

    // Aliases
    addAlias(showId, alias) {
        return this._fetch("/api/aliases", {
            method: "POST",
            body: JSON.stringify({ show_id: showId, alias }),
        });
    },
    getAliases(showId) {
        return this._fetch(`/api/aliases/${showId}`);
    },
    deleteAlias(aliasId) {
        return this._fetch(`/api/aliases/${aliasId}`, { method: "DELETE" });
    },
};

// ===========================================================================
// Utility Helpers
// ===========================================================================

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return "0m";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
}

function formatTimeAgo(isoString) {
    if (!isoString) return "";
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
}

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function epCode(season, episode) {
    const s = String(season).padStart(2, "0");
    const e = String(episode).padStart(2, "0");
    return `S${s}E${e}`;
}

function posterUrl(path) {
    if (!path) return null;
    if (path.startsWith("http")) return path;
    return `https://image.tmdb.org/t/p/w300${path}`;
}

// ===========================================================================
// Router
// ===========================================================================

const Router = {
    routes: {},

    register(pattern, handler) {
        this.routes[pattern] = handler;
    },

    navigate(hash) {
        window.location.hash = hash;
    },

    async resolve() {
        const hash = window.location.hash.slice(1) || "dashboard";
        const parts = hash.split("/");
        const route = parts[0];
        const params = parts.slice(1);

        // Update active nav link
        document.querySelectorAll(".nav-link").forEach((link) => {
            const linkRoute = link.getAttribute("data-route");
            link.classList.toggle(
                "active",
                linkRoute === route ||
                    (route === "show" && linkRoute === "shows")
            );
        });

        const handler = this.routes[route];
        if (handler) {
            try {
                await handler(...params);
            } catch (err) {
                console.error("Route error:", err);
                content().innerHTML = `
                    <div class="empty-state">
                        <div class="empty-state-icon">!</div>
                        <p class="empty-state-text">Error loading page: ${escapeHtml(err.message)}</p>
                    </div>
                `;
            }
        } else {
            Router.navigate("dashboard");
        }
    },
};

function content() {
    return document.getElementById("content");
}

// ===========================================================================
// Views
// ===========================================================================

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

async function renderDashboard() {
    content().innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Dashboard</h1>
            <p class="page-subtitle">Your watching activity at a glance</p>
        </div>
        <div class="now-watching hidden" id="nowWatching"></div>
        <div class="stat-cards" id="statCards">
            <div class="stat-card"><div class="stat-value">--</div><div class="stat-label">Total Watch Time</div></div>
            <div class="stat-card"><div class="stat-value">--</div><div class="stat-label">Episodes</div></div>
            <div class="stat-card"><div class="stat-value">--</div><div class="stat-label">Shows</div></div>
        </div>
        <div class="dashboard-grid">
            <div class="card">
                <div class="card-header"><span class="card-title">Recently Watched</span></div>
                <div id="recentList"><div class="loading-state"><div class="spinner"></div></div></div>
            </div>
            <div class="card">
                <div class="card-header"><span class="card-title">Next Up</span></div>
                <div id="nextUpList"><div class="loading-state"><div class="spinner"></div></div></div>
            </div>
        </div>
    `;

    // Load data in parallel
    const [statsData, recentData, nextData] = await Promise.all([
        API.stats().catch(() => null),
        API.recentHistory(10).catch(() => []),
        API.nextToWatch().catch(() => []),
    ]);

    // Stats
    if (statsData) {
        document.getElementById("statCards").innerHTML = `
            <div class="stat-card">
                <div class="stat-value">${formatDuration(statsData.total_watch_time_seconds)}</div>
                <div class="stat-label">Total Watch Time</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${statsData.total_episodes_watched}</div>
                <div class="stat-label">Episodes Watched</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${statsData.total_shows}</div>
                <div class="stat-label">Shows Tracked</div>
            </div>
        `;
    }

    // Recent
    const recentEl = document.getElementById("recentList");
    if (recentData.length === 0) {
        recentEl.innerHTML = `
            <div class="empty-state">
                <p class="empty-state-text">No watch history yet. Start watching something!</p>
            </div>
        `;
    } else {
        recentEl.innerHTML = `<ul class="recent-list">${recentData
            .map(
                (r) => `
            <li class="recent-item">
                <div class="recent-episode">
                    <div class="recent-show">${escapeHtml(r.show_title)}</div>
                    <div class="recent-ep">${epCode(r.season_number, r.episode_number)}${r.episode_title ? " - " + escapeHtml(r.episode_title) : ""}</div>
                </div>
                <span class="recent-badge ${r.completed ? "completed" : "partial"}">${r.completed ? "Watched" : "Partial"}</span>
                <span class="recent-time">${formatTimeAgo(r.started_at)}</span>
            </li>
        `
            )
            .join("")}</ul>`;
    }

    // Next up
    const nextEl = document.getElementById("nextUpList");
    if (nextData.length === 0) {
        nextEl.innerHTML = `
            <div class="empty-state">
                <p class="empty-state-text">No upcoming episodes.</p>
            </div>
        `;
    } else {
        nextEl.innerHTML = `<div class="next-up-list">${nextData
            .map(
                (n) => `
            <div class="next-up-item" onclick="Router.navigate('show/${n.show_id}')">
                <div>
                    <div class="next-up-show">${escapeHtml(n.show_title)}</div>
                    <div class="next-up-ep">${epCode(n.next_season, n.next_episode)}${n.episode_title ? " - " + escapeHtml(n.episode_title) : ""}</div>
                </div>
            </div>
        `
            )
            .join("")}</div>`;
    }

    // Currently watching
    updateNowWatching();
}

// ---------------------------------------------------------------------------
// Shows List
// ---------------------------------------------------------------------------

async function renderShows() {
    content().innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Shows</h1>
            <p class="page-subtitle">All tracked TV shows</p>
        </div>
        <div class="shows-grid" id="showsGrid">
            <div class="loading-state"><div class="spinner"></div></div>
        </div>
    `;

    const shows = await API.shows().catch(() => []);
    const grid = document.getElementById("showsGrid");

    if (shows.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#9733;</div>
                <p class="empty-state-text">No shows tracked yet.</p>
            </div>
        `;
        return;
    }

    grid.innerHTML = shows
        .map((s) => {
            const pct =
                s.total_episodes > 0
                    ? Math.round((s.episodes_watched / s.total_episodes) * 100)
                    : 0;
            const poster = posterUrl(s.poster_path);
            return `
            <div class="show-card" onclick="Router.navigate('show/${s.show_id}')">
                <div class="show-card-poster">
                    ${poster ? `<img src="${poster}" alt="" loading="lazy">` : "&#9733;"}
                </div>
                <div class="show-card-body">
                    <div class="show-card-title">${escapeHtml(s.title)}</div>
                    <div class="show-card-meta">
                        ${s.status || "Unknown"} ${s.total_seasons ? " \u00b7 " + s.total_seasons + " seasons" : ""}
                    </div>
                    <div class="progress-bar-container">
                        <div class="progress-bar-fill" style="width: ${pct}%"></div>
                    </div>
                    <div class="progress-text">${s.episodes_watched} / ${s.total_episodes} episodes (${pct}%)</div>
                </div>
            </div>
        `;
        })
        .join("");
}

// ---------------------------------------------------------------------------
// Show Detail
// ---------------------------------------------------------------------------

async function renderShowDetail(showId) {
    content().innerHTML = `
        <a href="#shows" class="back-link">&larr; Back to Shows</a>
        <div class="loading-state"><div class="spinner"></div></div>
    `;

    const detail = await API.showDetail(showId).catch(() => null);
    if (!detail) {
        content().innerHTML = `
            <a href="#shows" class="back-link">&larr; Back to Shows</a>
            <div class="empty-state">
                <p class="empty-state-text">Show not found.</p>
            </div>
        `;
        return;
    }

    const poster = posterUrl(detail.poster_path);
    const seasons = detail.seasons || [];
    const activeSeason = seasons.length > 0 ? seasons[0].season_number : 1;

    content().innerHTML = `
        <a href="#shows" class="back-link">&larr; Back to Shows</a>
        <div class="show-detail-header">
            <div class="show-detail-poster">
                ${poster ? `<img src="${poster}" alt="">` : "&#9733;"}
            </div>
            <div class="show-detail-info">
                <h1 class="show-detail-title">${escapeHtml(detail.title)}</h1>
                <div class="show-detail-meta">
                    ${detail.status ? `<span>${escapeHtml(detail.status)}</span>` : ""}
                    ${detail.first_air_date ? `<span>${detail.first_air_date}</span>` : ""}
                    ${detail.total_seasons ? `<span>${detail.total_seasons} seasons</span>` : ""}
                    ${detail.tmdb_id ? `<span>TMDb #${detail.tmdb_id}</span>` : ""}
                </div>
            </div>
        </div>
        <div class="season-tabs" id="seasonTabs">
            ${seasons
                .map(
                    (s) =>
                        `<button class="season-tab ${s.season_number === activeSeason ? "active" : ""}"
                            data-season="${s.season_number}">Season ${s.season_number}</button>`
                )
                .join("")}
        </div>
        <div class="episode-grid" id="episodeGrid"></div>
    `;

    // Render episodes for active season
    function renderSeason(seasonNum) {
        const season = seasons.find((s) => s.season_number === seasonNum);
        const grid = document.getElementById("episodeGrid");
        if (!season || !season.episodes.length) {
            grid.innerHTML = `<div class="empty-state"><p class="empty-state-text">No episodes in this season.</p></div>`;
            return;
        }
        grid.innerHTML = season.episodes
            .map(
                (ep) => `
            <div class="episode-item ${ep.watched ? "watched" : "unwatched"}">
                <div class="episode-check">${ep.watched ? "\u2713" : ""}</div>
                <span class="episode-number">E${String(ep.episode_number).padStart(2, "0")}</span>
                <div class="episode-info">
                    <div class="episode-title">${escapeHtml(ep.title) || "Untitled"}</div>
                    <div class="episode-date">${ep.air_date || ""}${ep.watch_count > 0 ? " \u00b7 watched " + ep.watch_count + "x" : ""}</div>
                </div>
            </div>
        `
            )
            .join("");
    }

    renderSeason(activeSeason);

    // Tab click handlers
    document.getElementById("seasonTabs").addEventListener("click", (e) => {
        const tab = e.target.closest(".season-tab");
        if (!tab) return;
        document
            .querySelectorAll(".season-tab")
            .forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        renderSeason(parseInt(tab.dataset.season, 10));
    });
}

// ---------------------------------------------------------------------------
// Unresolved
// ---------------------------------------------------------------------------

async function renderUnresolved() {
    content().innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Unresolved Events</h1>
            <p class="page-subtitle">Media detections that need your help to identify</p>
        </div>
        <div class="unresolved-list" id="unresolvedList">
            <div class="loading-state"><div class="spinner"></div></div>
        </div>
    `;

    const events = await API.unresolved().catch(() => []);
    const list = document.getElementById("unresolvedList");

    if (events.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#9888;</div>
                <p class="empty-state-text">No unresolved events. Everything is identified!</p>
            </div>
        `;
        return;
    }

    list.innerHTML = events
        .map(
            (ev) => `
        <div class="unresolved-item" id="unresolved-${ev.id}">
            <div class="unresolved-raw">${escapeHtml(ev.raw_input)}</div>
            <div class="unresolved-meta">
                Source: ${escapeHtml(ev.source)}
                ${ev.source_detail ? " \u00b7 " + escapeHtml(ev.source_detail) : ""}
                \u00b7 ${formatTimeAgo(ev.detected_at)}
                ${ev.confidence != null ? " \u00b7 Confidence: " + (ev.confidence * 100).toFixed(0) + "%" : ""}
            </div>
            ${
                ev.best_guess_show
                    ? `<div class="unresolved-guess">Best guess: ${escapeHtml(ev.best_guess_show)} ${ev.best_guess_season != null ? epCode(ev.best_guess_season, ev.best_guess_episode || 0) : ""}</div>`
                    : ""
            }
            <div class="unresolved-actions">
                <button class="btn btn-primary btn-sm" onclick="searchUnresolved(${ev.id}, '${escapeHtml(ev.best_guess_show || ev.raw_input).replace(/'/g, "\\'")}')">Search TMDb</button>
                <button class="btn btn-danger btn-sm" onclick="dismissUnresolved(${ev.id})">Dismiss</button>
            </div>
            <div class="search-results" id="search-${ev.id}"></div>
        </div>
    `
        )
        .join("");
}

async function searchUnresolved(eventId, defaultQuery) {
    const query = prompt("Search TMDb for:", defaultQuery);
    if (!query) return;

    const container = document.getElementById(`search-${eventId}`);
    container.innerHTML = `<div class="loading-state"><div class="spinner"></div><p>Searching...</p></div>`;

    try {
        const results = await API.searchTmdb(eventId, query);
        if (results.length === 0) {
            container.innerHTML = `<p style="color: var(--text-muted); font-size: 12px; padding: 8px 0;">No results found.</p>`;
            return;
        }

        container.innerHTML = results
            .map(
                (r) => `
            <div class="search-result-item" onclick="resolveToShow(${eventId}, ${r.tmdb_id}, '${escapeHtml(r.title).replace(/'/g, "\\'")}')">
                <div class="search-result-info">
                    <div class="search-result-title">${escapeHtml(r.title)}</div>
                    <div class="search-result-year">${r.first_air_date || "Unknown"}</div>
                </div>
                <button class="btn btn-success btn-sm">Select</button>
            </div>
        `
            )
            .join("");
    } catch (err) {
        container.innerHTML = `<p style="color: var(--danger); font-size: 12px;">Search failed: ${escapeHtml(err.message)}</p>`;
    }
}

async function resolveToShow(eventId, tmdbId, title) {
    const season = prompt(`Season number for "${title}":`, "1");
    if (!season) return;
    const episode = prompt("Episode number:", "1");
    if (!episode) return;

    try {
        // We need the show_id in our DB, which may differ from tmdb_id.
        // For now, use tmdb_id as show_id (the API will handle lookup).
        await API.resolveEvent(eventId, {
            show_id: tmdbId,
            season_number: parseInt(season, 10),
            episode_number: parseInt(episode, 10),
        });

        // Remove the item from the list
        const el = document.getElementById(`unresolved-${eventId}`);
        if (el) el.remove();

        // Check if list is now empty
        const remaining = document.querySelectorAll(".unresolved-item");
        if (remaining.length === 0) {
            document.getElementById("unresolvedList").innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#9888;</div>
                    <p class="empty-state-text">No unresolved events. Everything is identified!</p>
                </div>
            `;
        }
    } catch (err) {
        alert("Failed to resolve: " + err.message);
    }
}

async function dismissUnresolved(eventId) {
    if (!confirm("Dismiss this event? It will not be tracked.")) return;

    try {
        await API.dismissEvent(eventId);
        const el = document.getElementById(`unresolved-${eventId}`);
        if (el) el.remove();

        const remaining = document.querySelectorAll(".unresolved-item");
        if (remaining.length === 0) {
            document.getElementById("unresolvedList").innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#9888;</div>
                    <p class="empty-state-text">No unresolved events. Everything is identified!</p>
                </div>
            `;
        }
    } catch (err) {
        alert("Failed to dismiss: " + err.message);
    }
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

const SETTING_DEFINITIONS = [
    {
        key: "auto_log_threshold",
        label: "Auto-Log Confidence Threshold",
        hint: "Detections above this confidence are automatically logged (0.0 - 1.0)",
        default: "0.9",
    },
    {
        key: "review_threshold",
        label: "Review Queue Threshold",
        hint: "Detections below this confidence go to the unresolved queue (0.0 - 1.0)",
        default: "0.7",
    },
    {
        key: "ocr_enabled",
        label: "OCR Fallback Enabled",
        hint: "Enable OCR when window title and SMTC/MPRIS fail (true/false)",
        default: "true",
    },
    {
        key: "activitywatch_port",
        label: "ActivityWatch Port",
        hint: "Port where aw-server-rust listens",
        default: "5600",
    },
    {
        key: "heartbeat_interval",
        label: "Heartbeat Interval (seconds)",
        hint: "How often to send heartbeats during playback",
        default: "30",
    },
];

async function renderSettings() {
    content().innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Settings</h1>
            <p class="page-subtitle">Configure AutoShowTracker behavior</p>
        </div>
        <div class="settings-form" id="settingsForm">
            <div class="loading-state"><div class="spinner"></div></div>
        </div>
    `;

    const settings = await API.settings().catch(() => []);
    const settingsMap = {};
    settings.forEach((s) => (settingsMap[s.key] = s.value));

    const form = document.getElementById("settingsForm");
    form.innerHTML = SETTING_DEFINITIONS.map(
        (def) => `
        <div class="form-group">
            <label class="form-label" for="setting-${def.key}">${def.label}</label>
            <input class="form-input" id="setting-${def.key}"
                type="text"
                value="${escapeHtml(settingsMap[def.key] || def.default)}"
                data-key="${def.key}">
            <span class="form-hint">${def.hint}</span>
        </div>
    `
    ).join("");

    form.innerHTML += `
        <div style="margin-top: 8px;">
            <button class="btn btn-primary" id="saveSettingsBtn">Save Settings</button>
            <span id="settingsSaveStatus" style="margin-left: 12px; font-size: 12px; color: var(--success);"></span>
        </div>
    `;

    document.getElementById("saveSettingsBtn").addEventListener("click", async () => {
        const statusEl = document.getElementById("settingsSaveStatus");
        statusEl.textContent = "Saving...";
        statusEl.style.color = "var(--text-muted)";

        try {
            const inputs = form.querySelectorAll(".form-input[data-key]");
            for (const input of inputs) {
                await API.updateSetting(input.dataset.key, input.value);
            }
            statusEl.textContent = "Saved!";
            statusEl.style.color = "var(--success)";
        } catch (err) {
            statusEl.textContent = "Error: " + err.message;
            statusEl.style.color = "var(--danger)";
        }

        setTimeout(() => {
            statusEl.textContent = "";
        }, 3000);
    });
}

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------

async function renderStats() {
    content().innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Statistics</h1>
            <p class="page-subtitle">Your watching patterns and trends</p>
        </div>
        <div class="stats-charts">
            <div class="card">
                <div class="card-header"><span class="card-title">Daily Watch Time (Last 30 Days)</span></div>
                <div class="chart-container"><canvas id="dailyChart"></canvas></div>
            </div>
            <div class="card">
                <div class="card-header"><span class="card-title">Weekly Watch Time</span></div>
                <div class="chart-container"><canvas id="weeklyChart"></canvas></div>
            </div>
            <div class="card">
                <div class="card-header"><span class="card-title">Viewing Patterns</span></div>
                <div class="chart-container"><canvas id="patternsChart"></canvas></div>
            </div>
            <div class="card">
                <div class="card-header"><span class="card-title">Binge Sessions</span></div>
                <div id="bingeList"><div class="loading-state"><div class="spinner"></div></div></div>
            </div>
        </div>
    `;

    const [daily, weekly, patterns, binges] = await Promise.all([
        API.dailyStats(30).catch(() => []),
        API.weeklyStats(12).catch(() => []),
        API.viewingPatterns().catch(() => null),
        API.bingeSessions().catch(() => []),
    ]);

    // Daily chart
    if (typeof Chart !== "undefined" && daily.length > 0) {
        const reversed = [...daily].reverse();
        new Chart(document.getElementById("dailyChart"), {
            type: "bar",
            data: {
                labels: reversed.map((d) => d.date),
                datasets: [{
                    label: "Hours",
                    data: reversed.map((d) => +(d.total_seconds / 3600).toFixed(1)),
                    backgroundColor: "rgba(99, 102, 241, 0.7)",
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { maxTicksLimit: 10, color: "#999" }, grid: { display: false } },
                    y: { beginAtZero: true, ticks: { color: "#999" }, grid: { color: "rgba(255,255,255,0.05)" } },
                },
            },
        });
    }

    // Weekly chart
    if (typeof Chart !== "undefined" && weekly.length > 0) {
        const reversed = [...weekly].reverse();
        new Chart(document.getElementById("weeklyChart"), {
            type: "bar",
            data: {
                labels: reversed.map((w) => w.week),
                datasets: [{
                    label: "Hours",
                    data: reversed.map((w) => +(w.total_seconds / 3600).toFixed(1)),
                    backgroundColor: "rgba(74, 222, 128, 0.7)",
                    borderRadius: 4,
                }],
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: "#999" }, grid: { display: false } },
                    y: { beginAtZero: true, ticks: { color: "#999" }, grid: { color: "rgba(255,255,255,0.05)" } },
                },
            },
        });
    }

    // Patterns heatmap (hour of day)
    if (typeof Chart !== "undefined" && patterns) {
        const hours = patterns.hour_distribution || [];
        new Chart(document.getElementById("patternsChart"), {
            type: "bar",
            data: {
                labels: Array.from({ length: 24 }, (_, i) => `${i}:00`),
                datasets: [{
                    label: "Episodes",
                    data: hours,
                    backgroundColor: hours.map((v) => {
                        const intensity = Math.min(v / (Math.max(...hours) || 1), 1);
                        return `rgba(99, 102, 241, ${0.2 + intensity * 0.8})`;
                    }),
                    borderRadius: 2,
                }],
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false },
                    title: {
                        display: true,
                        text: `Most active: ${patterns.most_active_hour}:00 on ${patterns.most_active_day}s | Avg session: ${patterns.avg_session_minutes}m`,
                        color: "#999",
                        font: { size: 12 },
                    },
                },
                scales: {
                    x: { ticks: { maxTicksLimit: 12, color: "#999" }, grid: { display: false } },
                    y: { beginAtZero: true, ticks: { color: "#999" }, grid: { color: "rgba(255,255,255,0.05)" } },
                },
            },
        });
    }

    // Binge list
    const bingeEl = document.getElementById("bingeList");
    if (binges.length === 0) {
        bingeEl.innerHTML = `<div class="empty-state"><p class="empty-state-text">No binge sessions detected yet.</p></div>`;
    } else {
        bingeEl.innerHTML = `<ul class="recent-list">${binges.map((b) => `
            <li class="recent-item">
                <div class="recent-episode">
                    <div class="recent-show">${escapeHtml(b.show_title)}</div>
                    <div class="recent-ep">${b.episode_count} episodes (${b.first_episode} - ${b.last_episode})</div>
                </div>
                <span class="recent-badge completed">${formatDuration(b.total_seconds)}</span>
                <span class="recent-time">${b.date}</span>
            </li>
        `).join("")}</ul>`;
    }
}

// ---------------------------------------------------------------------------
// YouTube
// ---------------------------------------------------------------------------

async function renderYouTube() {
    content().innerHTML = `
        <div class="page-header">
            <h1 class="page-title">YouTube</h1>
            <p class="page-subtitle">Tracked YouTube video watches</p>
        </div>
        <div class="stat-cards" id="ytStatCards">
            <div class="stat-card"><div class="stat-value">--</div><div class="stat-label">Total Watches</div></div>
            <div class="stat-card"><div class="stat-value">--</div><div class="stat-label">Unique Videos</div></div>
            <div class="stat-card"><div class="stat-value">--</div><div class="stat-label">Watch Time</div></div>
        </div>
        <div class="card">
            <div class="card-header"><span class="card-title">Recent YouTube Videos</span></div>
            <div id="ytList"><div class="loading-state"><div class="spinner"></div></div></div>
        </div>
    `;

    const [stats, recent] = await Promise.all([
        API.youtubeStats().catch(() => null),
        API.youtubeRecent(50).catch(() => []),
    ]);

    // Stats
    if (stats) {
        document.getElementById("ytStatCards").innerHTML = `
            <div class="stat-card">
                <div class="stat-value">${stats.total_watches}</div>
                <div class="stat-label">Total Watches</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.unique_videos}</div>
                <div class="stat-label">Unique Videos</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${formatDuration(stats.total_watch_seconds)}</div>
                <div class="stat-label">Watch Time</div>
            </div>
        `;
    }

    // Recent list
    const listEl = document.getElementById("ytList");
    if (recent.length === 0) {
        listEl.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#9655;</div>
                <p class="empty-state-text">No YouTube watches tracked yet. YouTube videos will appear here when detected via the browser extension.</p>
            </div>
        `;
        return;
    }

    listEl.innerHTML = `<ul class="recent-list">${recent.map((v) => `
        <li class="recent-item">
            <div class="recent-episode">
                <div class="recent-show">${escapeHtml(v.title)}</div>
                <div class="recent-ep">${v.channel_name ? escapeHtml(v.channel_name) : v.video_id}${v.duration_seconds ? " \u00b7 " + formatDuration(v.duration_seconds) : ""}</div>
            </div>
            <a class="recent-badge completed" href="https://youtube.com/watch?v=${encodeURIComponent(v.video_id)}" target="_blank" rel="noopener" style="text-decoration:none">Watch</a>
            <span class="recent-time">${formatTimeAgo(v.started_at)}</span>
        </li>
    `).join("")}</ul>`;
}

// ---------------------------------------------------------------------------
// Movies
// ---------------------------------------------------------------------------

async function renderMovies() {
    content().innerHTML = `
        <div class="page-header">
            <h1 class="page-title">Movies</h1>
            <p class="page-subtitle">Tracked movie watches</p>
        </div>
        <div class="shows-grid" id="moviesGrid">
            <div class="loading-state"><div class="spinner"></div></div>
        </div>
    `;

    // There's no dedicated movies endpoint yet that returns aggregated data,
    // so we use a simple fetch. The backend can be extended later.
    let movies = [];
    try {
        const resp = await fetch("/api/export/history.json");
        if (resp.ok) {
            const all = await resp.json();
            // Filter for movie watches if the data includes media_type
            movies = all.filter((e) => e.media_type === "movie" || (e.show_title && !e.season_number && !e.episode_number));
        }
    } catch (_) {}

    const grid = document.getElementById("moviesGrid");

    if (movies.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">&#127909;</div>
                <p class="empty-state-text">No movies tracked yet. Movies will appear here when detected.</p>
            </div>
        `;
        return;
    }

    // Deduplicate by title
    const seen = new Set();
    const unique = [];
    for (const m of movies) {
        const key = (m.show_title || m.title || "").toLowerCase();
        if (!seen.has(key)) {
            seen.add(key);
            unique.push(m);
        }
    }

    grid.innerHTML = unique.map((m) => `
        <div class="show-card">
            <div class="show-card-poster">&#127909;</div>
            <div class="show-card-body">
                <div class="show-card-title">${escapeHtml(m.show_title || m.title || "Unknown")}</div>
                <div class="show-card-meta">
                    ${m.started_at ? formatTimeAgo(m.started_at) : ""}
                    ${m.duration_seconds ? " \u00b7 " + formatDuration(m.duration_seconds) : ""}
                </div>
                <div class="progress-text">${m.completed ? "Watched" : "Partial"} \u00b7 ${escapeHtml(m.source || "")}</div>
            </div>
        </div>
    `).join("");
}

// ---------------------------------------------------------------------------
// Currently Watching (auto-refresh)
// ---------------------------------------------------------------------------

let nowWatchingTimer = null;

async function updateNowWatching() {
    try {
        const data = await API.currentlyWatching();
        const el = document.getElementById("nowWatching");
        if (!el) return;

        if (data.is_watching && data.title) {
            el.classList.remove("hidden");
            let progressText = "";
            if (data.position != null && data.duration) {
                const pct = Math.round((data.position / data.duration) * 100);
                progressText = ` \u00b7 ${formatDuration(Math.round(data.position))} / ${formatDuration(Math.round(data.duration))} (${pct}%)`;
            }
            el.innerHTML = `
                <div class="now-pulse"></div>
                <div class="now-watching-info">
                    <div class="now-watching-label">Now Watching</div>
                    <div class="now-watching-title">${escapeHtml(data.title)}</div>
                    <div class="now-watching-meta">${escapeHtml(data.tab_url || "")}${progressText}</div>
                </div>
            `;
        } else {
            el.classList.add("hidden");
        }
    } catch (_) {
        // Service unavailable
    }
}

function startNowWatchingRefresh() {
    stopNowWatchingRefresh();
    nowWatchingTimer = setInterval(updateNowWatching, 10000);
}

function stopNowWatchingRefresh() {
    if (nowWatchingTimer) {
        clearInterval(nowWatchingTimer);
        nowWatchingTimer = null;
    }
}

// ---------------------------------------------------------------------------
// Connection Status
// ---------------------------------------------------------------------------

async function checkConnection() {
    const badge = document.getElementById("connectionBadge");
    if (!badge) return;

    try {
        await API.health();
        badge.innerHTML = `<span class="conn-dot connected"></span><span class="conn-text">Connected</span>`;
    } catch (_) {
        badge.innerHTML = `<span class="conn-dot disconnected"></span><span class="conn-text">Disconnected</span>`;
    }
}

// ===========================================================================
// Register Routes & Start
// ===========================================================================

Router.register("dashboard", renderDashboard);
Router.register("shows", renderShows);
Router.register("show", renderShowDetail);
Router.register("youtube", renderYouTube);
Router.register("movies", renderMovies);
Router.register("stats", renderStats);
Router.register("unresolved", renderUnresolved);
Router.register("settings", renderSettings);

// Listen for hash changes
window.addEventListener("hashchange", () => {
    stopNowWatchingRefresh();
    Router.resolve();
    if ((window.location.hash || "#dashboard") === "#dashboard") {
        startNowWatchingRefresh();
    }
});

// Initial load
document.addEventListener("DOMContentLoaded", () => {
    Router.resolve();
    checkConnection();
    setInterval(checkConnection, 30000);

    if (!window.location.hash || window.location.hash === "#dashboard") {
        startNowWatchingRefresh();
    }
});
