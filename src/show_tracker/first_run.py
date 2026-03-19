"""First-run wizard for Show Tracker.

Guides new users through initial setup: TMDb API key configuration
and database initialization. Can be run as a CLI wizard or triggered
automatically on first startup.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click

logger = logging.getLogger(__name__)


def needs_first_run(data_dir: Path) -> bool:
    """Check whether first-run setup is needed.

    Returns True if the watch history database does not exist yet.
    """
    return not (data_dir / "watch_history.db").exists()


def run_first_run_wizard(data_dir: Path) -> dict[str, str]:
    """Interactive CLI wizard for first-time setup.

    Prompts for a TMDb API key, validates it, writes it to ``.env``,
    and initializes the databases.

    Returns:
        Dict of configured settings (e.g. ``{"tmdb_api_key": "abc..."}``)
    """
    click.echo()
    click.secho("Welcome to Show Tracker!", fg="cyan", bold=True)
    click.echo("Let's get you set up.\n")

    # Step 1: TMDb API key
    click.echo("Step 1: TMDb API Key")
    click.echo("  You need a free API key from The Movie Database (TMDb).")
    click.echo("  Get one at: https://www.themoviedb.org/settings/api\n")

    api_key = click.prompt("  Enter your TMDb API key", type=str).strip()

    # Validate the key
    if api_key:
        click.echo("  Validating key...", nl=False)
        if _validate_tmdb_key(api_key):
            click.secho(" OK", fg="green")
        else:
            click.secho(" FAILED", fg="red")
            click.echo("  The key could not be validated. You can fix it later in .env")

    # Step 2: Write .env
    env_path = Path.cwd() / ".env"
    _write_env_key(env_path, "TMDB_API_KEY", api_key)
    click.echo(f"\n  Saved TMDB_API_KEY to {env_path}")

    # Step 3: Initialize databases
    click.echo("\nStep 2: Initializing databases...")
    data_dir.mkdir(parents=True, exist_ok=True)

    from show_tracker.storage.database import DatabaseManager

    db = DatabaseManager(data_dir=data_dir)
    db.init_databases()
    db.close()

    click.echo(f"  Databases created in {data_dir}")
    click.echo()
    click.secho("Setup complete! Run 'show-tracker run' to start.", fg="green", bold=True)
    click.echo()

    return {"tmdb_api_key": api_key}


def _validate_tmdb_key(api_key: str) -> bool:
    """Make a test API call to verify the TMDb key works."""
    try:
        import httpx

        resp = httpx.get(
            "https://api.themoviedb.org/3/configuration",
            params={"api_key": api_key},
            timeout=10.0,
        )
        return resp.status_code == 200
    except Exception:
        logger.debug("TMDb key validation failed", exc_info=True)
        return False


def _write_env_key(env_path: Path, key: str, value: str) -> None:
    """Write or update a key in a .env file."""
    lines: list[str] = []
    found = False

    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
                lines[i] = f"{key}={value}\n"
                found = True
                break

    if not found:
        lines.append(f"{key}={value}\n")

    env_path.write_text("".join(lines), encoding="utf-8")
