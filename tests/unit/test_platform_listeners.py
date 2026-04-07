"""Async integration tests for platform-specific listeners and AW process management.

Covers:
- SMTCListener: session attachment/detachment, event emission (winsdk mocked)
- MPRISListener: D-Bus connection, player discovery, signal dispatch (dbus-next mocked)
- ActivityWatchManager: subprocess launch, shutdown, health check (subprocess mocked)
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_smtc_session(title: str = "Test Show", status: int = 4) -> MagicMock:
    """Build a mock SMTC session object."""
    props = MagicMock()
    props.title = title
    props.artist = ""
    props.album_title = ""

    playback = MagicMock()
    playback.playback_status = status  # 4 = Playing

    session = MagicMock()
    session.source_app_user_model_id = "TestApp"
    session.try_get_media_properties_async = AsyncMock(return_value=props)
    session.get_playback_info = MagicMock(return_value=playback)
    session.add_media_properties_changed = MagicMock(return_value=MagicMock())
    session.add_playback_info_changed = MagicMock(return_value=MagicMock())
    return session


# ---------------------------------------------------------------------------
# 1. SMTCListener async integration
# ---------------------------------------------------------------------------


class TestSMTCListenerAsync:
    """SMTCListener behaviour with winsdk fully mocked."""

    def _make_listener(self, session: MagicMock | None = None) -> tuple[MagicMock, object]:
        """Patch winsdk and return (mock_manager, listener)."""
        from show_tracker.detection.smtc_listener import SMTCListener

        mock_manager = MagicMock()
        mock_manager.get_current_session = MagicMock(return_value=session)
        mock_manager.add_current_session_changed = MagicMock()

        mock_session_manager_cls = MagicMock()
        mock_session_manager_cls.request_async = AsyncMock(return_value=mock_manager)

        with (
            patch("show_tracker.detection.smtc_listener.sys") as mock_sys,
            patch(
                "show_tracker.detection.smtc_listener._WINSDK_AVAILABLE", True
            ),
            patch(
                "show_tracker.detection.smtc_listener.SessionManager",
                mock_session_manager_cls,
                create=True,
            ),
        ):
            mock_sys.platform = "win32"
            listener = SMTCListener()

        return mock_manager, listener, mock_session_manager_cls

    @pytest.mark.asyncio
    async def test_start_calls_request_async(self) -> None:
        """start() must call SessionManager.request_async()."""
        from show_tracker.detection.smtc_listener import SMTCListener

        mock_manager = MagicMock()
        mock_manager.get_current_session = MagicMock(return_value=None)
        mock_manager.add_current_session_changed = MagicMock()

        mock_cls = MagicMock()
        mock_cls.request_async = AsyncMock(return_value=mock_manager)

        with (
            patch("show_tracker.detection.smtc_listener.sys") as mock_sys,
            patch("show_tracker.detection.smtc_listener._WINSDK_AVAILABLE", True),
            patch("show_tracker.detection.smtc_listener.SessionManager", mock_cls, create=True),
        ):
            mock_sys.platform = "win32"
            listener = SMTCListener()
            await listener.start()

        mock_cls.request_async.assert_called_once()
        assert listener._running is True

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self) -> None:
        """Calling start() twice must not call request_async twice."""
        from show_tracker.detection.smtc_listener import SMTCListener

        mock_manager = MagicMock()
        mock_manager.get_current_session = MagicMock(return_value=None)
        mock_manager.add_current_session_changed = MagicMock()

        mock_cls = MagicMock()
        mock_cls.request_async = AsyncMock(return_value=mock_manager)

        with (
            patch("show_tracker.detection.smtc_listener.sys") as mock_sys,
            patch("show_tracker.detection.smtc_listener._WINSDK_AVAILABLE", True),
            patch("show_tracker.detection.smtc_listener.SessionManager", mock_cls, create=True),
        ):
            mock_sys.platform = "win32"
            listener = SMTCListener()
            await listener.start()
            await listener.start()  # second call should no-op

        assert mock_cls.request_async.call_count == 1

    @pytest.mark.asyncio
    async def test_start_attaches_to_session(self) -> None:
        """start() must subscribe to media property and playback events."""
        from show_tracker.detection.smtc_listener import SMTCListener

        session = _make_smtc_session()
        mock_manager = MagicMock()
        mock_manager.get_current_session = MagicMock(return_value=session)
        mock_manager.add_current_session_changed = MagicMock()

        mock_cls = MagicMock()
        mock_cls.request_async = AsyncMock(return_value=mock_manager)

        with (
            patch("show_tracker.detection.smtc_listener.sys") as mock_sys,
            patch("show_tracker.detection.smtc_listener._WINSDK_AVAILABLE", True),
            patch("show_tracker.detection.smtc_listener.SessionManager", mock_cls, create=True),
        ):
            mock_sys.platform = "win32"
            listener = SMTCListener()
            await listener.start()

        session.add_media_properties_changed.assert_called_once()
        session.add_playback_info_changed.assert_called_once()
        assert listener._session is session

    @pytest.mark.asyncio
    async def test_stop_clears_state(self) -> None:
        """stop() must clear manager, session, and running flag."""
        from show_tracker.detection.smtc_listener import SMTCListener

        mock_manager = MagicMock()
        mock_manager.get_current_session = MagicMock(return_value=None)
        mock_manager.add_current_session_changed = MagicMock()

        mock_cls = MagicMock()
        mock_cls.request_async = AsyncMock(return_value=mock_manager)

        with (
            patch("show_tracker.detection.smtc_listener.sys") as mock_sys,
            patch("show_tracker.detection.smtc_listener._WINSDK_AVAILABLE", True),
            patch("show_tracker.detection.smtc_listener.SessionManager", mock_cls, create=True),
        ):
            mock_sys.platform = "win32"
            listener = SMTCListener()
            await listener.start()
            await listener.stop()

        assert listener._running is False
        assert listener._manager is None

    @pytest.mark.asyncio
    async def test_emit_current_state_fires_callbacks(self) -> None:
        """_emit_current_state must invoke registered callbacks with a MediaSessionEvent."""
        from show_tracker.detection.media_session import MediaSessionEvent, PlaybackStatus
        from show_tracker.detection.smtc_listener import SMTCListener

        session = _make_smtc_session(title="Breaking Bad", status=4)
        mock_manager = MagicMock()
        mock_manager.get_current_session = MagicMock(return_value=session)
        mock_manager.add_current_session_changed = MagicMock()

        mock_cls = MagicMock()
        mock_cls.request_async = AsyncMock(return_value=mock_manager)

        received: list[MediaSessionEvent] = []

        with (
            patch("show_tracker.detection.smtc_listener.sys") as mock_sys,
            patch("show_tracker.detection.smtc_listener._WINSDK_AVAILABLE", True),
            patch("show_tracker.detection.smtc_listener.SessionManager", mock_cls, create=True),
        ):
            mock_sys.platform = "win32"
            listener = SMTCListener()
            listener.register_callback(received.append)
            await listener._emit_current_state(session)

        assert len(received) == 1
        assert received[0].title == "Breaking Bad"
        assert received[0].playback_status == PlaybackStatus.PLAYING

    def test_raises_on_non_windows(self) -> None:
        """SMTCListener must raise RuntimeError when not on Windows."""
        from show_tracker.detection.smtc_listener import SMTCListener

        with patch("show_tracker.detection.smtc_listener.sys") as mock_sys:
            mock_sys.platform = "linux"
            with pytest.raises(RuntimeError, match="Windows"):
                SMTCListener()

    def test_raises_without_winsdk(self) -> None:
        """SMTCListener must raise ImportError when winsdk is missing."""
        from show_tracker.detection.smtc_listener import SMTCListener

        with (
            patch("show_tracker.detection.smtc_listener.sys") as mock_sys,
            patch("show_tracker.detection.smtc_listener._WINSDK_AVAILABLE", False),
        ):
            mock_sys.platform = "win32"
            with pytest.raises(ImportError, match="winsdk"):
                SMTCListener()

    def test_on_session_changed_reattaches(self) -> None:
        """_on_session_changed must detach old session and attach new one."""
        from show_tracker.detection.smtc_listener import SMTCListener

        new_session = _make_smtc_session("New Show")
        mock_manager = MagicMock()
        mock_manager.get_current_session = MagicMock(return_value=new_session)
        mock_manager.add_current_session_changed = MagicMock()

        with (
            patch("show_tracker.detection.smtc_listener.sys") as mock_sys,
            patch("show_tracker.detection.smtc_listener._WINSDK_AVAILABLE", True),
        ):
            mock_sys.platform = "win32"
            listener = SMTCListener()
            listener._manager = mock_manager
            listener._running = True

            listener._on_session_changed(mock_manager, None)

        assert listener._session is new_session
        new_session.add_media_properties_changed.assert_called_once()


# ---------------------------------------------------------------------------
# 2. MPRISListener async integration
# ---------------------------------------------------------------------------


def _make_mock_bus(player_names: list[str] | None = None) -> MagicMock:
    """Build a minimal mock D-Bus message bus."""
    names = (player_names or []) + ["org.freedesktop.DBus"]

    dbus_iface = MagicMock()
    dbus_iface.call_list_names = AsyncMock(return_value=names)
    dbus_iface.on_name_owner_changed = MagicMock()

    introspection = MagicMock()
    proxy = MagicMock()
    proxy.get_interface = MagicMock(return_value=dbus_iface)

    bus = MagicMock()
    bus.introspect = AsyncMock(return_value=introspection)
    bus.get_proxy_object = MagicMock(return_value=proxy)
    bus.disconnect = MagicMock()
    return bus


class TestMPRISListenerAsync:
    """MPRISListener behaviour with dbus-next fully mocked."""

    @pytest.mark.asyncio
    async def test_start_connects_to_dbus(self) -> None:
        """start() must call MessageBus().connect()."""
        from show_tracker.detection.mpris_listener import MPRISListener

        mock_bus = _make_mock_bus()
        mock_bus_cls = MagicMock()
        mock_bus_cls.return_value.connect = AsyncMock(return_value=mock_bus)

        with (
            patch("show_tracker.detection.mpris_listener.sys") as mock_sys,
            patch("show_tracker.detection.mpris_listener._DBUS_AVAILABLE", True),
            patch("show_tracker.detection.mpris_listener.MessageBus", mock_bus_cls),
        ):
            mock_sys.platform = "linux"
            listener = MPRISListener()
            await listener.start()
            await listener.stop()

        mock_bus_cls.return_value.connect.assert_called_once()
        assert listener._running is False

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self) -> None:
        """Calling start() twice must only connect once."""
        from show_tracker.detection.mpris_listener import MPRISListener

        mock_bus = _make_mock_bus()
        mock_bus_cls = MagicMock()
        mock_bus_cls.return_value.connect = AsyncMock(return_value=mock_bus)

        with (
            patch("show_tracker.detection.mpris_listener.sys") as mock_sys,
            patch("show_tracker.detection.mpris_listener._DBUS_AVAILABLE", True),
            patch("show_tracker.detection.mpris_listener.MessageBus", mock_bus_cls),
        ):
            mock_sys.platform = "linux"
            listener = MPRISListener()
            await listener.start()
            await listener.start()  # second call should no-op
            await listener.stop()

        assert mock_bus_cls.return_value.connect.call_count == 1

    @pytest.mark.asyncio
    async def test_start_discovers_existing_players(self) -> None:
        """start() must call _track_player for every MPRIS player found on the bus."""
        from show_tracker.detection.mpris_listener import MPRISListener

        player_name = "org.mpris.MediaPlayer2.vlc"
        mock_bus = _make_mock_bus()
        mock_bus_cls = MagicMock()
        mock_bus_cls.return_value.connect = AsyncMock(return_value=mock_bus)

        with (
            patch("show_tracker.detection.mpris_listener.sys") as mock_sys,
            patch("show_tracker.detection.mpris_listener._DBUS_AVAILABLE", True),
            patch("show_tracker.detection.mpris_listener.MessageBus", mock_bus_cls),
        ):
            mock_sys.platform = "linux"
            listener = MPRISListener()

            tracked: list[str] = []

            async def _fake_track(name: str) -> None:
                tracked.append(name)

            with (
                patch.object(listener, "_discover_players", AsyncMock(return_value=[player_name])),
                patch.object(listener, "_track_player", _fake_track),
                patch.object(listener, "_watch_for_new_players", AsyncMock()),
            ):
                await listener.start()
                await listener.stop()

        assert player_name in tracked

    @pytest.mark.asyncio
    async def test_stop_disconnects_bus(self) -> None:
        """stop() must disconnect the D-Bus connection."""
        from show_tracker.detection.mpris_listener import MPRISListener

        mock_bus = _make_mock_bus()
        mock_bus_cls = MagicMock()
        mock_bus_cls.return_value.connect = AsyncMock(return_value=mock_bus)

        with (
            patch("show_tracker.detection.mpris_listener.sys") as mock_sys,
            patch("show_tracker.detection.mpris_listener._DBUS_AVAILABLE", True),
            patch("show_tracker.detection.mpris_listener.MessageBus", mock_bus_cls),
        ):
            mock_sys.platform = "linux"
            listener = MPRISListener()
            await listener.start()
            await listener.stop()

        mock_bus.disconnect.assert_called_once()

    def test_handle_properties_changed_fires_callbacks(self) -> None:
        """_handle_properties_changed must dispatch a MediaSessionEvent to callbacks."""
        from show_tracker.detection.media_session import PlaybackStatus
        from show_tracker.detection.mpris_listener import MPRISListener, _MPRIS_PLAYER_IFACE

        received = []

        # Variant=object means isinstance(v, object) is always True,
        # so _variant_value would try to call .value — avoid that by using
        # a sentinel class that nothing will be an instance of.
        class _FakeVariant:
            pass

        with (
            patch("show_tracker.detection.mpris_listener.sys") as mock_sys,
            patch("show_tracker.detection.mpris_listener._DBUS_AVAILABLE", True),
            patch("show_tracker.detection.mpris_listener.Variant", _FakeVariant),
        ):
            mock_sys.platform = "linux"
            listener = MPRISListener()
            listener.register_callback(received.append)

            listener._handle_properties_changed(
                bus_name="org.mpris.MediaPlayer2.vlc",
                player_name="vlc",
                interface_name=_MPRIS_PLAYER_IFACE,
                changed={
                    "Metadata": {"xesam:title": "Breaking Bad S01E01"},
                    "PlaybackStatus": "Playing",
                },
            )

        assert len(received) == 1
        assert received[0].title == "Breaking Bad S01E01"
        assert received[0].playback_status == PlaybackStatus.PLAYING
        assert received[0].player_name == "vlc"

    def test_handle_properties_changed_ignores_non_player_iface(self) -> None:
        """_handle_properties_changed must ignore signals for other interfaces."""
        from show_tracker.detection.mpris_listener import MPRISListener

        received = []

        class _FakeVariant:
            pass

        with (
            patch("show_tracker.detection.mpris_listener.sys") as mock_sys,
            patch("show_tracker.detection.mpris_listener._DBUS_AVAILABLE", True),
            patch("show_tracker.detection.mpris_listener.Variant", _FakeVariant),
        ):
            mock_sys.platform = "linux"
            listener = MPRISListener()
            listener.register_callback(received.append)

            listener._handle_properties_changed(
                bus_name="org.mpris.MediaPlayer2.vlc",
                player_name="vlc",
                interface_name="org.freedesktop.DBus.Properties",  # wrong iface
                changed={"Metadata": {"xesam:title": "Something"}},
            )

        assert len(received) == 0

    def test_raises_on_non_linux(self) -> None:
        """MPRISListener must raise RuntimeError on non-Linux platforms."""
        from show_tracker.detection.mpris_listener import MPRISListener

        with patch("show_tracker.detection.mpris_listener.sys") as mock_sys:
            mock_sys.platform = "win32"
            with pytest.raises(RuntimeError, match="Linux"):
                MPRISListener()

    def test_raises_without_dbus(self) -> None:
        """MPRISListener must raise ImportError when dbus-next is missing."""
        from show_tracker.detection.mpris_listener import MPRISListener

        with (
            patch("show_tracker.detection.mpris_listener.sys") as mock_sys,
            patch("show_tracker.detection.mpris_listener._DBUS_AVAILABLE", False),
        ):
            mock_sys.platform = "linux"
            with pytest.raises(ImportError, match="dbus-next"):
                MPRISListener()


# ---------------------------------------------------------------------------
# 3. ActivityWatchManager subprocess management
# ---------------------------------------------------------------------------


class TestActivityWatchManager:
    """ActivityWatchManager subprocess lifecycle with subprocess.Popen mocked."""

    def _make_mock_proc(self, pid: int = 1234, returncode: int | None = None) -> MagicMock:
        proc = MagicMock(spec=subprocess.Popen)
        proc.pid = pid
        proc.returncode = returncode
        proc.args = ["/path/to/aw-server-rust", "--port", "5600"]
        proc.poll = MagicMock(return_value=returncode)
        proc.terminate = MagicMock()
        proc.kill = MagicMock()
        proc.wait = MagicMock()
        return proc

    def test_start_attaches_to_existing_server(self) -> None:
        """start() must reuse an already-running AW server without spawning processes."""
        from show_tracker.detection.activitywatch import ActivityWatchManager

        with (
            patch("show_tracker.detection.activitywatch._is_aw_server", return_value=True),
            patch("show_tracker.detection.activitywatch.subprocess.Popen") as mock_popen,
        ):
            mgr = ActivityWatchManager(aw_dir="/fake", port=5600)
            mgr.start()

        mock_popen.assert_not_called()
        assert mgr._using_external is True

    def test_start_launches_processes_when_no_server(self) -> None:
        """start() must spawn aw-server-rust and aw-watcher-window when no server exists."""
        from show_tracker.detection.activitywatch import ActivityWatchManager

        mock_proc = self._make_mock_proc()

        with (
            patch("show_tracker.detection.activitywatch._is_aw_server", return_value=False),
            patch(
                "show_tracker.detection.activitywatch.find_available_port", return_value=5600
            ),
            patch(
                "show_tracker.detection.activitywatch.subprocess.Popen", return_value=mock_proc
            ) as mock_popen,
            patch.object(ActivityWatchManager, "_wait_for_server"),
        ):
            mgr = ActivityWatchManager(aw_dir="/fake", port=5600)
            mgr.start()

        assert mock_popen.call_count == 2  # aw-server-rust + aw-watcher-window
        assert mgr._using_external is False

    def test_shutdown_terminates_all_processes(self) -> None:
        """shutdown() must terminate then wait for every managed process."""
        from show_tracker.detection.activitywatch import ActivityWatchManager

        proc1 = self._make_mock_proc(pid=100)
        proc2 = self._make_mock_proc(pid=101)

        mgr = ActivityWatchManager(aw_dir="/fake", port=5600)
        mgr.processes = [proc1, proc2]
        mgr.shutdown()

        proc1.terminate.assert_called_once()
        proc2.terminate.assert_called_once()
        proc1.wait.assert_called_once()
        proc2.wait.assert_called_once()
        assert mgr.processes == []

    def test_shutdown_kills_unresponsive_processes(self) -> None:
        """shutdown() must kill processes that don't terminate within the timeout."""
        from show_tracker.detection.activitywatch import ActivityWatchManager

        proc = self._make_mock_proc(pid=100)
        proc.wait = MagicMock(side_effect=subprocess.TimeoutExpired(cmd="aw", timeout=5))

        mgr = ActivityWatchManager(aw_dir="/fake", port=5600)
        mgr.processes = [proc]
        mgr.shutdown()

        proc.kill.assert_called_once()

    def test_health_check_removes_dead_processes(self) -> None:
        """health_check() must remove processes that have exited."""
        from show_tracker.detection.activitywatch import ActivityWatchManager

        alive = self._make_mock_proc(pid=100, returncode=None)  # still running
        dead = self._make_mock_proc(pid=101, returncode=1)  # exited

        mgr = ActivityWatchManager(aw_dir="/fake", port=5600)
        mgr.processes = [alive, dead]

        with patch.object(mgr, "_attempt_restart"):
            mgr.health_check()

        assert alive in mgr.processes
        assert dead not in mgr.processes

    def test_health_check_attempts_restart_for_crashed_process(self) -> None:
        """health_check() must call _attempt_restart for any process that has exited."""
        from show_tracker.detection.activitywatch import ActivityWatchManager

        dead = self._make_mock_proc(pid=101, returncode=1)

        mgr = ActivityWatchManager(aw_dir="/fake", port=5600)
        mgr.processes = [dead]

        with patch.object(mgr, "_attempt_restart") as mock_restart:
            mgr.health_check()

        mock_restart.assert_called_once()

    def test_attempt_restart_gives_up_after_max_retries(self) -> None:
        """_attempt_restart must stop retrying after _MAX_CRASH_RETRIES consecutive crashes."""
        from show_tracker.detection.activitywatch import ActivityWatchManager, _MAX_CRASH_RETRIES

        mgr = ActivityWatchManager(aw_dir="/fake", port=5600)

        with (
            patch.object(mgr, "_start_process") as mock_start,
            patch("show_tracker.detection.activitywatch.time.sleep"),
        ):
            for _ in range(_MAX_CRASH_RETRIES + 2):
                mgr._attempt_restart("aw-server-rust")

        # Restarts on attempt 1..MAX_CRASH_RETRIES, gives up on MAX_CRASH_RETRIES+1
        assert mock_start.call_count == _MAX_CRASH_RETRIES

    def test_shutdown_is_safe_when_no_processes(self) -> None:
        """shutdown() must not raise when the process list is empty."""
        from show_tracker.detection.activitywatch import ActivityWatchManager

        mgr = ActivityWatchManager(aw_dir="/fake", port=5600)
        mgr.shutdown()  # should not raise
        assert mgr.processes == []
