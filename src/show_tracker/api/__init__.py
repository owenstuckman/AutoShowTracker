"""FastAPI web backend for AutoShowTracker.

Exposes the ``app`` object for uvicorn and re-exports it for convenience::

    uvicorn show_tracker.api:app --reload
"""

from show_tracker.api.app import app

__all__ = ["app"]
