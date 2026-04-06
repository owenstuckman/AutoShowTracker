"""Unit tests for the CLI entry point.

Uses Click's CliRunner to invoke commands without a real network/database.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from show_tracker.main import cli


class TestCLIHelp:
    """Basic CLI structural tests."""

    def test_cli_help_exits_zero(self) -> None:
        """show-tracker --help exits with code 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_cli_version(self) -> None:
        """show-tracker --version prints version info."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "show-tracker" in result.output.lower() or result.output.strip()

    def test_cli_lists_commands(self) -> None:
        """show-tracker --help mentions key subcommands."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "identify" in result.output
        assert "init-db" in result.output

    def test_identify_help_exits_zero(self) -> None:
        """show-tracker identify --help exits 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["identify", "--help"])
        assert result.exit_code == 0

    def test_init_db_help_exits_zero(self) -> None:
        """show-tracker init-db --help exits 0."""
        runner = CliRunner()
        result = runner.invoke(cli, ["init-db", "--help"])
        assert result.exit_code == 0


class TestIdentifyCommand:
    """Tests for the identify subcommand."""

    def test_identify_exits_nonzero_without_tmdb_key(self) -> None:
        """identify fails with a useful error when TMDB_API_KEY is not set."""
        runner = CliRunner()
        # Ensure no TMDB key in environment
        result = runner.invoke(
            cli,
            ["identify", "Breaking Bad S01E01"],
            env={"TMDB_API_KEY": ""},
            catch_exceptions=False,
        )
        # Should exit non-zero because no API key
        assert result.exit_code != 0
        assert "TMDB_API_KEY" in result.output or "TMDB_API_KEY" in (result.stderr or "")

    def test_identify_with_mock_result(self) -> None:
        """identify exits 0 and prints JSON when identification succeeds."""
        runner = CliRunner()

        mock_result = {
            "show_name": "Breaking Bad",
            "season": 1,
            "episode": 1,
            "episode_title": "Pilot",
            "confidence": 0.95,
        }

        async def mock_identify(raw_string: str, **kwargs):  # type: ignore[no-untyped-def]
            return mock_result

        with patch("show_tracker.main.load_settings") as mock_settings_loader:
            settings = MagicMock()
            settings.has_tmdb_key.return_value = True
            mock_settings_loader.return_value = settings

            with patch("show_tracker.identification.identify_media", new=mock_identify):
                result = runner.invoke(cli, ["identify", "Breaking.Bad.S01E01.mkv"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["show_name"] == "Breaking Bad"
        assert parsed["season"] == 1


class TestInitDbCommand:
    """Tests for the init-db subcommand."""

    def test_init_db_creates_databases(self) -> None:
        """init-db creates watch_history.db and media_cache.db in data-dir."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = runner.invoke(
                cli,
                ["--data-dir", tmp_dir, "init-db"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0, f"Command failed: {result.output}"
            assert "Databases initialised successfully" in result.output

            db_dir = Path(tmp_dir)
            watch_db = db_dir / "watch_history.db"
            cache_db = db_dir / "media_cache.db"
            assert watch_db.exists(), f"watch_history.db not found in {tmp_dir}"
            assert cache_db.exists(), f"media_cache.db not found in {tmp_dir}"

    def test_init_db_force_flag_accepted(self) -> None:
        """init-db --force runs without error."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = runner.invoke(
                cli,
                ["--data-dir", tmp_dir, "init-db", "--force"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0

    def test_init_db_idempotent(self) -> None:
        """init-db can be run twice without error (idempotent)."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmp_dir:
            # First run
            result1 = runner.invoke(cli, ["--data-dir", tmp_dir, "init-db"])
            assert result1.exit_code == 0

            # Second run
            result2 = runner.invoke(cli, ["--data-dir", tmp_dir, "init-db"])
            assert result2.exit_code == 0

    def test_init_db_prints_db_paths(self) -> None:
        """init-db output mentions the database file paths."""
        runner = CliRunner()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = runner.invoke(cli, ["--data-dir", tmp_dir, "init-db"])
            assert result.exit_code == 0
            # Should mention both databases
            assert "watch_history" in result.output
            assert "media_cache" in result.output
