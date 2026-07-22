"""Cross-service track matching (M4).

Resolution order per plan: ISRC exact → UPC (albums) → fuzzy fallback
(normalized artist+title, duration ±3s) emitting a confidence score.

Confidence contract:
- >= AUTO_THRESHOLD  → safe to write automatically ("matched")
- REVIEW_THRESHOLD.. → a MatchCandidate for the manual queue ("review")
- below              → no plausible match ("none")

Ambiguity NEVER auto-writes: version variants (live/remix/acoustic/…) on one
side only are penalized below the auto threshold by construction. Remasters
and deluxe/edition tags are the same recording — stripped, no penalty.

Pure module: no DB, no HTTP. M5's migration runner and the review API consume it.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

AUTO_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.50

# Same-recording decorations — safe to strip entirely.
_IGNORABLE = re.compile(
    r"""
    [\(\[\-–]\s*
    (
        (\d{4}\s*)?remaster(ed)?(\s*\d{4})?(\s*version)?
      | deluxe(\s+edition)?
      | expanded(\s+edition)?
      | special(\s+edition)?
      | anniversary(\s+edition)?
      | bonus\s+track(\s+version)?
      | single\s+version
      | album\s+version
      | radio\s+edit
      | mono | stereo
    )
    \s*[\)\]]?\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Different-recording variants — flags that must agree on both sides.
_VARIANTS = {
    "live": re.compile(r"\b(live|en vivo|in concert)\b", re.IGNORECASE),
    "acoustic": re.compile(r"\bacoustic\b", re.IGNORECASE),
    "remix": re.compile(r"\b(remix|rmx|mix\b(?!tape))\b", re.IGNORECASE),
    "instrumental": re.compile(r"\binstrumental\b", re.IGNORECASE),
    "demo": re.compile(r"\bdemo\b", re.IGNORECASE),
    "karaoke": re.compile(r"\bkaraoke\b", re.IGNORECASE),
    "cover": re.compile(r"\bcover\b", re.IGNORECASE),
}

_FEAT = re.compile(
    r"[\(\[]?\s*(?:feat\.?|featuring|ft\.?|with)\s+([^)\]]+)[\)\]]?\s*$",
    re.IGNORECASE,
)


@dataclass
class TrackRef:
    title: str
    artists: list[str] = field(default_factory=list)
    duration_ms: int | None = None
    isrc: str | None = None
    upc: str | None = None
    album: str | None = None
    external_id: str | None = None
    payload: dict = field(default_factory=dict)


@dataclass
class MatchResult:
    status: str                  # matched | review | none
    candidate: TrackRef | None
    confidence: float
    method: str                  # isrc | upc | fuzzy | none


def _ascii_fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _ascii_fold(s).lower()).strip()


def parse_title(title: str) -> tuple[str, list[str], frozenset[str]]:
    """→ (normalized base title, feat-artists lifted out, variant flags)."""
    work = title
    feat_artists: list[str] = []
    m = _FEAT.search(work)
    if m:
        feat_artists = [a.strip() for a in re.split(r",|&| and ", m.group(1)) if a.strip()]
        work = work[: m.start()].strip()

    flags = frozenset(name for name, rx in _VARIANTS.items() if rx.search(work))

    prev = None
    while prev != work:  # strip stacked decorations: "X (Deluxe) - 2011 Remaster"
        prev = work
        work = _IGNORABLE.sub("", work).strip()
    # Drop remaining parenthetical/bracket/dash tails that carried variant info.
    work = re.sub(r"\s*[\(\[][^)\]]*[\)\]]\s*$", "", work).strip()
    work = re.sub(r"\s*[-–]\s*(live|acoustic|remix|instrumental|demo)\b.*$", "", work,
                  flags=re.IGNORECASE).strip()
    return _norm(work) or _norm(title), feat_artists, flags


def _artist_set(ref: TrackRef, feat_from_title: list[str]) -> set[str]:
    return {_norm(a) for a in [*ref.artists, *feat_from_title] if _norm(a)}


def _title_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _artist_score(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.5  # unknown — neutral, never a boost
    if a & b:
        return len(a & b) / len(a | b) * 0.5 + 0.5  # any shared artist is strong signal
    # No exact overlap: allow fuzzy primary-artist match ("Beyonce" vs "Beyoncé" folds earlier).
    best = max(SequenceMatcher(None, x, y).ratio() for x in a for y in b)
    return best * 0.6


def _duration_score(a: int | None, b: int | None) -> float:
    if a is None or b is None:
        return 0.6  # unknown — mildly neutral
    delta = abs(a - b)
    if delta <= 3000:      # plan: ±3s
        return 1.0
    if delta <= 10000:
        return 0.4
    return 0.0


def score(source: TrackRef, candidate: TrackRef) -> float:
    """Fuzzy confidence 0..1."""
    s_title, s_feat, s_flags = parse_title(source.title)
    c_title, c_feat, c_flags = parse_title(candidate.title)
    conf = (
        0.50 * _title_score(s_title, c_title)
        + 0.35 * _artist_score(_artist_set(source, s_feat), _artist_set(candidate, c_feat))
        + 0.15 * _duration_score(source.duration_ms, candidate.duration_ms)
    )
    if s_flags != c_flags:
        # A live/remix/acoustic on one side only is a different recording:
        # cap far below AUTO so it can only ever reach the review queue.
        conf *= 0.55
    if (source.duration_ms is not None and candidate.duration_ms is not None
            and abs(source.duration_ms - candidate.duration_ms) > 10000):
        # >10s apart is a different edit even when the names agree perfectly
        # ("Echoes" 3:20 radio edit vs 23:30 album cut) — review, never auto.
        conf = min(conf, AUTO_THRESHOLD - 0.05)
    return round(conf, 4)


def best_match(source: TrackRef, candidates: list[TrackRef]) -> MatchResult:
    if not candidates:
        return MatchResult("none", None, 0.0, "none")

    if source.isrc:
        for c in candidates:
            if c.isrc and c.isrc.strip().upper() == source.isrc.strip().upper():
                return MatchResult("matched", c, 1.0, "isrc")

    if source.upc:
        for c in candidates:
            if c.upc and c.upc.strip() == source.upc.strip():
                return MatchResult("matched", c, 1.0, "upc")

    scored = sorted(((score(source, c), c) for c in candidates), key=lambda t: -t[0])
    conf, best = scored[0]
    if conf >= AUTO_THRESHOLD:
        return MatchResult("matched", best, conf, "fuzzy")
    if conf >= REVIEW_THRESHOLD:
        return MatchResult("review", best, conf, "fuzzy")
    return MatchResult("none", None, conf, "none")
