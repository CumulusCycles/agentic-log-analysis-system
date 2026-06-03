import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


# JSONB on Postgres (production), JSON on SQLite (tests). Same Python interface.
_JSONB = JSONB().with_variant(JSON(), "sqlite")

# BIGSERIAL on Postgres, INTEGER PRIMARY KEY (autoincrement) on SQLite.
_BIG_PK = BigInteger().with_variant(Integer(), "sqlite")

# Valid claim status enum per ADR-007.
CLAIM_STATUS_VALUES: tuple[str, ...] = (
    "submitted",
    "triaged",
    "investigating",
    "settled",
    "closed",
    "denied",
)
_STATUS_LIST_SQL = ", ".join(f"'{v}'" for v in CLAIM_STATUS_VALUES)

# Used as ``claim_status_history.actor_id`` when a transition has no assigned
# adjuster (e.g., the first transition of a freshly seeded `submitted` claim
# if agent seeding somehow failed). Surfaces in logs and the dashboard as a
# known non-human actor rather than a silent magic string. Lives on the data
# model so both the simulator (writer) and the consistency check (reader) can
# import it without creating a cross-package cycle.
SYSTEM_ACTOR_ID = "system"


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            f"current_status IN ({_STATUS_LIST_SQL})",
            name="claims_current_status_enum",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    policy_number: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[str] = mapped_column(Text, nullable=False)
    vin: Mapped[str] = mapped_column(Text, nullable=False)
    vehicle_snapshot: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    incident_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    current_status: Mapped[str] = mapped_column(Text, nullable=False, default="submitted")
    assigned_adjuster_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    history: Mapped[list["ClaimStatusHistory"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimStatusHistory(Base):
    __tablename__ = "claim_status_history"
    __table_args__ = (
        CheckConstraint(
            f"to_status IN ({_STATUS_LIST_SQL})",
            name="claim_status_history_to_status_enum",
        ),
        CheckConstraint(
            f"from_status IS NULL OR from_status IN ({_STATUS_LIST_SQL})",
            name="claim_status_history_from_status_enum",
        ),
    )

    id: Mapped[int] = mapped_column(_BIG_PK, primary_key=True, autoincrement=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    note: Mapped[str | None] = mapped_column(Text)

    claim: Mapped[Claim] = relationship(back_populates="history")
