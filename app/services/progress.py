"""Episode progress — manual marking (issue #2).

MediaShelf never plays TV: `video_options` hands out deep links and the session
continues inside Netflix or Prime, where nothing reports back. So there is no
playback signal to derive watched state from, and marking is manual — the same
constraint JustWatch works under, and the same answer.

Automatic state has to come from something that *does* see playback: a Plex or
Jellyfin server, or Trakt. Both are connectors that would write into this store
rather than replace it, so the shape here is deliberately source-agnostic — a
row says "this episode was watched", not "the user ticked a box".

Stored as `LibraryEntry` rows, not a new table. `entry_type` is a free-form
string and every existing reader filters to its own known values, so a new type
is invisible to them; this adds no columns and needs no migration (there is no
Alembic — `create_all()` would not reach an existing database).
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LibraryEntry

logger = logging.getLogger(__name__)

ENTRY_TYPE = "watched_episode"


def _external_id(item_id: int, season: int, episode: int) -> str:
    """Dedupe key. LibraryEntry has no unique constraint, so uniqueness is
    enforced here the same way the watchlist importer does it (api.py)."""
    return f"{item_id}:s{season}:e{episode}"


def watched(db: Session, item_id: int) -> set[tuple[int, int]]:
    """Every (season, episode) marked watched for one show."""
    rows = db.scalars(select(LibraryEntry).where(
        LibraryEntry.entry_type == ENTRY_TYPE,
        LibraryEntry.media_item_id == item_id))
    out: set[tuple[int, int]] = set()
    for row in rows:
        season, episode = row.payload.get("season"), row.payload.get("episode")
        if season is not None and episode is not None:
            out.add((int(season), int(episode)))
    return out


def mark(db: Session, item_id: int, season: int, episodes: list[int],
         is_watched: bool) -> set[tuple[int, int]]:
    """Mark or unmark episodes of one season. Takes a list so "watch this whole
    season" is a single call rather than twenty. Returns the resulting set."""
    current = watched(db, item_id)
    if is_watched:
        for episode in episodes:
            if (season, episode) in current:
                continue  # already marked — never write a duplicate row
            db.add(LibraryEntry(
                media_item_id=item_id, entry_type=ENTRY_TYPE,
                external_id=_external_id(item_id, season, episode),
                payload={"season": season, "episode": episode, "source": "manual"}))
            current.add((season, episode))
    else:
        wanted = {_external_id(item_id, season, e) for e in episodes}
        for row in db.scalars(select(LibraryEntry).where(
                LibraryEntry.entry_type == ENTRY_TYPE,
                LibraryEntry.media_item_id == item_id)):
            if row.external_id in wanted:
                db.delete(row)
        current -= {(season, e) for e in episodes}
    db.commit()
    return current


def state_of(item, seen: set[tuple[int, int]]) -> dict:
    """Summarise straight off a MediaItem, reading the cached season data in
    ``extra``. One code path for the title page and the shelf rail, so the two
    can never disagree about whether you are caught up."""
    return summarise(
        item.extra.get("seasons") or [], seen,
        status=item.extra.get("show_status"),
        last_aired=item.extra.get("last_aired"),
        next_air_date=item.extra.get("next_air_date"))


def tracked_shows(db: Session) -> dict[int, set[tuple[int, int]]]:
    """Watched episodes grouped by show, plus the most recent mark per show.

    One query for the whole shelf — the rail must not turn into N queries.
    """
    rows = db.scalars(select(LibraryEntry)
                      .where(LibraryEntry.entry_type == ENTRY_TYPE,
                             LibraryEntry.media_item_id.isnot(None))
                      .order_by(LibraryEntry.created_at))
    out: dict[int, set[tuple[int, int]]] = {}
    for row in rows:
        season, episode = row.payload.get("season"), row.payload.get("episode")
        if season is None or episode is None:
            continue
        out.setdefault(row.media_item_id, set()).add((int(season), int(episode)))
    return out


