# Content Identification and Parsing

## Overview

Raw detection signals (window titles, URLs, OCR text, SMTC metadata) must be normalized to canonical episode entries. This document covers the parsing layer (extracting structured data from raw strings) and the identification layer (resolving parsed data to canonical database entries).

## Parsing Layer

### Input Formats

The parsing layer receives strings in wildly different formats depending on the source:

```
# From pirate site filenames / VLC window titles:
"law.and.order.svu.s03e07.720p.bluray.x264-demand.mkv"
"Law.&.Order.SVU.S03E07.Sacrifice.720p.WEB-DL.mkv"
"[SubGroup] Law and Order SVU - 03x07 (720p).mkv"

# From browser tab titles:
"Law & Order SVU Season 3 Episode 7 - Watch Free HD"
"Watch Law and Order: Special Victims Unit S3E7 Online"
"Law & Order: Special Victims Unit | Netflix"

# From SMTC/MPRIS metadata:
"Law & Order: SVU - Sacrifice"
"law.and.order.svu.s03e07.720p.bluray.mkv"

# From YouTube:
"Law & Order SVU Season 3 Episode 7 Full Episode"
"L&O SVU 3x07 Sacrifice"

# From Plex (clean metadata):
"Law & Order: Special Victims Unit - S03E07 - Sacrifice"
```

### guessit Integration

`guessit` is a Python library designed for parsing media filenames from torrent/release naming conventions. It handles the majority of parsing work.

```python
from guessit import guessit

result = guessit("law.and.order.svu.s03e07.720p.bluray.x264-demand.mkv")
# Returns:
# {
#     "title": "law and order svu",
#     "season": 3,
#     "episode": 7,
#     "screen_size": "720p",
#     "source": "Blu-ray",
#     "video_codec": "H.264",
#     "release_group": "demand",
#     "container": "mkv",
#     "type": "episode"
# }
```

`guessit` handles these common patterns:
- `S01E03`, `s01e03` (SxxExx)
- `1x03` (seasonXepisode)
- `Season 1 Episode 3`
- `Episode 3` (no season — requires additional context)
- Multi-episode: `S01E03E04`, `S01E03-E05`
- Date-based episodes: `2024.01.15` (common for daily shows)
- Absolute episode numbering: `Episode 145` (common for anime)

### Custom Parsing for Non-Filename Sources

`guessit` is optimized for filenames. Browser tab titles and SMTC metadata may need preprocessing:

```python
import re

def preprocess_for_guessit(raw_string: str, source_type: str) -> str:
    """Clean raw string before passing to guessit."""

    # Remove common browser title suffixes
    suffixes_to_strip = [
        r"\s*\|\s*Netflix$",
        r"\s*-\s*YouTube$",
        r"\s*-\s*Watch Free.*$",
        r"\s*-\s*Watch Online.*$",
        r"\s*\|\s*Hulu$",
        r"\s*\|\s*Disney\+$",
        r"\s*\|\s*Amazon Prime Video$",
        r"\s*-\s*Crunchyroll$",
    ]
    cleaned = raw_string
    for pattern in suffixes_to_strip:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Remove common streaming site noise words
    noise = ["watch", "free", "hd", "online", "streaming", "full episode"]
    if source_type == "browser_title":
        for word in noise:
            cleaned = re.sub(rf"\b{word}\b", "", cleaned, flags=re.IGNORECASE)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned
```

### URL Pattern Matching

For browser sources, URL patterns are often more reliable than page titles. Build a pattern engine for known sites:

```python
URL_PATTERNS = {
    # Netflix: /watch/<content_id>
    r"netflix\.com/watch/(\d+)": {
        "platform": "netflix",
        "id_type": "netflix_content_id",
        "extract": lambda m: {"platform_id": m.group(1)}
    },
    # YouTube: /watch?v=<video_id>
    r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)": {
        "platform": "youtube",
        "id_type": "youtube_video_id",
        "extract": lambda m: {"platform_id": m.group(1)}
    },
    # Crunchyroll: /watch/<slug>/episode-<num>
    r"crunchyroll\.com/.*/watch/.*?/(.+)": {
        "platform": "crunchyroll",
        "id_type": "crunchyroll_slug",
        "extract": lambda m: {"slug": m.group(1)}
    },
    # Plex: /web/index.html#!/server/<id>/details?key=<key>
    r"plex\.tv/web/.*key=%2Flibrary%2Fmetadata%2F(\d+)": {
        "platform": "plex",
        "id_type": "plex_metadata_key",
        "extract": lambda m: {"platform_id": m.group(1)}
    },
    # Generic pirate site patterns — extract from URL slug
    # e.g., /watch/law-and-order-svu-s03e07 or /show/law-and-order-svu/season-3/episode-7
    r"/(?:watch|stream|play|view)/([a-z0-9-]+s\d{1,2}e\d{1,2})": {
        "platform": "generic",
        "id_type": "url_slug_with_episode",
        "extract": lambda m: {"slug": m.group(1)}
    },
    r"/(?:show|series|tv)/([a-z0-9-]+)/season-?(\d+)/episode-?(\d+)": {
        "platform": "generic",
        "id_type": "url_structured",
        "extract": lambda m: {
            "slug": m.group(1),
            "season": int(m.group(2)),
            "episode": int(m.group(3))
        }
    },
}
```

### YouTube-Specific Handling

YouTube content is unique because it's not always episodic TV. The parser must categorize:

1. **YouTube as a platform for TV content:** Users upload full episodes. Title usually contains show name + episode info. Parse with guessit.
2. **YouTube original series:** Use the YouTube Data API to get playlist info and episode ordering.
3. **Regular YouTube videos:** Log as standalone video watches (title + channel), not as TV episodes.

