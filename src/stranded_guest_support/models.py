"""Domain models, enumerations, and policy exceptions for stranded guest support."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

TWO_PLACES = Decimal("0.01")
REBOOK_PRICE_MULTIPLIER = Decimal("1.20")
DEFAULT_UPLIFT_BUDGET = Decimal("9000.00")


class TicketType(str, Enum):
    """Supported incident ticket classifications."""

    REBOOKING = "rebooking"
    REFUND = "refund"
    SAFETY = "safety"


class SafetyCondition(str, Enum):
    """Five AirCover safety conditions triggering mandatory live hand-off."""

    INJURY_OR_MEDICAL_NEED = "injury_or_medical_need"
    THREAT_OR_VIOLENCE = "threat_or_violence"
    NOWHERE_SAFE_TO_WAIT = "nowhere_safe_to_wait"
    UNACCOMPANIED_MINOR = "unaccompanied_minor"
    STATED_FEAR_OF_PERSON = "stated_fear_of_person"


class AgentRole(str, Enum):
    """Specialist agent roles with strict tool permissions."""

    REBOOKING_AGENT = "rebooking_agent"
    REFUND_AGENT = "refund_agent"
    SAFETY_AGENT = "safety_agent"


class ListingStatus(str, Enum):
    """Availability status of an open Lisbon listing."""

    AVAILABLE = "available"
    ON_HOLD = "on_hold"
    BOOKED = "booked"


class PolicyViolationError(ValueError):
    """Raised when an action violates AirCover rebooking, refund, or stay rules."""


class UnauthorizedToolError(PolicyViolationError):
    """Raised when an agent attempts to invoke a tool outside its specialist role."""


class SafetyHandoffRequiredError(PolicyViolationError):
    """Raised when booking or refund is attempted on a safety ticket before hand-off."""


@dataclass(frozen=True)
class SupportTicket:
    """Stranded guest incident ticket."""

    ticket_id: str
    opened_at: datetime
    reservation_id: str
    guest_name: str
    guest_language: str
    original_listing_id: str
    original_listing_title: str
    neighborhood: str
    property_type: str
    bedrooms: int
    party_size: int
    check_in_date: date
    check_out_date: date
    nightly_price: Decimal
    total_paid: Decimal
    host_id: str
    host_cancelled_at: datetime | None
    host_last_reply_at: datetime | None
    guest_requested: str
    guest_message: str
    expected_outcome: str | None = None

    def __post_init__(self) -> None:
        if not self.ticket_id or not self.reservation_id or not self.guest_name:
            raise ValueError("ticket_id, reservation_id, and guest_name are required")
        if self.bedrooms < 0:
            raise ValueError("bedrooms must be >= 0")
        if self.party_size < 1:
            raise ValueError("party_size must be >= 1")
        if self.check_out_date <= self.check_in_date:
            raise ValueError("check_out_date must be after check_in_date")
        if self.nightly_price <= Decimal("0.00"):
            raise ValueError("nightly_price must be > 0")
        if self.total_paid <= Decimal("0.00"):
            raise ValueError("total_paid must be > 0")

    @property
    def nights(self) -> int:
        """Total nights in the reservation stay."""
        return (self.check_out_date - self.check_in_date).days

    @property
    def max_rebook_nightly_price(self) -> Decimal:
        """Maximum permitted nightly rate (120% of original nightly_price)."""
        return (self.nightly_price * REBOOK_PRICE_MULTIPLIER).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )


@dataclass
class OpenListing:
    """Candidate open Lisbon listing for comparable-home rebooking."""

    listing_id: str
    neighborhood: str
    bedrooms: int
    max_guests: int
    available_from: date
    available_to: date
    nightly_price: Decimal
    status: ListingStatus
    property_type: str = ""
    host_id: str = ""
    title: str = ""
    instant_book: bool = False
    rating: Decimal | None = None

    def __post_init__(self) -> None:
        if self.bedrooms < 0:
            raise ValueError("bedrooms must be >= 0")
        if self.max_guests < 1:
            raise ValueError("max_guests must be >= 1")
        if self.available_to < self.available_from:
            raise ValueError("available_to must be >= available_from")
        if self.nightly_price <= Decimal("0.00"):
            raise ValueError("nightly_price must be > 0")


@dataclass(frozen=True)
class ToolCallRecord:
    """Immutable audit log entry for every permitted or blocked tool call."""

    ticket_id: str
    reservation_id: str
    agent_role: AgentRole
    tool_name: str
    allowed: bool
    listing_id: str | None = None
    refund_amount: Decimal | None = None
    safety_conditions: tuple[SafetyCondition, ...] = ()
    rejection_reason: str | None = None


@dataclass
class IncidentLedger:
    """Tracks stay-level remedies, safety hand-offs, uplift budget, and audit calls."""

    remedies_by_reservation: dict[str, str] = field(default_factory=dict)
    total_uplift_budget: Decimal = DEFAULT_UPLIFT_BUDGET
    uplift_spent: Decimal = Decimal("0.00")
    safety_handoffs_completed: set[str] = field(default_factory=set)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


@dataclass(frozen=True)
class TicketResolution:
    """Outcome produced for a processed support ticket."""

    ticket_id: str
    reservation_id: str
    ticket_type: TicketType
    agent_role: AgentRole
    tool_used: str
    safety_conditions: tuple[SafetyCondition, ...] = ()
    listing_id: str | None = None
    refund_amount: Decimal | None = None
    uplift: Decimal = Decimal("0.00")
    handoff_completed: bool = False
    fallback_to_refund: bool = False
