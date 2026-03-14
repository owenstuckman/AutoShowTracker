# Data Model and Storage

## Database Choice: SQLite

SQLite is used for all persistent storage. Rationale:
- Local-first, zero configuration, no separate server process.
- Sufficient for single-user workload (no concurrent write contention).
- Portable — the database is a single file that can be backed up or moved.
- Python has built-in `sqlite3` support.

Two separate databases (or schemas within one file, but separate files are simpler for backup):
1. **watch_history.db** — the user's watch log and preferences.
2. **media_cache.db** — cached TMDb/TVDb data (can be deleted and rebuilt without data loss).

## Schema: watch_history.db

### shows

Canonical show entries. One row per unique TV series.

```sql
CREATE TABLE shows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tmdb_id INTEGER UNIQUE,             -- TMDb show ID (nullable if YouTube-only content)
    tvdb_id INTEGER,                     -- TVDb show ID (nullable)
    title TEXT NOT NULL,                 -- Canonical show title
    original_title TEXT,                 -- Original language title
    poster_path TEXT,                    -- TMDb poster URL path
    first_air_date TEXT,                 -- ISO date
    status TEXT,                         -- "Returning Series", "Ended", etc.
    total_seasons INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_shows_tmdb ON shows(tmdb_id);
CREATE INDEX idx_shows_title ON shows(title);
```

### episodes

Canonical episode entries. One row per unique episode.

```sql
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id INTEGER NOT NULL REFERENCES shows(id),
    tmdb_episode_id INTEGER UNIQUE,     -- TMDb episode ID
    season_number INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,
    title TEXT,                          -- Episode title ("Sacrifice")
    air_date TEXT,                       -- ISO date
    runtime_minutes INTEGER,            -- Expected runtime
    created_at TEXT DEFAULT (datetime('now')),

    UNIQUE(show_id, season_number, episode_number)
);

CREATE INDEX idx_episodes_show ON episodes(show_id);
CREATE INDEX idx_episodes_lookup ON episodes(show_id, season_number, episode_number);
```

### watch_events

The core table. Each row represents a single viewing session of a single episode.

```sql
CREATE TABLE watch_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL REFERENCES episodes(id),
    started_at TEXT NOT NULL,            -- ISO datetime, when playback was first detected
    ended_at TEXT,                       -- ISO datetime, when playback stopped
    duration_seconds INTEGER,           -- Total seconds watched (may differ from ended-started if paused)
    completed BOOLEAN DEFAULT 0,        -- Did the user watch >= 90% of the episode?
    source TEXT NOT NULL,               -- Detection source: "smtc", "mpris", "browser", "ocr", "manual"
    source_detail TEXT,                 -- Additional context: app name, URL, filename
    confidence REAL,                    -- Identification confidence score (0.0 - 1.0)
    raw_input TEXT,                     -- The raw string that was parsed (for debugging/review)
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_watch_events_episode ON watch_events(episode_id);
CREATE INDEX idx_watch_events_time ON watch_events(started_at);
CREATE INDEX idx_watch_events_confidence ON watch_events(confidence);
```

### youtube_watches

Separate table for YouTube content that doesn't map to a TV episode.

```sql
CREATE TABLE youtube_watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,             -- YouTube video ID
    title TEXT NOT NULL,
    channel_name TEXT,
    channel_id TEXT,
    duration_seconds INTEGER,
    watched_seconds INTEGER,
    playlist_id TEXT,                   -- If part of a series/playlist
    playlist_index INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_youtube_video ON youtube_watches(video_id);
CREATE INDEX idx_youtube_playlist ON youtube_watches(playlist_id);
```

### show_aliases

User-defined and system-provided aliases for show names. Used during the identification step to resolve abbreviated or alternate titles.

```sql
CREATE TABLE show_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id INTEGER NOT NULL REFERENCES shows(id),
    alias TEXT NOT NULL,                -- e.g., "L&O SVU", "SVU", "Law and Order SVU"
    source TEXT DEFAULT 'system',       -- "system" (shipped with app) or "user" (user-added)

    UNIQUE(alias)
);

CREATE INDEX idx_aliases_lookup ON show_aliases(alias);
```

### unresolved_events

Events that could not be confidently identified. Queued for user review.

```sql
CREATE TABLE unresolved_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_input TEXT NOT NULL,            -- The raw string from detection
    source TEXT NOT NULL,               -- Detection source
    source_detail TEXT,
    detected_at TEXT NOT NULL,
    best_guess_show TEXT,               -- Parser's best guess at show name
    best_guess_season INTEGER,
    best_guess_episode INTEGER,
    confidence REAL,
    resolved BOOLEAN DEFAULT 0,         -- User has manually resolved or dismissed
    resolved_episode_id INTEGER REFERENCES episodes(id),  -- If user confirmed a match
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_unresolved_pending ON unresolved_events(resolved) WHERE resolved = 0;
```

### user_settings

Key-value store for user preferences and configuration.

