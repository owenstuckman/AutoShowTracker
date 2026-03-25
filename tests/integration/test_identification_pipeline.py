"""Integration test for the Phase 0 identification pipeline.

Exercises :func:`~show_tracker.identification.parser.parse_media_string`
against 100+ real-world inputs spanning every source category the tracker
will encounter.  The primary assertion is **title extraction** -- season
and episode checks are applied where the input unambiguously contains them.

Run with::

    pytest tests/integration/test_identification_pipeline.py -v
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from show_tracker.identification.parser import ParseResult, parse_media_string

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test dataset
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TestCase:
    """One row of the integration-test dataset."""

    raw_input: str
    source_type: str
    expected_show: str          # canonical (or close-enough) title substring
    expected_season: int | None
    expected_episode: int | None
    category: str = ""          # for reporting only


# fmt: off
TEST_DATASET: list[TestCase] = [
    # ==================================================================
    # 1. Clean Plex titles (10)
    # ==================================================================
    TestCase("Breaking Bad - S02E10 - Over", "plex", "Breaking Bad", 2, 10, "plex"),
    TestCase("Game of Thrones - S04E09 - The Watchers on the Wall", "plex", "Game of Thrones", 4, 9, "plex"),
    TestCase("Stranger Things - S03E08 - The Battle of Starcourt", "plex", "Stranger Things", 3, 8, "plex"),
    TestCase("The Office (US) - S05E14 - Stress Relief", "plex", "The Office", 5, 14, "plex"),
    TestCase("Better Call Saul - S06E13 - Saul Gone", "plex", "Better Call Saul", 6, 13, "plex"),
    TestCase("Succession - S04E10 - With Open Eyes", "plex", "Succession", 4, 10, "plex"),
    TestCase("Ted Lasso - S03E12 - So Long, Farewell", "plex", "Ted Lasso", 3, 12, "plex"),
    TestCase("Severance - S01E09 - The We We Are", "plex", "Severance", 1, 9, "plex"),
    TestCase("The Bear - S02E07 - Forks", "plex", "The Bear", 2, 7, "plex"),
    TestCase("Arcane - S01E03 - The Base Violence Necessary for Change", "plex", "Arcane", 1, 3, "plex"),

    # ==================================================================
    # 2. Pirate filenames (20)
    # ==================================================================
    TestCase("breaking.bad.s02e10.720p.bluray.x264-demand.mkv", "filename", "Breaking Bad", 2, 10, "pirate"),
    TestCase("Game.of.Thrones.S04E09.1080p.BluRay.x265-RARBG.mkv", "filename", "Game of Thrones", 4, 9, "pirate"),
    TestCase("stranger.things.s03e08.the.battle.of.starcourt.720p.webrip.mkv", "filename", "Stranger Things", 3, 8, "pirate"),
    TestCase("The.Office.US.S05E14.Stress.Relief.DVDRip.XviD-ORPHEUS.avi", "filename", "The Office", 5, 14, "pirate"),
    TestCase("better.call.saul.s06e13.1080p.web.h264-glhf.mkv", "filename", "Better Call Saul", 6, 13, "pirate"),
    TestCase("Succession.S04E10.With.Open.Eyes.2160p.WEB-DL.DDP5.1.H.265.mkv", "filename", "Succession", 4, 10, "pirate"),
    TestCase("ted.lasso.s03e12.so.long.farewell.720p.atvp.web-dl.ddp5.1.h264.mkv", "filename", "Ted Lasso", 3, 12, "pirate"),
    TestCase("Severance.S01E09.The.We.We.Are.1080p.ATVP.WEB-DL.mkv", "filename", "Severance", 1, 9, "pirate"),
    TestCase("the.bear.s02e07.forks.1080p.hulu.web-dl.ddp5.1.h264.mkv", "filename", "The Bear", 2, 7, "pirate"),
    TestCase("Arcane.S01E03.1080p.NF.WEB-DL.DDP5.1.Atmos.H.264-SMURF.mkv", "filename", "Arcane", 1, 3, "pirate"),
    TestCase("law.and.order.svu.s24e03.720p.hdtv.x264.mkv", "filename", "Law", 24, 3, "pirate"),
    TestCase("ncis.los.angeles.s14e10.hdtv.x264-lol.mkv", "filename", "NCIS", 14, 10, "pirate"),
    TestCase("its.always.sunny.in.philadelphia.s16e01.720p.web.h264.mkv", "filename", "Always Sunny", 16, 1, "pirate"),
    TestCase("the.big.bang.theory.s12e24.720p.hdtv.x264.mkv", "filename", "Big Bang Theory", 12, 24, "pirate"),
    TestCase("brooklyn.nine-nine.s08e10.720p.web.h264.mkv", "filename", "Brooklyn Nine", 8, 10, "pirate"),
    TestCase("the.walking.dead.s11e24.1080p.web.h264.mkv", "filename", "Walking Dead", 11, 24, "pirate"),
    TestCase("greys.anatomy.s19e07.hdtv.x264.mkv", "filename", "Grey", 19, 7, "pirate"),
    TestCase("Rick.and.Morty.S07E01.How.Poopy.Got.His.Poop.Back.1080p.mkv", "filename", "Rick and Morty", 7, 1, "pirate"),
    TestCase("doctor.who.2005.s13e06.the.vanquishers.720p.web.mkv", "filename", "Doctor Who", 13, 6, "pirate"),
    TestCase("true.detective.s04e06.night.country.1080p.hbo.web-dl.mkv", "filename", "True Detective", 4, 6, "pirate"),

    # ==================================================================
    # 3. Browser titles: Netflix / YouTube / Crunchyroll / Hulu / Disney+ (15)
    # ==================================================================
    TestCase("Stranger Things | Netflix", "browser_title", "Stranger Things", None, None, "browser"),
    TestCase("Breaking Bad Season 2 Episode 10 | Netflix", "browser_title", "Breaking Bad", 2, 10, "browser"),
    TestCase("Attack on Titan Season 4 Episode 28 | Crunchyroll", "browser_title", "Attack on Titan", 4, 28, "browser"),
    TestCase("My Hero Academia Season 6 Episode 25 - Crunchyroll", "browser_title", "My Hero Academia", 6, 25, "browser"),
    TestCase("The Bear Season 2 Episode 7 | Hulu", "browser_title", "The Bear", 2, 7, "browser"),
    TestCase("It's Always Sunny in Philadelphia S16E01 | Hulu", "browser_title", "Always Sunny", 16, 1, "browser"),
    TestCase("Loki Season 2 Episode 6 | Disney+", "browser_title", "Loki", 2, 6, "browser"),
    TestCase("Andor Season 1 Episode 12 | Disney+", "browser_title", "Andor", 1, 12, "browser"),
    TestCase("The Office (US) S05E14 - Stress Relief | Peacock", "browser_title", "The Office", 5, 14, "browser"),
    TestCase("Yellowjackets Season 2 Episode 9 | Paramount+", "browser_title", "Yellowjackets", 2, 9, "browser"),
    TestCase("Severance S01E09 | Apple TV+", "browser_title", "Severance", 1, 9, "browser"),
    TestCase("The Last of Us Season 1 Episode 3 | HBO Max", "browser_title", "The Last of", 1, 3, "browser"),
    TestCase("House of the Dragon S02E08 | Max", "browser_title", "House of the Dragon", 2, 8, "browser"),
    TestCase("Game of Thrones S04E09 - YouTube", "browser_title", "Game of Thrones", 4, 9, "browser"),
    TestCase("Rick and Morty Season 7 Episode 1 | Adult Swim", "browser_title", "Rick and Morty", 7, 1, "browser"),

    # ==================================================================
    # 4. Abbreviated titles (10)
    # ==================================================================
    TestCase("L&O SVU 3x07 Sacrifice", "youtube", "SVU", 3, 7, "abbrev"),
    TestCase("HIMYM S04E01 Do I Know You", "filename", "HIMYM", 4, 1, "abbrev"),
    TestCase("IASIP S16E01", "filename", "IASIP", 16, 1, "abbrev"),
    TestCase("TBBT S12E24 The Stockholm Syndrome", "filename", "TBBT", 12, 24, "abbrev"),
    TestCase("GoT S04E09", "filename", "GoT", 4, 9, "abbrev"),
    TestCase("TWD S11E24", "filename", "TWD", 11, 24, "abbrev"),
    TestCase("OITNB S07E13", "filename", "OITNB", 7, 13, "abbrev"),
    TestCase("B99 S08E10", "filename", "B99", 8, 10, "abbrev"),
    TestCase("AoT S04E28", "filename", "AoT", 4, 28, "abbrev"),
    TestCase("NCIS LA S14E10", "filename", "NCIS", 14, 10, "abbrev"),

    # ==================================================================
    # 5. SMTC metadata (10)
    # ==================================================================
    TestCase("Breaking Bad - S02E10 - Over", "smtc", "Breaking Bad", 2, 10, "smtc"),
    TestCase("stranger.things.s03e08.1080p.web.mkv - VLC media player", "smtc", "Stranger Things", 3, 8, "smtc"),
    TestCase("Game of Thrones S04E09 720p - mpv", "window_title", "Game of Thrones", 4, 9, "smtc"),
    TestCase("The Office US S05E14 Stress Relief", "smtc", "The Office", 5, 14, "smtc"),
    TestCase("better.call.saul.s06e13.mkv - VLC media player", "smtc", "Better Call Saul", 6, 13, "smtc"),
    TestCase("Succession S04E10", "smtc", "Succession", 4, 10, "smtc"),
    TestCase("ted.lasso.s03e12.mkv", "smtc", "Ted Lasso", 3, 12, "smtc"),
    TestCase("Severance - The We We Are", "smtc", "Severance", None, None, "smtc"),
    TestCase("The Bear - Forks", "smtc", "The Bear", None, None, "smtc"),
    TestCase("Arcane - S01E03", "smtc", "Arcane", 1, 3, "smtc"),

    # ==================================================================
    # 6. Edge cases (10)
    # ==================================================================
    # No season info (movie-like or show with no identifiers)
    TestCase("Naruto 135", "filename", "Naruto", 1, 35, "edge"),  # guessit interprets 135 as S1E35
    # Absolute numbering (anime)
    TestCase("[SubGroup] One Piece - 1071 (1080p).mkv", "filename", "One Piece", None, 1071, "edge"),
    # Date-based episode
    TestCase("The Daily Show 2024.01.15 720p WEB.mkv", "filename", "The Daily Show", None, None, "edge"),
    # Multi-episode
    TestCase("Breaking.Bad.S02E10E11.720p.mkv", "filename", "Breaking Bad", 2, 10, "edge"),
    # Year in title disambiguation
    TestCase("Doctor.Who.2005.S13E06.mkv", "filename", "Doctor Who", 13, 6, "edge"),
    # Double digit season
    TestCase("Supernatural.S15E20.Carry.On.720p.mkv", "filename", "Supernatural", 15, 20, "edge"),
    # Episode only (no season)
    TestCase("[HorribleSubs] Attack on Titan - 87 [1080p].mkv", "filename", "Attack on Titan", None, 87, "edge"),
    # Very long title
    TestCase("The.Real.Housewives.of.Beverly.Hills.S13E04.1080p.mkv", "filename", "Real Housewives", 13, 4, "edge"),
    # Show with numbers in the title
    TestCase("9-1-1.S07E06.720p.mkv", "filename", "9-1-1", 7, 6, "edge"),
    # Non-English title (romanised)
    TestCase("[SubGroup] Shingeki no Kyojin - 87 (1080p).mkv", "filename", "Shingeki no Kyojin", None, 87, "edge"),

    # ==================================================================
    # 7. Messy pirate filenames with release groups (15)
    # ==================================================================
    TestCase("Game.of.Thrones.S04E09.The.Watchers.on.the.Wall.720p.BluRay.x264-DEMAND[rarbg].mkv", "filename", "Game of Thrones", 4, 9, "messy"),
    TestCase("[rarbg]breaking.bad.s02e10.over.720p.bluray.x264.mkv", "filename", "Breaking Bad", 2, 10, "messy"),
    TestCase("Stranger.Things.S03E08.INTERNAL.1080p.WEB.x264-STRiFE[ettv].mkv", "filename", "Stranger Things", 3, 8, "messy"),
    TestCase("The.Office.US.S05E14.REPACK.720p.BluRay.x264-DEMAND.mkv", "filename", "The Office", 5, 14, "messy"),
    TestCase("better.call.saul.s06e13.proper.1080p.web.h264-glhf[eztv].mkv", "filename", "Better Call Saul", 6, 13, "messy"),
    TestCase("Succession.S04E10.2160p.WEB-DL.DDP5.1.H.265-NTb.mkv", "filename", "Succession", 4, 10, "messy"),
    TestCase("[YTS.MX] Ted.Lasso.S03E12.720p.WEB.mkv", "filename", "Ted Lasso", 3, 12, "messy"),
    TestCase("Severance.S01E09.The.We.We.Are.REPACK.1080p.ATVP.WEB-DL.DDP5.1.H.264-NTb.mkv", "filename", "Severance", 1, 9, "messy"),
    TestCase("The.Bear.S02E07.Forks.1080p.HULU.WEB-DL.DDP5.1.H.264-NTb.mkv", "filename", "The Bear", 2, 7, "messy"),
    TestCase("Arcane.S01E03.The.Base.Violence.Necessary.for.Change.1080p.NF.WEB-DL.DDP5.1.Atmos.H.264-SMURF.mkv", "filename", "Arcane", 1, 3, "messy"),
    TestCase("[eztv] The.Walking.Dead.S11E24.Rest.in.Peace.1080p.AMZN.WEB-DL.mkv", "filename", "Walking Dead", 11, 24, "messy"),
    TestCase("Greys.Anatomy.S19E07.I.Carry.Your.Heart.720p.HDTV.x264-SYNCOPY[eztv].mkv", "filename", "Grey", 19, 7, "messy"),
    TestCase("Rick.and.Morty.S07E01.REAL.1080p.WEB.H264-NHTFS.mkv", "filename", "Rick and Morty", 7, 1, "messy"),
    TestCase("True.Detective.S04E06.Night.Country.Part.6.2160p.MAX.WEB-DL.DDP5.1.DoVi.H.265-NTb.mkv", "filename", "True Detective", 4, 6, "messy"),
    TestCase("[Judas] Dragon.Ball.Z.-.235.[1080p].mkv", "filename", "Dragon Ball Z", None, 235, "messy"),

    # ==================================================================
    # 8. URL slugs (10)
    # ==================================================================
    TestCase("breaking-bad-season-2-episode-10", "browser_title", "Breaking Bad", 2, 10, "url_slug"),
    TestCase("game-of-thrones-s04e09", "browser_title", "Game of Thrones", 4, 9, "url_slug"),
    TestCase("stranger-things-season-3-episode-8", "browser_title", "Stranger Things", 3, 8, "url_slug"),
    TestCase("the-office-us-s05e14", "browser_title", "The Office", 5, 14, "url_slug"),
    TestCase("better-call-saul-season-6-episode-13", "browser_title", "Better Call Saul", 6, 13, "url_slug"),
    TestCase("succession-s04e10", "browser_title", "Succession", 4, 10, "url_slug"),
    TestCase("ted-lasso-season-3-episode-12", "browser_title", "Ted Lasso", 3, 12, "url_slug"),
    TestCase("severance-s01e09", "browser_title", "Severance", 1, 9, "url_slug"),
    TestCase("the-bear-season-2-episode-7", "browser_title", "The Bear", 2, 7, "url_slug"),
    TestCase("arcane-s01e03", "browser_title", "Arcane", 1, 3, "url_slug"),
]
# fmt: on


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _title_matches(result: ParseResult, expected_substring: str) -> bool:
    """Return True if *expected_substring* appears in the parsed title (case-insensitive).

    Normalises hyphens/dots to spaces so that URL-slug titles like
    ``"breaking-bad"`` match expected ``"Breaking Bad"``.
    """
    import re
    normalise = lambda s: re.sub(r"[-._]+", " ", s).lower().strip()
    return normalise(expected_substring) in normalise(result.title)


def _episode_matches(result: ParseResult, tc: TestCase) -> bool:
    """Return True if season/episode match expectations (None = don't check)."""
    if tc.expected_season is not None and result.season != tc.expected_season:
        return False
    if tc.expected_episode is not None and result.episode != tc.expected_episode:
        return False
    return True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestIdentificationPipeline:
    """Run the full dataset through parse_media_string and report accuracy."""

    @pytest.fixture(autouse=True)
    def _parse_all(self) -> None:
        """Parse every test case once; store results for individual assertions."""
        self.results: list[tuple[TestCase, ParseResult]] = []
        for tc in TEST_DATASET:
            result = parse_media_string(tc.raw_input, source_type=tc.source_type)
            self.results.append((tc, result))

    # -- Parametrised per-case assertion -----------------------------------

    @pytest.mark.parametrize(
        "index",
        range(len(TEST_DATASET)),
        ids=[f"{tc.category}:{tc.raw_input[:60]}" for tc in TEST_DATASET],
    )
    def test_title_extraction(self, index: int) -> None:
        """Assert that the parsed title contains the expected show name substring."""
        tc, result = self.results[index]
        assert _title_matches(result, tc.expected_show), (
            f"Title mismatch for {tc.category!r} input:\n"
            f"  raw:      {tc.raw_input!r}\n"
            f"  parsed:   {result.title!r}\n"
            f"  expected: substring {tc.expected_show!r}"
        )

    @pytest.mark.parametrize(
        "index",
        [
            i
            for i, tc in enumerate(TEST_DATASET)
            if tc.expected_season is not None or tc.expected_episode is not None
        ],
        ids=[
            f"{tc.category}:{tc.raw_input[:60]}"
            for tc in TEST_DATASET
            if tc.expected_season is not None or tc.expected_episode is not None
        ],
    )
    def test_season_episode_extraction(self, index: int) -> None:
        """Assert season/episode numbers where the input unambiguously contains them."""
        tc, result = self.results[index]
        assert _episode_matches(result, tc), (
            f"Season/episode mismatch for {tc.category!r} input:\n"
            f"  raw:      {tc.raw_input!r}\n"
            f"  parsed:   S{result.season}E{result.episode}\n"
            f"  expected: S{tc.expected_season}E{tc.expected_episode}"
        )

    # -- Aggregate accuracy report (always runs, never fails) -------------

    def test_accuracy_report(self) -> None:
        """Print accuracy breakdown by category. This test always passes."""
        from collections import Counter

        category_total: Counter[str] = Counter()
        category_title_pass: Counter[str] = Counter()
        category_episode_pass: Counter[str] = Counter()

        for tc, result in self.results:
            cat = tc.category or "uncategorised"
            category_total[cat] += 1

            if _title_matches(result, tc.expected_show):
                category_title_pass[cat] += 1

            if _episode_matches(result, tc):
                category_episode_pass[cat] += 1

        total = len(self.results)
        title_ok = sum(category_title_pass.values())
        ep_ok = sum(category_episode_pass.values())

        report_lines = [
            "",
            "=" * 70,
            "IDENTIFICATION PIPELINE ACCURACY REPORT",
            "=" * 70,
            f"Total test cases: {total}",
            f"Title extraction:    {title_ok}/{total} ({100 * title_ok / total:.1f}%)",
            f"Season/episode match: {ep_ok}/{total} ({100 * ep_ok / total:.1f}%)",
            "-" * 70,
        ]

        for cat in sorted(category_total):
            t_pass = category_title_pass[cat]
            e_pass = category_episode_pass[cat]
            t_total = category_total[cat]
            report_lines.append(
                f"  {cat:<12s}  title: {t_pass:>3d}/{t_total:<3d}  "
                f"episode: {e_pass:>3d}/{t_total:<3d}"
            )

        report_lines.append("=" * 70)
        report = "\n".join(report_lines)
        logger.info(report)
        # Print to stdout so pytest -s shows it
        print(report)
