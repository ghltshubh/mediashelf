"""Playback routing (M3).

The chain, per plan: Spotify SDK if Premium connected → MusicKit if configured
→ YouTube iframe (full track/video, free tier, ads) → Spotify embed (free
account, 30s preview — ranks BELOW YouTube) → deep-link to best service.
A Settings pin ("preferred music service") outranks the chain when that
service is playable. Dedupe never hides playback choice: every option is
returned so rows can expand to an explicit "play on…" list.

DRM stays structurally impossible: engines exist only for spotify / apple /
youtube payloads; every other service can only ever yield a deeplink option.
"""

import json

from sqlalchemy.orm import Session

from app import settings_store


def user_playback_state(db: Session) -> dict:
    profile = settings_store.get_setting(db, "spotify_profile")
    p = json.loads(profile) if profile else {}
    return {
        "spotify_connected": settings_store.get_setting(db, "spotify_oauth") is not None
        and settings_store.get_setting(db, "spotify_auth_error") != "true",
        "spotify_premium": p.get("product") == "premium",
        "apple_configured": settings_store.get_setting(db, "apple_developer_token") is not None,
        "preferred": settings_store.get_setting(db, "preferred_music_service") or "auto",
    }


def music_options(entity: dict, state: dict) -> dict:
    """entity: {spotify_id?, spotify_uri?, apple_id?, youtube_video_id?,
                links: [{service_key, service_name, url, owned}]}
    Returns {"options": [...], "default": option or None} — options ordered by
    the chain; default respects the preferred-service pin."""
    options: list[dict] = []

    spotify_id = entity.get("spotify_id")
    if spotify_id and state["spotify_connected"] and state["spotify_premium"]:
        options.append({"engine": "spotify_sdk", "service_key": "spotify",
                        "label": "Spotify", "kind": "full",
                        "payload": {"spotify_uri": entity.get("spotify_uri")
                                    or f"spotify:track:{spotify_id}"}})
    if entity.get("apple_id") and state["apple_configured"]:
        options.append({"engine": "musickit", "service_key": "apple_music",
                        "label": "Apple Music", "kind": "full",
                        "payload": {"apple_id": entity["apple_id"]}})
    if entity.get("youtube_video_id"):
        options.append({"engine": "youtube", "service_key": "youtube",
                        "label": "YouTube", "kind": "full · ads",
                        "payload": {"video_id": entity["youtube_video_id"]}})
    # Spotify free: official embed, 30s preview — below YouTube per plan.
    if spotify_id and not (state["spotify_connected"] and state["spotify_premium"]):
        options.append({"engine": "spotify_embed", "service_key": "spotify",
                        "label": "Spotify preview", "kind": "30s preview",
                        "payload": {"track_id": spotify_id}})
    # Deep links tail the chain — owned services first.
    links = sorted(entity.get("links", []), key=lambda ln: not ln.get("owned"))
    for link in links:
        if link.get("url"):
            options.append({"engine": "deeplink", "service_key": link["service_key"],
                            "label": link["service_name"], "kind": "open in app",
                            "payload": {"url": link["url"]}})

    default = None
    if options:
        preferred = state["preferred"]
        if preferred != "auto":
            default = next((o for o in options
                            if o["service_key"] == preferred and o["engine"] != "deeplink"), None)
        default = default or options[0]
    return {"options": options, "default": default}


def video_options(badges: list[dict]) -> dict:
    """Movies/TV: deep links only — DRM services never get an in-app engine."""
    ordered = sorted((b for b in badges if b.get("deep_link")),
                     key=lambda b: (not b["owned"],))
    options = [{"engine": "deeplink", "service_key": b["service_key"],
                "label": b["service_name"], "kind": b["offer_type"],
                "payload": {"url": b["deep_link"]}} for b in ordered]
    return {"options": options, "default": options[0] if options else None}
