"""SQLAlchemy models.

All entities from the plan are modeled from day one (M9's FeedSource/FeedItem included)
so later milestones never need destructive migrations.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Service(Base):
    """A streaming service. Tier 3 services are data, not code (Appendix A)."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16))  # video | music | meta | podcast
    tier: Mapped[int] = mapped_column(Integer, default=3)
    # Deep-link URL template; {query} is replaced with the URL-encoded title.
    # Fallback chain (plan: failure modes): template → search → homepage — all data, not code.
    deep_link_template: Mapped[str | None] = mapped_column(Text, default=None)
    homepage_url: Mapped[str | None] = mapped_column(Text, default=None)
    logo_url: Mapped[str | None] = mapped_column(Text, default=None)
    signup_url: Mapped[str | None] = mapped_column(Text, default=None)
    sso_note: Mapped[str | None] = mapped_column(String(128), default=None)
    # Capability flags drive the UI (plan: catalog/user_library/write_likes/write_follows/playback).
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    tmdb_provider_id: Mapped[int | None] = mapped_column(Integer, default=None, index=True)
    auto_added: Mapped[bool] = mapped_column(Boolean, default=False)
    # User-created service (M1 custom services): joins the checklist and lit/dimmed
    # treatment, opens via homepage_url, carries no per-title availability.
    custom: Mapped[bool] = mapped_column(Boolean, default=False)

    subscription: Mapped["UserSub | None"] = relationship(back_populates="service", uselist=False)


class UserSub(Base):
    """The subscription checklist — user declares what they pay for, no logins needed."""

    __tablename__ = "user_subs"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), unique=True)
    subscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    service: Mapped[Service] = relationship(back_populates="subscription")


class MediaItem(Base):
    __tablename__ = "media_items"
    __table_args__ = (UniqueConstraint("media_type", "tmdb_id", name="uq_media_tmdb"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    media_type: Mapped[str] = mapped_column(String(16), index=True)  # movie | tv | track | album | artist
    tmdb_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    # Music entity resolution keys (M4) — nullable from day one.
    isrc: Mapped[str | None] = mapped_column(String(32), index=True, default=None)
    upc: Mapped[str | None] = mapped_column(String(32), index=True, default=None)
    title: Mapped[str] = mapped_column(String(512))
    year: Mapped[int | None] = mapped_column(Integer, default=None)
    overview: Mapped[str | None] = mapped_column(Text, default=None)
    poster_path: Mapped[str | None] = mapped_column(String(256), default=None)
    backdrop_path: Mapped[str | None] = mapped_column(String(256), default=None)
    genres: Mapped[list] = mapped_column(JSON, default=list)
    popularity: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[float | None] = mapped_column(Float, default=None)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, default=None)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    availabilities: Mapped[list["Availability"]] = relationship(
        back_populates="media_item", cascade="all, delete-orphan"
    )


class Availability(Base):
    __tablename__ = "availabilities"
    __table_args__ = (
        UniqueConstraint("media_item_id", "service_id", "country", "offer_type", name="uq_avail"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    media_item_id: Mapped[int] = mapped_column(ForeignKey("media_items.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    offer_type: Mapped[str] = mapped_column(String(16))  # flatrate | rent | buy | free | ads
    price: Mapped[str | None] = mapped_column(String(32), default=None)
    # TMDB's aggregated watch page for this title — fallback link when a service
    # has no deep-link template.
    tmdb_link: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    media_item: Mapped[MediaItem] = relationship(back_populates="availabilities")
    service: Mapped[Service] = relationship()


class LibraryEntry(Base):
    """Synced likes/subs/watchlist entries (M3+); modeled now."""

    __tablename__ = "library_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    media_item_id: Mapped[int | None] = mapped_column(ForeignKey("media_items.id"), default=None)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), default=None)
    entry_type: Mapped[str] = mapped_column(String(32))  # like | follow | subscription | watchlist
    external_id: Mapped[str | None] = mapped_column(String(256), default=None)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MigrationJob(Base):
    """Resumable migration state machine (M5); modeled now."""

    __tablename__ = "migration_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), default=None)
    target_service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), default=None)
    # pending → matching → review → writing → paused_quota → done
    status: Mapped[str] = mapped_column(String(24), default="pending")
    scope: Mapped[dict] = mapped_column(JSON, default=dict)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    log: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MatchCandidate(Base):
    """Below-threshold matches for the manual review queue (M4); modeled now."""

    __tablename__ = "match_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("migration_jobs.id"), default=None)
    source_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    candidate_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # pending | approved | skipped | replaced
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Setting(Base):
    """Key/value config. Secret values are encrypted at rest (see app/secrets.py)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, default=None)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FeedSource(Base):
    """Pulse feed source (M9); modeled from day one per plan."""

    __tablename__ = "feed_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))  # bluesky | mastodon | reddit | youtube_rss | rss
    label: Mapped[str] = mapped_column(String(256))
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedItem(Base):
    __tablename__ = "feed_items"
    __table_args__ = (UniqueConstraint("source_id", "external_id", name="uq_feed_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("feed_sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(512))
    author: Mapped[str | None] = mapped_column(String(256), default=None)
    body: Mapped[str | None] = mapped_column(Text, default=None)
    url: Mapped[str | None] = mapped_column(Text, default=None)
    media_item_id: Mapped[int | None] = mapped_column(ForeignKey("media_items.id"), default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
