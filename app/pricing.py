"""Known base-plan pricing — static, editable concierge data (M7).

Approximate entry-plan prices (US, ad-supported tier where that's the cheapest
way in). These drift as services change plans, so they're deliberately kept as a
plain, hand-maintained map here rather than fetched — edit freely. Shown with a
"~" prefix in the UI so it always reads as an estimate, never a quote.

Keyed by Service.key. Anything not listed simply shows no price.
"""

KNOWN_PRICING: dict[str, str] = {
    "netflix": "~$7.99/mo (ads)",
    "prime_video": "~$8.99/mo",
    "disney_plus": "~$9.99/mo (ads)",
    "hulu": "~$9.99/mo (ads)",
    "max": "~$9.99/mo (ads)",
    "peacock": "~$7.99/mo (ads)",
    "paramount_plus": "~$7.99/mo",
    "apple_tv_plus": "~$9.99/mo",
    "starz": "~$9.99/mo",
    "amc_plus": "~$8.99/mo",
    "crunchyroll": "~$7.99/mo",
    "showtime": "~$10.99/mo",
    "mgm_plus": "~$6.99/mo",
    "tubi": "Free (ads)",
    "pluto_tv": "Free (ads)",
    "the_roku_channel": "Free (ads)",
    "spotify": "~$11.99/mo",
    "youtube_premium": "~$13.99/mo",
    "apple_music": "~$10.99/mo",
}


def price_for(key: str) -> str | None:
    return KNOWN_PRICING.get(key)
