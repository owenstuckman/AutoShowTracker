"""Unit tests for the configuration module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from show_tracker.config import Settings, load_settings


class TestConfigDefaults:
    """Verify default configuration values."""

    def test_load_settings_no_error(self) -> None:
        """load_settings() returns a Settings instance without raising."""
        settings = load_settings()
        assert settings is not None
        assert isinstance(settings, Settings)

    def test_default_activitywatch_port(self) -> None:
        """Default ActivityWatch port is 5600."""
        settings = load_settings()
        assert settings.activitywatch_port == 5600

    def test_default_media_service_port(self) -> None:
        """Default media service port is 7600."""
        settings = load_settings()
        assert settings.media_service_port == 7600

    def test_default_auto_log_threshold(self) -> None:
        """Default auto-log confidence threshold is 0.9."""
        settings = load_settings()
        assert settings.auto_log_threshold == pytest.approx(0.9)

    def test_default_review_threshold(self) -> None:
        """Default review confidence threshold is 0.7."""
        settings = load_settings()
        assert settings.review_threshold == pytest.approx(0.7)

    def test_default_ocr_enabled(self) -> None:
        """OCR is enabled by default."""
        settings = load_settings()
        assert settings.ocr_enabled is True

    def test_default_tmdb_api_key_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TMDB API key is empty when env var is explicitly set to empty."""
        monkeypatch.setenv("TMDB_API_KEY", "")
        settings = load_settings()
        assert settings.tmdb_api_key == ""

    def test_default_heartbeat_interval(self) -> None:
        """Default heartbeat interval is 30 seconds."""
        settings = load_settings()
        assert settings.heartbeat_interval == 30

    def test_default_grace_period(self) -> None:
        """Default grace period is 120 seconds."""
        settings = load_settings()
        assert settings.grace_period == 120

    def test_default_polling_interval(self) -> None:
        """Default polling interval is 10 seconds."""
        settings = load_settings()
        assert settings.polling_interval == 10

    def test_data_dir_is_absolute(self) -> None:
        """data_dir is always resolved to an absolute path."""
        settings = load_settings()
        assert settings.data_dir.is_absolute()

    def test_derived_watch_history_db_path(self) -> None:
        """watch_history_db property is inside data_dir."""
        settings = load_settings()
        assert settings.watch_history_db == settings.data_dir / "watch_history.db"

    def test_derived_media_cache_db_path(self) -> None:
        """media_cache_db property is inside data_dir."""
        settings = load_settings()
        assert settings.media_cache_db == settings.data_dir / "media_cache.db"

    def test_derived_log_dir(self) -> None:
        """log_dir property is inside data_dir."""
        settings = load_settings()
        assert settings.log_dir == settings.data_dir / "logs"

    def test_has_tmdb_key_false_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """has_tmdb_key() returns False when key is set to empty string."""
        monkeypatch.setenv("TMDB_API_KEY", "")
        settings = load_settings()
        assert not settings.has_tmdb_key()

    def test_has_tmdb_key_true_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """has_tmdb_key() returns True when a key is provided."""
        monkeypatch.setenv("TMDB_API_KEY", "fake_key_abc123")
        settings = load_settings()
        assert settings.has_tmdb_key()


class TestEnvVarOverride:
    """Verify environment variable overrides."""

    def test_tmdb_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """TMDB_API_KEY env var is picked up by settings."""
        monkeypatch.setenv("TMDB_API_KEY", "env_test_key_xyz")
        settings = load_settings()
        assert settings.tmdb_api_key == "env_test_key_xyz"

    def test_youtube_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """YOUTUBE_API_KEY env var is picked up by settings."""
        monkeypatch.setenv("YOUTUBE_API_KEY", "yt_key_test")
        settings = load_settings()
        assert settings.youtube_api_key == "yt_key_test"

    def test_st_prefixed_activitywatch_port(self) -> None:
        """Programmatic override sets activitywatch_port correctly."""
        settings = load_settings(activitywatch_port=9999)
        assert settings.activitywatch_port == 9999

    def test_st_prefixed_media_service_port(self) -> None:
        """Programmatic override sets media_service_port correctly."""
        settings = load_settings(media_service_port=8888)
        assert settings.media_service_port == 8888

    def test_st_ocr_enabled_false(self) -> None:
        """Programmatic override disables OCR."""
        settings = load_settings(ocr_enabled=False)
        assert settings.ocr_enabled is False

    def test_data_dir_override_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ST_DATA_DIR env var overrides the default data directory."""
        with tempfile.TemporaryDirectory() as tmp:
            monkeypatch.setenv("ST_DATA_DIR", tmp)
            settings = load_settings()
            assert settings.data_dir == Path(tmp).expanduser().resolve()


class TestConfigPriority:
    """Verify programmatic overrides beat defaults."""

    def test_programmatic_override_beats_default(self) -> None:
        """Keyword arguments to load_settings() override defaults."""
        with tempfile.TemporaryDirectory() as tmp:
            settings = load_settings(data_dir=tmp)
            assert settings.data_dir == Path(tmp).expanduser().resolve()

    def test_env_var_beats_file_default(self) -> None:
        """Programmatic overrides take precedence over JSON file defaults."""
        settings = load_settings(heartbeat_interval=60)
        assert settings.heartbeat_interval == 60

    def test_threshold_validation_error(self) -> None:
        """Settings raises ValueError if review_threshold > auto_log_threshold."""
        with pytest.raises(ValueError):
            Settings(review_threshold=0.95, auto_log_threshold=0.85)

    def test_ensure_directories_creates_data_dir(self) -> None:
        """ensure_directories() creates the data directory."""
        with tempfile.TemporaryDirectory() as tmp:
            new_dir = Path(tmp) / "new_subdir"
            settings = load_settings(data_dir=str(new_dir))
            settings.ensure_directories()
            assert new_dir.exists()
            assert (new_dir / "logs").exists()