```python
# Use YouTube Data API to get video details
# GET https://www.googleapis.com/youtube/v3/videos?id=<VIDEO_ID>&part=snippet
# Response includes: title, channelTitle, description, tags
# Check if it belongs to a playlist (series) or is standalone
```

**Decision logic:** If guessit detects `type: "episode"` from the title, treat it as TV content and resolve against TMDb. If not, log it as a YouTube video (store video ID, title, channel, duration).

## Identification Layer

### TMDb Integration

TMDb (The Movie Database) is the primary canonical database. Free API with 50 requests per second.

**Workflow:**

1. **Search:** `GET /search/tv?query=<show_name>` — returns list of matching shows.
2. **Select best match:** Use fuzzy string matching (Levenshtein ratio) between the parsed show name and each result's `name` and `original_name`. Accept matches above 0.8 similarity threshold.
3. **Get episode:** `GET /tv/<show_id>/season/<season>/episode/<episode>` — returns canonical episode data including `id`, `name`, `overview`, `air_date`, `runtime`.
4. **Cache:** Cache show search results and episode data locally. Show names don't change; episode data is static once aired.

```python
# Pseudocode for TMDb resolution
import requests
from difflib import SequenceMatcher

TMDB_API_KEY = "..."
TMDB_BASE = "https://api.themoviedb.org/3"

def resolve_episode(parsed: dict) -> dict | None:
    """Resolve parsed show/season/episode to a canonical TMDb entry."""

    # Step 1: Check local cache first
    cached = cache.get_show(parsed["title"])
    if cached:
        return fetch_episode(cached["tmdb_id"], parsed["season"], parsed["episode"])

    # Step 2: Search TMDb
    results = requests.get(f"{TMDB_BASE}/search/tv", params={
        "api_key": TMDB_API_KEY,
        "query": parsed["title"]
    }).json()["results"]

    if not results:
        return None

    # Step 3: Fuzzy match
    best_match = None
    best_score = 0.0
    for show in results:
        for name_field in [show["name"], show.get("original_name", "")]:
            score = SequenceMatcher(None, parsed["title"].lower(), name_field.lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = show

    if best_score < 0.8:
        return None  # No confident match

    # Step 4: Fetch episode
    cache.store_show(parsed["title"], best_match["id"])
    return fetch_episode(best_match["id"], parsed["season"], parsed["episode"])
```

### TVDb as Fallback

Some shows (especially anime with absolute episode numbering) have better data on TVDb. Use TVDb when:
- TMDb search returns no results.
- The parsed episode uses absolute numbering (e.g., "Episode 145" with no season) and TMDb can't resolve it.

TVDb requires a paid API subscription for new integrations as of 2024 — evaluate whether the cost is justified based on how many edge cases TMDb misses.

### Handling Ambiguous Parses

Common ambiguity cases and resolution strategies:

**No season number:** `"Law and Order SVU Episode 7"` — could be any season.
- Strategy: If the user has prior watch history for this show, assume the next unwatched season. If no history, query TMDb for the most recent season and try episode 7.

**Abbreviated or alternate titles:** `"L&O SVU"`, `"NCIS: LA"`, `"AoT"` (Attack on Titan).
- Strategy: Maintain an alias table mapping common abbreviations to canonical show names. Populate initially with the most common abbreviations, then let users add custom aliases.

**Multiple shows with similar names:** `"The Office"` (US vs UK).
- Strategy: Rank by popularity on TMDb (the `popularity` field). If ambiguous, check if the season/episode combination exists for each candidate — the US Office has 9 seasons, the UK version has 2.

**Year-ambiguous reboots:** `"Battlestar Galactica"` (1978 vs 2004).
- Strategy: If a year is present in the raw string, use it. Otherwise, prefer the more popular/recent version. Allow user override in settings.

### Caching Strategy

TMDb API calls should be aggressively cached to minimize API usage and improve response time.

| Data | Cache Duration | Rationale |
|------|---------------|-----------|
| Show search results | 30 days | Show metadata rarely changes |
| Episode details | Indefinite (for aired episodes) | Aired episodes don't change |
| Season episode lists | 7 days | New episodes may be added to current seasons |
| Show alias mappings | Indefinite | User-defined or manually curated |
| Failed lookups | 24 hours | Prevent hammering API for non-existent content |

Use SQLite for the cache — same database as watch history, separate tables.

### Confidence Scoring

Each identification should carry a confidence score so the UI can flag uncertain matches for user review.

```python
@dataclass
class IdentificationResult:
    canonical_id: str          # TMDb episode ID
    show_name: str             # Canonical show name
    season: int
    episode: int
    episode_title: str | None
    confidence: float          # 0.0 to 1.0
    source: str                # "smtc", "activitywatch", "browser", "ocr"
    raw_input: str             # Original string that was parsed
    match_method: str          # "exact_url", "guessit+tmdb_fuzzy", "ocr+tmdb_fuzzy"

# Confidence thresholds:
# >= 0.9: Auto-log, no user confirmation needed
# 0.7 - 0.9: Auto-log but flag for review in UI
# < 0.7: Do not auto-log; queue for manual confirmation
```

Factors that increase confidence: URL pattern match on a known platform (very high), exact season+episode numbers present in the raw string, high TMDb fuzzy match score, SMTC metadata from a well-behaved player like Plex.

Factors that decrease confidence: OCR source (noisy), no season number, abbreviated title, multiple TMDb candidates with similar scores.
