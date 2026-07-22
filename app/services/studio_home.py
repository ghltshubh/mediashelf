"""Infer a *likely* streaming home for an upcoming title that has no confirmed
availability yet, from its TMDB studio (movies: ``production_companies``) or
network (TV: ``networks``).

This is a heuristic prediction, never confirmed data — the UI must label it
"expected on X", not present it as a real availability badge. Output deals are
US-oriented and shift over time, so it will sometimes be wrong.

Keyed by TMDB IDs. Company IDs (movies) and network IDs (TV) live in *separate*
namespaces, so they get separate maps — id 174 is Warner Bros. as a company but
a different entity as a network.
"""

# TMDB production-company id -> (service key, display name). Movies.
_COMPANY_HOME: dict[int, tuple[str, str]] = {
    # Disney family -> Disney+
    2: ("disney_plus", "Disney+"),        # Walt Disney Pictures
    3: ("disney_plus", "Disney+"),        # Pixar
    420: ("disney_plus", "Disney+"),      # Marvel Studios
    1: ("disney_plus", "Disney+"),        # Lucasfilm
    6125: ("disney_plus", "Disney+"),     # Walt Disney Animation Studios
    127928: ("disney_plus", "Disney+"),   # 20th Century Studios
    25: ("disney_plus", "Disney+"),       # 20th Century Fox
    # Universal family -> Peacock
    33: ("peacock", "Peacock"),           # Universal Pictures
    6704: ("peacock", "Peacock"),         # Illumination
    521: ("peacock", "Peacock"),          # DreamWorks Animation
    # Warner family -> Max
    174: ("max", "Max"),                  # Warner Bros. Pictures
    12: ("max", "Max"),                   # New Line Cinema
    # Paramount -> Paramount+
    4: ("paramount_plus", "Paramount+"),  # Paramount
    # Sony has no streamer of its own; its US pay-1 window goes to Netflix.
    5: ("netflix", "Netflix"),            # Columbia Pictures
    34: ("netflix", "Netflix"),           # Sony Pictures
    # Amazon / MGM -> Prime Video
    21: ("prime_video", "Prime Video"),   # Metro-Goldwyn-Mayer
    20580: ("prime_video", "Prime Video"),  # Amazon Studios
}

# TMDB network id -> (service key, display name). TV. Networks map very cleanly:
# a show's home network usually IS its streaming service.
_NETWORK_HOME: dict[int, tuple[str, str]] = {
    213: ("netflix", "Netflix"),
    49: ("max", "Max"),                   # HBO
    2739: ("disney_plus", "Disney+"),
    453: ("hulu", "Hulu"),
    2552: ("apple_tv_plus", "Apple TV+"),
    1024: ("prime_video", "Prime Video"),  # Amazon
    3353: ("peacock", "Peacock"),
    4330: ("paramount_plus", "Paramount+"),
}


def infer_expected(detail: dict, media_type: str) -> tuple[str, str] | None:
    """Return ``(service_key, service_name)`` for the likeliest streaming home,
    or ``None`` when no known studio/network matches. For TV the home network is
    checked first (most reliable), falling back to production companies for
    co-productions."""
    if media_type == "tv":
        for net in detail.get("networks") or []:
            hit = _NETWORK_HOME.get(net.get("id"))
            if hit:
                return hit
    for comp in detail.get("production_companies") or []:
        hit = _COMPANY_HOME.get(comp.get("id"))
        if hit:
            return hit
    return None
