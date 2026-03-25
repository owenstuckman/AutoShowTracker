# Documentation Index

## For Users

| Document | Description |
|----------|-------------|
| [Setup Guide](SETUP.md) | Installation, configuration, VLC/mpv setup, browser extension |
| [Human TODO](HUMAN_TODO.md) | Manual tasks: detection source testing, tuning, packaging |
| [Distribution](DISTRIBUTION.md) | How to build, package, and publish releases |
| [API Reference](API_REFERENCE.md) | Full HTTP API documentation with request/response examples |

## For Developers

| Document | Description |
|----------|-------------|
| [Architecture](ARCHITECTURE.md) | System architecture, data flow, detection priority, confidence scoring |
| [ActivityWatch](ACTIVITYWATCH.md) | ActivityWatch integration: subprocess management, polling, event flow |
| [Decisions](DECISIONS.md) | Numbered implementation decision log (D001–D013) |
| [Features](FEATURES.md) | Completed features — everything implemented and working |
| [TODO](TODO.md) | What's left — CI fixes, missing functionality, test coverage |

## Design Specifications

Original design documents in [`design/`](design/). These capture the initial design intent — the actual implementation may have evolved.

| # | Document | Covers |
|---|----------|--------|
| 00 | [Entry Point](design/00_CLAUDE_CODE_ENTRY_POINT.md) | Project summary, document index, where to start |
| 01 | [Project Overview](design/01_PROJECT_OVERVIEW.md) | Vision, design decisions with rationale |
| 02 | [Architecture](design/02_ARCHITECTURE.md) | Five-layer architecture, process model, data flow |
| 03 | [Media Detection](design/03_MEDIA_DETECTION.md) | Six-level detection priority chain |
| 04 | [Content Identification](design/04_CONTENT_IDENTIFICATION.md) | guessit, TMDb/TVDb resolution, fuzzy matching, confidence |
| 05 | [ActivityWatch Integration](design/05_ACTIVITYWATCH_INTEGRATION.md) | Subprocess management, REST API, polling |
| 06 | [Browser Extension](design/06_BROWSER_EXTENSION.md) | Content script, metadata extraction, heartbeats |
| 07 | [Data Model](design/07_DATA_MODEL.md) | Full SQLite schema, data flow, query patterns |
| 08 | [Implementation Roadmap](design/08_IMPLEMENTATION_ROADMAP.md) | Phased milestones (all complete) |
| 09 | [Licensing & Distribution](design/09_LICENSING_AND_DISTRIBUTION.md) | MPL 2.0 obligations, dependency licenses, packaging |

## Other Project Files

| File | Description |
|------|-------------|
| [README.md](../README.md) | Project overview and quick start |
| [PRIVACY_POLICY.md](../PRIVACY_POLICY.md) | Data collection and privacy details |
| [THIRD_PARTY_LICENSES.txt](../THIRD_PARTY_LICENSES.txt) | Dependency license listing |
| [CLAUDE.md](../CLAUDE.md) | Instructions for Claude Code AI assistant |
