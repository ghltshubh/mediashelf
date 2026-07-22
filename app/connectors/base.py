"""ConnectorProtocol — per-service adapters (plan architecture).

M3 implements OAuth + read paths (read_likes / read_follows). Write paths
(add_like / follow) belong to M5's migration engine and raise until then.
Capability flags drive the UI: a connector only ever advertises what it can do.
"""

from typing import Any, Protocol, runtime_checkable

from sqlalchemy.orm import Session


class AuthExpired(Exception):
    """Token expired/revoked. Never surfaces as a raw error: the connection
    card and affected surfaces show 'Reconnect <service>' (plan failure modes)."""

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"{provider} authorization expired")


class NotConnected(Exception):
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"{provider} is not connected")


class QuotaExhausted(Exception):
    """Daily API quota hit. Never an error state: jobs persist progress, pause
    cleanly as `paused_quota`, and resume after the provider's reset."""

    def __init__(self, provider: str, detail: str = ""):
        self.provider = provider
        self.detail = detail
        super().__init__(f"{provider} quota exhausted {detail}".strip())


@runtime_checkable
class ConnectorProtocol(Protocol):
    key: str
    name: str

    def capabilities(self) -> dict: ...
    def configured(self, db: Session) -> bool: ...        # app credentials present
    def connected(self, db: Session) -> bool: ...         # user tokens present
    def auth_url(self, db: Session, state: str, redirect_uri: str) -> str: ...
    def handle_callback(self, db: Session, code: str, redirect_uri: str) -> None: ...
    def disconnect(self, db: Session) -> None: ...
    def status(self, db: Session) -> dict: ...
    def read_likes(self, db: Session) -> list[dict[str, Any]]: ...
    def read_follows(self, db: Session) -> list[dict[str, Any]]: ...
    # M5 (migrations): search_track(), add_like(), follow()
