"""Resolve a bare title string to a TMDB entry.

Imports arrive as text — a pasted list, an official data export, Netflix's
published Top 10 TSV — never as ids. This is the shared machinery that turns
"Ludo" into the right TMDB row, and it lives in services/ rather than the HTTP
layer because providers need it too: `app/providers/netflix_top10.py` resolves
the same way the import endpoint does, and neither should import from `api.py`.

Article-insensitive by design ("Devil's Advocate" == "The Devil's Advocate"),
because published lists and streaming UIs disagree about leading articles.
"""

import re

from app.providers.tmdb import TMDBClient

_ARTICLE_RE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)

# Candidates checked against the source service before falling back. Each costs
# a watch-providers call, so this is a deliberate ceiling, not a magic number.
_SERVICE_CHECK_LIMIT = 6


def norm_title(t: str) -> str:
    t = _ARTICLE_RE.sub("", t.lower().strip())
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def resolve_best(results: list[dict], title: str, year: int | None) -> dict | None:
    """Pick the best TMDB hit for a scraped title. Article-insensitive
    ("Devil's Advocate" == "The Devil's Advocate"); among title matches, prefer
    a year match then popularity; else fall back to the most popular result."""
    qn = norm_title(title)
    matches: list[tuple[bool, float, dict]] = []
    for r in results:
        name = r.get("title") or r.get("name") or ""
        date = r.get("release_date") or r.get("first_air_date") or ""
        r_year = int(date[:4]) if date[:4].isdigit() else None
        if norm_title(name) == qn:
            matches.append((year is not None and r_year == year,
                            r.get("popularity", 0.0), r))
    if matches:
        matches.sort(key=lambda mrec: (not mrec[0], -mrec[1]))
        return matches[0][2]
    return results[0] if results else None


async def resolve_for_service(client: TMDBClient, results: list[dict], title: str,
                              year: int | None, source_key: str, country: str,
                              known_keys: set[str]) -> dict | None:
    """Service-aware resolution: a title from your Netflix list should match the
    TMDB entry that's actually ON Netflix. Disambiguates same-name films
    ("Ludo" 2020 Bollywood on Netflix vs a 2021 documentary) by checking each
    candidate's availability on the source service; falls back to resolve_best.

    A supplied year wins outright: when the caller knows the year, checking
    availability can only lose to it — two same-titled films can both be on
    Netflix, and popularity would then pick the wrong one.
    """
    qn = norm_title(title)
    matches = [r for r in results
               if norm_title(r.get("title") or r.get("name") or "") == qn]
    pool = matches or results
    if len(pool) <= 1:
        return pool[0] if pool else None

    if year is not None:
        exact = [r for r in pool
                 if ((r.get("release_date") or r.get("first_air_date") or "")[:4]
                     == str(year))]
        if len(exact) == 1:
            return exact[0]
        if exact:
            pool = exact  # narrow, then let the service check break the tie

    from app.services.catalog import _slugify, resolve_alias_key

    for cand in sorted(pool, key=lambda r: -(r.get("popularity") or 0.0))[:_SERVICE_CHECK_LIMIT]:
        try:
            regions = await client.watch_providers(cand["media_type"], cand["id"])
        except Exception:
            continue  # a provider lookup failing is not "not on this service"
        data = regions.get(country) or {}
        keys: set[str] = set()
        for field in ("flatrate", "free", "ads", "rent", "buy"):
            for p in data.get(field, []) or []:
                name = p.get("provider_name", "")
                keys.add(resolve_alias_key(name, known_keys) or _slugify(name))
        if source_key in keys:
            return cand
    return resolve_best(pool, title, year)
