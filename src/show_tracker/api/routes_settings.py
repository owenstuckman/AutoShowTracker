"""Settings and aliases API routes.

Provides endpoints for reading/updating user settings and managing
show name aliases.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from show_tracker.api.schemas import (
    AliasCreate,
    AliasOut,
    SettingOut,
    SettingUpdate,
)
from show_tracker.storage.models import ShowAlias, UserSetting

router = APIRouter(prefix="/api", tags=["settings"])


# ---------------------------------------------------------------------------
# GET /api/settings
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=list[SettingOut])
async def get_all_settings(request: Request) -> list[SettingOut]:
    """Return all user settings as key-value pairs."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = session.query(UserSetting).order_by(UserSetting.key).all()
        return [
            SettingOut(key=r.key, value=r.value)
            for r in rows
        ]


# ---------------------------------------------------------------------------
# PUT /api/settings/{key}
# ---------------------------------------------------------------------------

@router.put("/settings/{key}", response_model=SettingOut)
async def update_setting(
    key: str,
    body: SettingUpdate,
    request: Request,
) -> SettingOut:
    """Create or update a single setting."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        existing = session.query(UserSetting).filter(UserSetting.key == key).first()
        if existing is None:
            setting = UserSetting(key=key, value=body.value)
            session.add(setting)
        else:
            existing.value = body.value

    return SettingOut(key=key, value=body.value)


# ---------------------------------------------------------------------------
# POST /api/aliases
# ---------------------------------------------------------------------------

@router.post("/aliases", response_model=AliasOut, status_code=201)
async def add_alias(body: AliasCreate, request: Request) -> AliasOut:
    """Add a new show alias for name resolution."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        # Check for duplicate
        existing = (
            session.query(ShowAlias)
            .filter(ShowAlias.alias == body.alias)
            .first()
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Alias '{body.alias}' already exists (show_id={existing.show_id})",
            )

        alias = ShowAlias(
            show_id=body.show_id,
            alias=body.alias,
            source="user",
        )
        session.add(alias)
        session.flush()

        return AliasOut(
            id=alias.id,
            show_id=alias.show_id,
            alias=alias.alias,
            source=alias.source,
        )


# ---------------------------------------------------------------------------
# GET /api/aliases/{show_id}
# ---------------------------------------------------------------------------

@router.get("/aliases/{show_id}", response_model=list[AliasOut])
async def get_aliases(show_id: int, request: Request) -> list[AliasOut]:
    """Return all aliases for a given show."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(ShowAlias)
            .filter(ShowAlias.show_id == show_id)
            .order_by(ShowAlias.alias)
            .all()
        )
        return [
            AliasOut(id=r.id, show_id=r.show_id, alias=r.alias, source=r.source)
            for r in rows
        ]


# ---------------------------------------------------------------------------
# DELETE /api/aliases/{alias_id}
# ---------------------------------------------------------------------------

@router.delete("/aliases/{alias_id}")
async def delete_alias(alias_id: int, request: Request) -> dict[str, str]:
    """Remove a show alias."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        alias = session.query(ShowAlias).filter(ShowAlias.id == alias_id).first()
        if alias is None:
            raise HTTPException(status_code=404, detail="Alias not found")
        session.delete(alias)

    return {"status": "ok", "message": "Alias deleted"}