def last_marked_at(db: Session) -> dict[int, object]:
    """When each show was last marked — the ordering for Continue watching, so
    the show you touched most recently leads."""
    rows = db.scalars(select(LibraryEntry)
                      .where(LibraryEntry.entry_type == ENTRY_TYPE,
                             LibraryEntry.media_item_id.isnot(None))
                      .order_by(LibraryEntry.created_at))
    out: dict[int, object] = {}
    for row in rows:
        out[row.media_item_id] = row.created_at  # ascending → last write wins
    return out


def clear(db: Session, item_id: int) -> int:
    """Forget all progress for a show. Returns how many rows went."""
    rows = list(db.scalars(select(LibraryEntry).where(
        LibraryEntry.entry_type == ENTRY_TYPE,
        LibraryEntry.media_item_id == item_id)))
    for row in rows:
        db.delete(row)
    db.commit()
    return len(rows)


# A show whose run is over can be "seen"; one still going can only be "caught up".
ENDED_STATUSES = {"Ended", "Canceled", "Cancelled"}

# The four states JustWatch sorts a tracked show into. Matching them is the
# point of issue #2 — "just like in JustWatch" means the library reorganises
# itself, not only that episodes have tick-boxes.
NOT_STARTED, WATCHING, CAUGHT_UP, SEEN = "not_started", "watching", "caught_up", "seen"


def aired_count(seasons: list[dict], last_aired: dict | None) -> int:
    """How many episodes exist so far, per TMDB's `last_episode_to_air`.

    Without it (older or sparsely-tracked shows) assume everything listed has
    aired — the safe direction, since it can only under-report "caught up",
    never claim you are up to date on an episode that doesn't exist yet.
    """
    total = sum(s.get("episode_count") or 0 for s in seasons)
    if not last_aired:
        return total
    aired = 0
    for season in seasons:
        number = season["season_number"]
        count = season.get("episode_count") or 0
        if number < last_aired["season"]:
            aired += count
        elif number == last_aired["season"]:
            aired += min(last_aired["episode"], count)
    return min(aired, total)


def summarise(seasons: list[dict], seen: set[tuple[int, int]], *,
              status: str | None = None, last_aired: dict | None = None,
              next_air_date: str | None = None) -> dict:
    """Per-season counts, the next unwatched episode, and the show's state.

    `seasons` carries TMDB's `episode_count`, which is the total we compare
    against — so a season reads 6/10 even before its episode list is opened.
    Next-up walks seasons in order and returns the first gap, which is what
    "where was I" actually means for someone bingeing in order.
    """
    per_season, total, watched_total = [], 0, 0
    next_up = None
    for season in seasons:
        number = season["season_number"]
        count = season.get("episode_count") or 0
        marked = sorted(e for (s, e) in seen if s == number)
        total += count
        watched_total += len(marked)
        if next_up is None:
            # First episode in this season that isn't marked. Episode numbers
            # are 1-based and TMDB is not always contiguous, so scan the range
            # rather than trusting max(marked) + 1.
            gap = next((e for e in range(1, count + 1) if (number, e) not in seen), None)
            if gap is not None:
                next_up = {"season": number, "episode": gap}
        per_season.append({
            "season_number": number,
            "name": season.get("name"),
            "episode_count": count,
            "air_date": season.get("air_date"),
            "watched_count": len(marked),
        })

    aired = aired_count(seasons, last_aired)
    # Only episodes that already exist can be "waiting for you" — counting
    # unaired ones would park every running show permanently in Watching.
    unwatched_aired = max(aired - watched_total, 0)
    complete = total > 0 and watched_total >= total
    ended = (status or "") in ENDED_STATUSES
    if watched_total == 0:
        state = NOT_STARTED
    elif complete and ended:
        state = SEEN
    elif unwatched_aired > 0:
        state = WATCHING
    else:
        state = CAUGHT_UP
    return {
        "seasons": per_season,
        "total_episodes": total,
        "watched_episodes": watched_total,
        "aired_episodes": aired,
        "unwatched_aired": unwatched_aired,
        "next_up": next_up,
        "complete": complete,
        "state": state,
        "show_status": status,
        "next_air_date": next_air_date,
    }
