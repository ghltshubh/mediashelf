"""M4 fixture suite. Acceptance: ≥95% precision on the exact-ISRC set;
ambiguous fixtures land in review, never auto-write."""

from app.services.matching import (
    AUTO_THRESHOLD,
    MatchResult,
    TrackRef,
    best_match,
    parse_title,
    score,
)


def t(title, artists, dur=None, isrc=None, ext=None):
    return TrackRef(title=title, artists=artists, duration_ms=dur, isrc=isrc, external_id=ext)


# ---------- exact-ISRC set (20 fixtures — precision must be 100%) ----------

ISRC_SET = [
    (t(f"Song {i}", [f"Artist {i}"], 200000 + i, isrc=f"USRC17{i:05d}"),
     [t(f"Totally Different {i}", ["Someone Else"], 180000, isrc=f"USRC99{i:05d}", ext="wrong"),
      t(f"Song {i} (Remastered)", [f"Artist {i}"], 200000 + i, isrc=f"USRC17{i:05d}", ext="right")])
    for i in range(20)
]


def test_isrc_set_precision():
    correct = 0
    for source, candidates in ISRC_SET:
        r = best_match(source, candidates)
        if r.status == "matched" and r.method == "isrc" and r.candidate.external_id == "right":
            correct += 1
    precision = correct / len(ISRC_SET)
    assert precision >= 0.95  # acceptance floor; engine achieves 1.0
    assert precision == 1.0


def test_isrc_case_insensitive():
    r = best_match(t("X", ["A"], isrc="usrc17607839"),
                   [t("Y", ["B"], isrc="USRC17607839", ext="right")])
    assert r.status == "matched" and r.method == "isrc"


def test_upc_album_match():
    source = TrackRef(title="Blue Train", artists=["John Coltrane"], upc="0025218603')")
    cand = TrackRef(title="Blue Train (Expanded Edition)", artists=["John Coltrane"],
                    upc="0025218603')", external_id="right")
    r = best_match(source, [cand, TrackRef(title="Blue Train", artists=["X"], upc="999")])
    assert r.status == "matched" and r.method == "upc"


# ---------- remasters: same recording, must auto-match ----------

def test_remaster_variants_auto_match():
    pairs = [
        ("Africa", "Africa - 2018 Remaster"),
        ("Bohemian Rhapsody", "Bohemian Rhapsody (2011 Remaster)"),
        ("Time", "Time - Remastered 2011"),
        ("So What", "So What (Stereo)"),
        ("Hey Jude", "Hey Jude (Anniversary Edition)"),
    ]
    for a, b in pairs:
        r = best_match(t(a, ["The Band"], 240000), [t(b, ["The Band"], 241000, ext="right")])
        assert r.status == "matched", (a, b, r.confidence)


# ---------- live versions: different recording, NEVER auto ----------

def test_live_version_queues_never_auto():
    source = t("Comfortably Numb", ["Pink Floyd"], 384000)
    live_only = [t("Comfortably Numb - Live at Pompeii", ["Pink Floyd"], 540000)]
    r = best_match(source, live_only)
    assert r.status != "matched"

    # And when both studio and live exist, studio wins.
    both = [t("Comfortably Numb (Live)", ["Pink Floyd"], 540000, ext="live"),
            t("Comfortably Numb", ["Pink Floyd"], 383000, ext="studio")]
    r = best_match(source, both)
    assert r.status == "matched" and r.candidate.external_id == "studio"


def test_remix_and_acoustic_queue():
    for variant in ("Halo (Remix)", "Halo - Acoustic", "Halo (Instrumental)"):
        r = best_match(t("Halo", ["Beyoncé"], 261000),
                       [t(variant, ["Beyoncé"], 261000)])
        assert r.status != "matched", variant


def test_matching_live_flags_on_both_sides_ok():
    r = best_match(t("One More Time (Live)", ["Daft Punk"], 315000),
                   [t("One More Time - Live", ["Daft Punk"], 316000, ext="right")])
    assert r.status == "matched"


# ---------- feat.-artist formatting ----------

def test_feat_in_title_vs_artist_list():
    source = t("All The Stars (with SZA)", ["Kendrick Lamar"], 232000)
    cand = t("All The Stars", ["Kendrick Lamar", "SZA"], 232000, ext="right")
    r = best_match(source, [cand])
    assert r.status == "matched"

    source = t("Ride (feat. Lil Baby)", ["Twenty One Pilots"], 214000)
    cand = t("Ride", ["Twenty One Pilots", "Lil Baby"], 214500, ext="right")
    assert best_match(source, [cand]).status == "matched"


def test_accent_folding():
    r = best_match(t("Beyoncé", ["Beyoncé"], 200000), [t("Beyonce", ["Beyonce"], 200000)])
    assert r.status == "matched"


# ---------- duration mismatches ----------

def test_duration_within_3s_matches():
    r = best_match(t("Yellow", ["Coldplay"], 266000), [t("Yellow", ["Coldplay"], 268500)])
    assert r.status == "matched"


def test_big_duration_gap_queues():
    # Same name, same artist, radically different length: extended cut or a
    # different piece — must go to review, never auto.
    r = best_match(t("Echoes", ["Pink Floyd"], 200000), [t("Echoes", ["Pink Floyd"], 1410000)])
    assert r.status == "review"
    assert r.confidence < AUTO_THRESHOLD


# ---------- wrong candidates / none ----------

def test_wrong_song_never_matches():
    r = best_match(t("Karma Police", ["Radiohead"], 264000),
                   [t("Creep", ["Radiohead"], 238000)])
    assert r.status != "matched"


def test_empty_candidates():
    assert best_match(t("X", ["A"]), []).status == "none"


def test_unknown_durations_still_match_on_strong_title_artist():
    r = best_match(t("Nightcall", ["Kavinsky"]), [t("Nightcall", ["Kavinsky"], ext="right")])
    assert r.status == "matched"


# ---------- normalization unit checks ----------

def test_parse_title():
    base, feat, flags = parse_title("Uptown Funk (feat. Bruno Mars)")
    assert base == "uptown funk" and feat == ["Bruno Mars"] and not flags
    base, _, flags = parse_title("Smells Like Teen Spirit - Live at Reading")
    assert base == "smells like teen spirit" and "live" in flags
    base, _, flags = parse_title("Dreams - 2004 Remaster")
    assert base == "dreams" and not flags


def test_confidence_is_symmetricish_and_bounded():
    a, b = t("Song A", ["X"], 200000), t("Song B", ["Y"], 500000)
    assert 0.0 <= score(a, b) <= 1.0
    assert isinstance(best_match(a, [b]), MatchResult)
