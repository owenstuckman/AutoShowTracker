# Privacy Policy

**AutoShowTracker** — Last updated: 2026-03-16

## Summary

AutoShowTracker is a locally-run application. All data stays on your machine. No telemetry, no analytics, no cloud sync (unless you explicitly enable optional third-party integrations).

## Data Collection

### What AutoShowTracker collects

- **Window titles** from your desktop (via ActivityWatch)
- **Media session metadata** from your operating system (SMTC on Windows, MPRIS on Linux)
- **Browser tab URLs and page metadata** (via the browser extension, only when tracking is enabled)
- **Player metadata** from VLC and mpv (via local IPC, only when those players are running)
- **Screenshots of player windows** (only when OCR fallback is triggered, processed locally, never stored as images)

All of this data is processed locally and stored in SQLite databases on your machine.

### What AutoShowTracker does NOT collect

- No personal information (name, email, account credentials)
- No audio or video content
- No browsing history beyond the active tab's media-related metadata
- No data from non-media applications
- No usage analytics or telemetry

## Data Storage

All data is stored locally in your configured data directory (default: `~/.show-tracker/`):

| File | Contents | Sensitivity |
|------|----------|-------------|
| `watch_history.db` | Your watch log, show metadata, aliases, settings | **User data** — back up, do not share publicly |
| `media_cache.db` | Cached TMDb API responses | Rebuildable — safe to delete |
| `logs/` | Application log files | May contain window titles and URLs |

No data is transmitted to any server except:
- **TMDb API** (`api.themoviedb.org`): Show title search queries and episode lookups. TMDb receives the show names you search for. See [TMDb's privacy policy](https://www.themoviedb.org/privacy-policy).
- **ActivityWatch** (`localhost:5600`): Local communication only. ActivityWatch is a separate application with its own privacy policy.
- **YouTube Data API** (optional, `googleapis.com`): If configured, video ID lookups are sent to Google's API. See [Google's privacy policy](https://policies.google.com/privacy).

## Browser Extension

The Chrome extension:
- Only activates on pages with `<video>` elements
- Extracts page metadata (URL, title, Open Graph tags, JSON-LD structured data)
- Sends this metadata to your local AutoShowTracker instance (`localhost:7600`) only
- Can be toggled on/off via the extension popup
- Does not communicate with any external server
- Stores only a boolean "tracking enabled" preference in Chrome's local storage

### Extension Permissions

| Permission | Why |
|------------|-----|
| `activeTab` / `tabs` | Read the current tab's URL and title for media detection |
| `storage` | Persist the tracking on/off toggle |
| `<all_urls>` | Inject the content script on streaming sites to detect video playback |

## Data Retention

- Watch history is retained indefinitely until you delete it
- TMDb cache entries expire after 7 days and are automatically refreshed
- Failed lookup entries expire after 24 hours
- Log files are rotated automatically

To delete all data: remove the `~/.show-tracker/` directory, or run `show-tracker init-db --force` to reset databases.

## Third-Party Services

| Service | Data Sent | Purpose |
|---------|-----------|---------|
| TMDb API | Show/episode title queries | Identify shows and fetch metadata |
| YouTube Data API (optional) | Video IDs | Identify YouTube series content |
| ActivityWatch (local) | Nothing (we read from it) | Window title detection |

## Children's Privacy

AutoShowTracker does not knowingly collect data from children under 13. It is a local tool with no account system.

## Changes

This policy may be updated as features are added. Changes will be noted in the project's commit history.

## Contact

For privacy concerns, open an issue on the project's GitHub repository.