```sql
CREATE TABLE user_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

Settings include:
- `auto_log_threshold`: confidence threshold for auto-logging (default: 0.9)
- `review_threshold`: confidence threshold below which events go to unresolved queue (default: 0.7)
- `ocr_enabled`: whether OCR fallback is active (default: true)
- `player_ipc_vlc_enabled`: VLC integration toggle
- `player_ipc_mpv_enabled`: mpv integration toggle
- `activitywatch_port`: port for AW server (default: 5600)

## Schema: media_cache.db

### tmdb_show_cache

```sql
CREATE TABLE tmdb_show_cache (
    tmdb_id INTEGER PRIMARY KEY,
    data TEXT NOT NULL,                 -- Full JSON response from TMDb
    fetched_at TEXT DEFAULT (datetime('now'))
);
```

### tmdb_search_cache

Cache search queries to avoid repeated API calls for the same show name.

```sql
CREATE TABLE tmdb_search_cache (
    query TEXT PRIMARY KEY,             -- Normalized search query (lowercase, trimmed)
    result_tmdb_ids TEXT NOT NULL,      -- JSON array of matching TMDb show IDs
    fetched_at TEXT DEFAULT (datetime('now'))
);
```

### tmdb_episode_cache

```sql
CREATE TABLE tmdb_episode_cache (
    tmdb_episode_id INTEGER PRIMARY KEY,
    show_tmdb_id INTEGER NOT NULL,
    season_number INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,
    data TEXT NOT NULL,                 -- Full JSON response
    fetched_at TEXT DEFAULT (datetime('now'))
);
```

### failed_lookups

Prevent hammering the API for content that doesn't exist in TMDb.

```sql
CREATE TABLE failed_lookups (
    query TEXT PRIMARY KEY,
    reason TEXT,                        -- "no_results", "low_confidence", "api_error"
    attempts INTEGER DEFAULT 1,
    first_failed_at TEXT DEFAULT (datetime('now')),
    last_failed_at TEXT DEFAULT (datetime('now'))
);
```

## Data Flow: Detection to Storage

```
Raw signal (window title, URL, SMTC metadata, OCR text)
    │
    ▼
Parsing layer extracts: {show_name, season, episode}
    │
    ▼
Check show_aliases for known mappings
    │
    ▼
Check tmdb_search_cache for prior lookups
    │
    ├── Cache hit ──▶ Use cached TMDb ID
    │
    ├── Cache miss ──▶ Query TMDb API ──▶ Cache result
    │
    └── Failed lookup cache hit ──▶ Skip (don't re-query within 24h)
    │
    ▼
Resolve to canonical episode (check tmdb_episode_cache or fetch)
    │
    ▼
Upsert into shows table (if new show)
Upsert into episodes table (if new episode)
    │
    ▼
Calculate confidence score
    │
    ├── confidence >= auto_log_threshold ──▶ Insert into watch_events
    │
    ├── confidence >= review_threshold ──▶ Insert into watch_events (flagged)
    │
    └── confidence < review_threshold ──▶ Insert into unresolved_events
```

## Duration Tracking (Heartbeat Pattern)

Rather than a single "started watching" / "stopped watching" event pair, the system uses heartbeats for accurate duration tracking.

While a media source is active (playing), the detection loop sends a heartbeat every 30 seconds. The storage layer handles this:

```python
def process_heartbeat(episode_id: int, source: str, confidence: float, raw_input: str):
    """Called every ~30 seconds while an episode is detected as playing."""

    # Find the most recent watch event for this episode within the last 5 minutes
    recent = db.execute("""
        SELECT id, started_at, duration_seconds
        FROM watch_events
        WHERE episode_id = ? AND ended_at IS NULL
          AND started_at > datetime('now', '-5 minutes')
        ORDER BY started_at DESC LIMIT 1
    """, (episode_id,)).fetchone()

    if recent:
        # Extend the existing event
        new_duration = recent["duration_seconds"] + 30
        db.execute("""
            UPDATE watch_events
            SET duration_seconds = ?, ended_at = datetime('now')
            WHERE id = ?
        """, (new_duration, recent["id"]))
    else:
        # Start a new watch event
        db.execute("""
            INSERT INTO watch_events
                (episode_id, started_at, duration_seconds, source, source_detail, confidence, raw_input)
            VALUES (?, datetime('now'), 0, ?, ?, ?, ?)
        """, (episode_id, source, None, confidence, raw_input))

def finalize_watch_event(episode_id: int):
    """Called when playback stops or episode changes."""
    event = db.execute("""
        SELECT id, duration_seconds FROM watch_events
        WHERE episode_id = ? AND ended_at IS NULL
        ORDER BY started_at DESC LIMIT 1
    """, (episode_id,)).fetchone()

    if event:
        episode = db.execute("SELECT runtime_minutes FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        expected_duration = (episode["runtime_minutes"] or 45) * 60
        completed = event["duration_seconds"] >= (expected_duration * 0.9)

        db.execute("""
            UPDATE watch_events
            SET ended_at = datetime('now'), completed = ?
            WHERE id = ?
        """, (completed, event["id"]))
```

## Query Patterns for the Frontend

### Get watch progress for a show

```sql
SELECT
    e.season_number,
    e.episode_number,
    e.title AS episode_title,
    MAX(w.completed) AS watched,
    MAX(w.duration_seconds) AS longest_watch,
    MAX(w.started_at) AS last_watched
FROM episodes e
LEFT JOIN watch_events w ON w.episode_id = e.id
WHERE e.show_id = ?
GROUP BY e.id
ORDER BY e.season_number, e.episode_number;
```

### Get recently watched episodes

```sql
SELECT
    s.title AS show_title,
    e.season_number,
    e.episode_number,
    e.title AS episode_title,
    w.started_at,
    w.duration_seconds,
    w.completed,
    w.source
FROM watch_events w
JOIN episodes e ON e.id = w.episode_id
JOIN shows s ON s.id = e.show_id
ORDER BY w.started_at DESC
LIMIT 50;
```

### Get "next to watch" per show

```sql
SELECT
    s.id AS show_id,
    s.title AS show_title,
    MIN(e.season_number) AS next_season,
    MIN(e.episode_number) AS next_episode
FROM shows s
JOIN episodes e ON e.show_id = s.id
LEFT JOIN watch_events w ON w.episode_id = e.id AND w.completed = 1
WHERE w.id IS NULL
  AND s.id IN (SELECT DISTINCT show_id FROM episodes JOIN watch_events ON watch_events.episode_id = episodes.id)
GROUP BY s.id;
```
