"""Generic deep-link-only connector (netflix, hulu, prime, gaana, …).

Tier 3 services are data, not code (Appendix A): rows in the Service table.
This class exists so every service resolves to *some* connector; its
capabilities are honest — browse-and-link only, per the DRM hard constraint.
"""


class DeeplinkOnlyConnector:
    def __init__(self, key: str, name: str):
        self.key = key
        self.name = name

    def capabilities(self) -> dict:
        return {"catalog": False, "user_library": False, "write_likes": False,
                "write_follows": False, "playback": "deeplink"}
