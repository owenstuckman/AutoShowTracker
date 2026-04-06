"""CLI entry point for Show Tracker.

Provides commands to launch all services, run standalone identification,
exercise the test pipeline, and initialise databases.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Coroutine

import click

from show_tracker import __version__
from show_tracker.config import load_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine from synchronous Click handlers."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro)


def _echo_json(data: dict[str, Any]) -> None:
    """Pretty-print a dict as JSON to stdout."""
    click.echo(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(version=__version__, prog_name="show-tracker")
@click.option(
    "--data-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Override the default data directory (~/.show-tracker).",
)
@click.pass_context
def cli(ctx: click.Context, data_dir: Path | None) -> None:
    """Show Tracker -- automatic cross-platform media tracking."""
    overrides: dict[str, Any] = {}
    if data_dir is not None:
        overrides["data_dir"] = data_dir
    ctx.ensure_object(dict)
    ctx.obj["settings"] = load_settings(**overrides)


# ---------------------------------------------------------------------------
# run -- main launcher
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind address for the HTTP API.")
@click.option(
    "--port", type=int, default=None, help="Port for the HTTP API (default: from config)."
)
@click.pass_context
def run(ctx: click.Context, host: str, port: int | None) -> None:
    """Start all Show Tracker services.

    Launches the media identification service, ActivityWatch integration,
    SMTC/MPRIS listener, and the local HTTP API.
    """
    settings = ctx.obj["settings"]
    if port is not None:
        settings.media_service_port = port
    settings.ensure_directories()

    # Check for first-run
    from show_tracker.first_run import needs_first_run

    if needs_first_run(settings.data_dir):
        click.echo("First-time setup detected.")
        if click.confirm("Would you like to run the setup wizard?", default=True):
            from show_tracker.first_run import run_first_run_wizard

            run_first_run_wizard(settings.data_dir)
            # Reload settings after wizard writes .env
            settings = load_settings()
            ctx.obj["settings"] = settings

    # Wire up file + console logging before anything else.
    from show_tracker.utils.logging import setup_logging

    setup_logging(log_dir=settings.log_dir)

    async def _start() -> None:
        click.echo(f"Show Tracker v{__version__}")
        click.echo(f"  Data directory : {settings.data_dir}")
        click.echo(f"  HTTP API       : http://{host}:{settings.media_service_port}")
        click.echo(f"  AW endpoint    : http://127.0.0.1:{settings.activitywatch_port}")
        click.echo(f"  OCR enabled    : {settings.ocr_enabled}")
        click.echo(f"  TMDb key set   : {settings.has_tmdb_key()}")
        click.echo()

        if not settings.has_tmdb_key():
            click.secho(
                "WARNING: TMDB_API_KEY is not set. Content identification will not work.",
                fg="yellow",
                err=True,
            )

        # Start system tray icon (non-blocking)
        tray = None
        try:
            from show_tracker.tray import TrayIcon

            dashboard_url = f"http://{host}:{settings.media_service_port}/"
            tray = TrayIcon(dashboard_url=dashboard_url)
            tray.start()
        except Exception:
            pass  # pystray not available — continue without tray

        # Import here to avoid heavy imports when running lightweight commands.
        import uvicorn

        config = uvicorn.Config(
            "show_tracker.api:app",
            host=host,
            port=settings.media_service_port,
            log_level="info",
            factory=False,
        )
        server = uvicorn.Server(config)

        click.echo("Starting services... (press Ctrl+C to stop)")
        try:
            await server.serve()
        except KeyboardInterrupt:
            click.echo("\nShutting down gracefully...")
        finally:
            if tray is not None:
                tray.stop()

    _run_async(_start())


# ---------------------------------------------------------------------------
# identify -- Phase 0 standalone identification
# ---------------------------------------------------------------------------


@cli.command()
@click.argument("raw_string")
@click.option("--source", default="manual", help="Source type hint (e.g. browser_title, filename).")
@click.pass_context
def identify(ctx: click.Context, raw_string: str, source: str) -> None:
    """Identify a media title from a raw string.

    Takes a raw window title, filename, or browser tab title and attempts
    to resolve it to a canonical TMDb episode entry.

    Example:

        show-tracker identify "law.and.order.svu.s03e07.720p.bluray.mkv"
    """
    settings = ctx.obj["settings"]

    if not settings.has_tmdb_key():
        click.secho("Error: TMDB_API_KEY environment variable is required.", fg="red", err=True)
        raise SystemExit(1)

    async def _identify() -> None:
        # Lazy import so the CLI stays responsive for --help etc.
        from show_tracker.identification import identify_media

        result = await identify_media(raw_string, source=source, settings=settings)
        if result is None:
            click.secho("No match found.", fg="yellow")
            raise SystemExit(1)

        _echo_json(result)

    _run_async(_identify())


# ---------------------------------------------------------------------------
# test-pipeline -- batch-test the identification pipeline
# ---------------------------------------------------------------------------


@cli.command("test-pipeline")
@click.option(
    "--dataset",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Path to a JSON test dataset file. Each entry should have 'input' and 'expected' keys.",
)
@click.option("--verbose", "-v", is_flag=True, help="Print per-case results.")
@click.pass_context
def test_pipeline(ctx: click.Context, dataset: Path | None, verbose: bool) -> None:
    """Run a test dataset through the identification pipeline.

    Reads a JSON file of test cases and reports accuracy metrics.
    Each test case should be an object with at least:

    \b
      {
        "input": "law.and.order.svu.s03e07.720p.bluray.mkv",
        "expected": {
          "show": "Law & Order: Special Victims Unit",
          "season": 3,
          "episode": 7
        }
      }
    """
    settings = ctx.obj["settings"]

    if not settings.has_tmdb_key():
        click.secho("Error: TMDB_API_KEY environment variable is required.", fg="red", err=True)
        raise SystemExit(1)

    if dataset is None:
        default_path = (
            Path(__file__).resolve().parent.parent.parent
            / "tests"
            / "data"
            / "identification_dataset.json"
        )
        if not default_path.exists():
            click.secho(
                f"No dataset found at {default_path}. Provide one with --dataset.",
                fg="red",
                err=True,
            )
            raise SystemExit(1)
        dataset = default_path

    async def _run_pipeline() -> None:
        from show_tracker.identification import identify_media

        with open(dataset, encoding="utf-8") as fh:
            cases: list[dict[str, Any]] = json.load(fh)

        total = len(cases)
        correct = 0
        failures: list[dict[str, Any]] = []

        click.echo(f"Running {total} test cases...")
        click.echo()

        for i, case in enumerate(cases, start=1):
            raw_input = case["input"]
            expected = case["expected"]
            source = case.get("source", "test")

            result = await identify_media(raw_input, source=source, settings=settings)

            matched = _check_match(result, expected)
            if matched:
                correct += 1
                if verbose:
                    click.secho(f"  [{i}/{total}] PASS: {raw_input}", fg="green")
            else:
                failures.append({"input": raw_input, "expected": expected, "got": result})
                if verbose:
                    click.secho(f"  [{i}/{total}] FAIL: {raw_input}", fg="red")
                    click.echo(f"         expected: {expected}")
                    click.echo(f"         got:      {result}")

        accuracy = (correct / total * 100) if total else 0.0
        click.echo()
        click.echo(f"Results: {correct}/{total} correct ({accuracy:.1f}%)")

        if failures and not verbose:
            click.echo(f"\n{len(failures)} failures (use -v to see details)")

        if accuracy < 80.0:
            click.secho(
                f"\nAccuracy {accuracy:.1f}% is below the 80% target.",
                fg="yellow",
            )

    _run_async(_run_pipeline())


def _check_match(result: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    """Compare an identification result against expected values."""
    if result is None:
        return False

    # Compare season and episode numbers (required).
    if result.get("season") != expected.get("season"):
        return False
    if result.get("episode") != expected.get("episode"):
        return False

    # If an expected show name is given, do a case-insensitive substring check
    # to handle minor formatting differences.
    expected_show = expected.get("show", "").lower()
    result_show = result.get("show_name", "").lower()
    return not (
        expected_show and expected_show not in result_show and result_show not in expected_show
    )


# ---------------------------------------------------------------------------
# init-db -- database initialisation
# ---------------------------------------------------------------------------


@cli.command("init-db")
@click.option("--force", is_flag=True, help="Drop and recreate tables if they already exist.")
@click.pass_context
def init_db(ctx: click.Context, force: bool) -> None:
    """Initialise the watch-history and media-cache databases.

    Creates the data directory and database files with the required schema.
    Existing data is preserved unless --force is passed.
    """
    settings = ctx.obj["settings"]
    settings.ensure_directories()

    async def _init() -> None:
        from show_tracker.storage.database import DatabaseManager

        click.echo(f"Data directory: {settings.data_dir}")
        db = DatabaseManager(data_dir=settings.data_dir)
        db.init_databases()
        click.echo("Databases initialised successfully.")
        click.echo(f"  watch_history : {db.watch_db_path}")
        click.echo(f"  media_cache   : {db.cache_db_path}")
        db.close()

    _run_async(_init())


# ---------------------------------------------------------------------------
# setup -- first-run wizard (can be run manually)
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def setup(ctx: click.Context) -> None:
    """Run the first-time setup wizard.

    Prompts for a TMDb API key, validates it, and initialises databases.
    Can be re-run at any time to reconfigure.
    """
    settings = ctx.obj["settings"]

    from show_tracker.first_run import run_first_run_wizard

    run_first_run_wizard(settings.data_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
