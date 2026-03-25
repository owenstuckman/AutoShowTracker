"""Default alias seed data for show name resolution.

Maps common abbreviations, acronyms, and alternate spellings to their
canonical show titles.  Used during first-run database initialisation so
the identification pipeline can resolve shorthand inputs without a TMDb
round-trip.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from show_tracker.storage.models import Show, ShowAlias

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Seed data: alias -> canonical title
# -----------------------------------------------------------------------
# Keep sorted by canonical title for maintainability.

INITIAL_ALIASES: dict[str, str] = {
    # American Horror Story
    "ahs": "American Horror Story",
    "american horror": "American Horror Story",
    # Attack on Titan
    "aot": "Attack on Titan",
    "shingeki no kyojin": "Attack on Titan",
    "snk": "Attack on Titan",
    # Avatar: The Last Airbender
    "atla": "Avatar: The Last Airbender",
    "avatar tla": "Avatar: The Last Airbender",
    # Better Call Saul
    "bcs": "Better Call Saul",
    # Bob's Burgers
    "bobs burgers": "Bob's Burgers",
    # Brooklyn Nine-Nine
    "b99": "Brooklyn Nine-Nine",
    "brooklyn 99": "Brooklyn Nine-Nine",
    "brooklyn nine nine": "Brooklyn Nine-Nine",
    # Breaking Bad
    "bb": "Breaking Bad",
    "brba": "Breaking Bad",
    # Criminal Minds
    "cm": "Criminal Minds",
    # CSI: Crime Scene Investigation
    "csi": "CSI: Crime Scene Investigation",
    # Curb Your Enthusiasm
    "curb": "Curb Your Enthusiasm",
    "cye": "Curb Your Enthusiasm",
    # Doctor Who
    "dr who": "Doctor Who",
    # Dragon Ball Z
    "dbz": "Dragon Ball Z",
    # Game of Thrones
    "got": "Game of Thrones",
    "game of thrones": "Game of Thrones",
    # Grey's Anatomy
    "greys": "Grey's Anatomy",
    "greys anatomy": "Grey's Anatomy",
    # How I Met Your Mother
    "himym": "How I Met Your Mother",
    "how i met your mother": "How I Met Your Mother",
    # It's Always Sunny in Philadelphia
    "iasip": "It's Always Sunny in Philadelphia",
    "always sunny": "It's Always Sunny in Philadelphia",
    "its always sunny": "It's Always Sunny in Philadelphia",
    # Law & Order: Special Victims Unit
    "l&o svu": "Law & Order: Special Victims Unit",
    "law and order svu": "Law & Order: Special Victims Unit",
    "svu": "Law & Order: Special Victims Unit",
    "law & order svu": "Law & Order: Special Victims Unit",
    # My Hero Academia
    "mha": "My Hero Academia",
    "bnha": "My Hero Academia",
    "boku no hero academia": "My Hero Academia",
    # NCIS: Los Angeles
    "ncis la": "NCIS: Los Angeles",
    "ncis los angeles": "NCIS: Los Angeles",
    # One Piece
    "op": "One Piece",
    # Orange Is the New Black
    "oitnb": "Orange Is the New Black",
    "orange is the new black": "Orange Is the New Black",
    # Parks and Recreation
    "parks and rec": "Parks and Recreation",
    "pandr": "Parks and Recreation",
    # Rick and Morty
    "rick & morty": "Rick and Morty",
    "r&m": "Rick and Morty",
    # Stranger Things
    "st": "Stranger Things",
    # The Big Bang Theory
    "tbbt": "The Big Bang Theory",
    "big bang theory": "The Big Bang Theory",
    # The Flash
    "flash": "The Flash",
    # The Legend of Korra
    "tlok": "The Legend of Korra",
    "lok": "The Legend of Korra",
    # The Office (US)
    "the office us": "The Office",
    # The Simpsons
    "simpsons": "The Simpsons",
    # The Walking Dead
    "twd": "The Walking Dead",
    "walking dead": "The Walking Dead",
    # The Witcher
    "witcher": "The Witcher",
    # True Detective
    "td": "True Detective",
    # Westworld
    "ww": "Westworld",
}


def seed_aliases(db_session: Session) -> int:
    """Insert initial alias mappings into the ``show_aliases`` table.

    For each alias in :data:`INITIAL_ALIASES`, the function:

    1. Finds or creates the :class:`~show_tracker.storage.models.Show` row
       for the canonical title.
    2. Inserts a :class:`~show_tracker.storage.models.ShowAlias` row if one
       with that alias string does not already exist.

    Parameters
    ----------
    db_session:
        An active SQLAlchemy session bound to the watch-history database.

    Returns
    -------
    int
        Number of new alias rows inserted (skips duplicates).
    """
    inserted = 0
    # Cache show lookups within this call to avoid repeated queries.
    show_cache: dict[str, Show] = {}

    for alias_text, canonical_title in INITIAL_ALIASES.items():
        # Check if alias already exists
        existing = (
            db_session.query(ShowAlias)
            .filter(ShowAlias.alias == alias_text)
            .first()
        )
        if existing is not None:
            continue

        # Find or create the show
        if canonical_title in show_cache:
            show = show_cache[canonical_title]
        else:
            show_or_none = (
                db_session.query(Show)
                .filter(Show.title == canonical_title)
                .first()
            )
            if show_or_none is None:
                show = Show(title=canonical_title)
                db_session.add(show)
                db_session.flush()  # materialise the id
            else:
                show = show_or_none
            show_cache[canonical_title] = show

        db_session.add(
            ShowAlias(show_id=show.id, alias=alias_text, source="seed")
        )
        inserted += 1

    logger.info("Seeded %d aliases (%d total defined)", inserted, len(INITIAL_ALIASES))
    return inserted
