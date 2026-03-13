# Licensing and Distribution

## License Landscape

### ActivityWatch: MPL 2.0 (Mozilla Public License 2.0)

MPL 2.0 is a file-level copyleft license. Its key properties for this project:

1. **File-level copyleft:** Any modifications to MPL-licensed source files must be distributed under MPL 2.0. If you change a line in an ActivityWatch `.rs` or `.py` file, that file stays MPL 2.0.
2. **Larger Works provision (Section 3.3):** MPL-licensed files can be combined with files under different licenses (including proprietary) in a "Larger Work." The non-MPL files do not become MPL-licensed.
3. **Binary distribution:** You can distribute MPL-licensed binaries (compiled executables) as long as you make the corresponding source code available. For unmodified ActivityWatch, pointing to their GitHub repository satisfies this.

### What This Means in Practice

Since we chose Option 1 (subprocess bundle) and do NOT modify any ActivityWatch source files:
- Our own code (media identification service, browser extension, UI, OCR pipeline, SMTC/MPRIS listeners) can be under any license we choose.
- ActivityWatch binaries are shipped as-is. We satisfy the MPL 2.0 source obligation by including a notice that points to the ActivityWatch GitHub repository and the specific release version we bundled.
- If we ever need to patch an ActivityWatch file (e.g., a bug fix), that patched file must remain MPL 2.0 and its source must be available. This is another reason to avoid modifying their code — communicate only via their API.

### Other Dependency Licenses

| Dependency | License | Obligation |
|------------|---------|------------|
| guessit | LGPL 3.0 | Can be used as a library (dynamic linking / import) without our code becoming LGPL. If we modify guessit's source, those modifications must be LGPL 3.0. Standard pip import usage is fine. |
| Tesseract | Apache 2.0 | Permissive. Include license notice and attribution. |
| EasyOCR | Apache 2.0 | Same as Tesseract. |
| winsdk (Python) | MIT | Permissive. Include license notice. |
| dbus-next | MIT | Permissive. Include license notice. |
| Flask | BSD-3 | Permissive. Include license notice. |
| FastAPI | MIT | Permissive. Include license notice. |
| SQLite | Public Domain | No obligations. |
| Chromium extension APIs | N/A | Subject to Chrome Web Store policies, not a code license. |

No dependency has a license that would force our code to be open source, provided we use them as libraries (import/link) rather than modifying their source files.

### TMDb API Terms

TMDb's free API requires:
- Attribution: "This product uses the TMDb API but is not endorsed or certified by TMDb." Include the TMDb logo in the application's about/credits screen.
- No caching of TMDb data for more than 6 months (in practice, our cache rotation handles this).
- No redistribution of bulk TMDb data.
- Rate limit: 50 requests per second (more than sufficient for single-user).

### YouTube Data API Terms

Google's API Terms of Service apply. Key points:
- Must comply with YouTube ToS (no circumvention of restrictions).
- Quota: 10,000 units/day on free tier. Each `videos.list` call costs 1 unit. Sufficient for individual use but monitor usage.
- Attribution: display YouTube branding when showing YouTube content data.

## Recommended License for Our Code

**Recommendation: MIT License** for the open-source release, or proprietary if the intent is commercial.

If open source: MIT is simple, permissive, and compatible with all dependencies. Users can fork, modify, and redistribute. Combined with MPL 2.0 for the ActivityWatch bundle, the full distribution is clean.

If proprietary: the Larger Works provision of MPL 2.0 explicitly allows this. Ship ActivityWatch binaries with source notice, keep our code proprietary.

## Distribution Package Contents

The installer ships the following directory structure:

```
show-tracker/
├── show-tracker.exe             # Our launcher (or show-tracker on Linux/macOS)
├── LICENSE.txt                  # Our license (MIT or proprietary)
├── THIRD_PARTY_LICENSES.txt     # All dependency licenses consolidated
├── activitywatch/               # Bundled AW binaries (unmodified)
│   ├── aw-server-rust(.exe)
│   ├── aw-watcher-window(.exe)
│   ├── LICENSE-activitywatch.txt  # MPL 2.0 text
│   └── SOURCE_NOTICE.txt       # "Source code available at https://github.com/ActivityWatch/activitywatch, release vX.Y.Z"
├── lib/                         # Python runtime + our code + pip dependencies
│   ├── media_service/           # Our media identification service
│   ├── smtc_listener/           # SMTC/MPRIS daemon
│   ├── ocr_pipeline/            # OCR subsystem
│   └── ...
├── extension/                   # Browser extension files
│   ├── chrome/                  # Unpacked Chrome extension
│   └── firefox/                 # Firefox XPI
├── profiles/                    # OCR app region profiles
│   └── default_profiles.json
└── web/                         # Frontend static files
    └── ...
```

### THIRD_PARTY_LICENSES.txt

This file must consolidate all license texts. Format:

```
==============================================================================
ActivityWatch
License: Mozilla Public License 2.0
Source: https://github.com/ActivityWatch/activitywatch
Version: vX.Y.Z (bundled binaries, unmodified)
==============================================================================
[Full MPL 2.0 text]

==============================================================================
guessit
License: LGPL 3.0
Source: https://github.com/guessit-io/guessit
==============================================================================
[Full LGPL 3.0 text]

==============================================================================
Tesseract OCR
License: Apache 2.0
Source: https://github.com/tesseract-ocr/tesseract
==============================================================================
[Full Apache 2.0 text]

... (repeat for each dependency)
```

## Source Code Availability Obligations

| Component | Must Source Be Available? | How to Satisfy |
|-----------|--------------------------|----------------|
| ActivityWatch binaries | Yes (MPL 2.0) | SOURCE_NOTICE.txt pointing to their GitHub + release tag |
| Our code (if MIT) | Yes (if distributed) | Include source or link to repository |
| Our code (if proprietary) | No | Not required by any dependency license |
| guessit (if unmodified) | Technically yes (LGPL) | It's on PyPI; include link in THIRD_PARTY_LICENSES |
| guessit (if modified) | Yes, modifications must be LGPL | Publish modified version |

## Installer Considerations

### Windows
- Use Inno Setup or NSIS.
- Register the application in Add/Remove Programs.
- Optional: add to Windows startup (user choice during install).
- Install browser extension: provide instructions to sideload the Chrome extension (or link to Chrome Web Store if published).

### Linux
- AppImage: single-file, no installation needed. Recommended for broadest compatibility.
- Flatpak: sandboxed, handles desktop integration. May complicate D-Bus access for MPRIS.
- Deb/RPM: traditional but requires maintaining per-distro packages.
- Recommendation: start with AppImage, add Flatpak later.

### macOS
- DMG with drag-to-Applications. Standard distribution.
- Consider notarization for Gatekeeper (Apple Developer Program, $99/year). Without it, users must bypass Gatekeeper on first launch.
- The Swift helper binary for MediaRemote should be code-signed with the same certificate.

## Privacy Policy Requirements

Both the Chrome Web Store and Firefox Add-ons require a privacy policy for extensions requesting `<all_urls>`. Additionally, since the application tracks user viewing habits, a privacy policy is advisable for the application itself.

Key points the policy must cover:
- All data is stored locally on the user's device. No data is transmitted to any server.
- The application reads browser tab URLs and titles to identify media content.
- The application reads window titles and OS media session metadata.
- If OCR is enabled, screenshots of media player windows are captured temporarily for text extraction and are not stored.
- TMDb and YouTube API calls transmit show names and video IDs to those services' servers (necessary for identification). No personal user data is included in these calls.
- The user can export or delete all stored data at any time.
