"""Policy-guarded tool execution gateway for specialist support agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .eligibility import calculate_uplift, is_comparable_home, qualifies_for_rebooking
from .models import (
    AgentRole,
    IncidentLedger,
    ListingStatus,
    OpenListing,
    PolicyViolationError,
    SafetyCondition,
    SafetyHandoffRequiredError,
    SupportTicket,
    ToolCallRecord,
    UnauthorizedToolError,
)

ROLE_PERMITTED_TOOL: dict[AgentRole, str] = {
    AgentRole.REBOOKING_AGENT: "hold_booking",
    AgentRole.REFUND_AGENT: "issue_refund",
    AgentRole.SAFETY_AGENT: "handoff_to_safety_agent",
}


@dataclass
class PolicyToolGateway:
    """Enforces specialist agent permissions, safety locks, and financial bounds."""

    ledger: IncidentLedger = field(default_factory=IncidentLedger)
    safety_ticket_ids: set[str] = field(default_factory=set)

    def register_safety_ticket(self, ticket_id: str) -> None:
        """Mark a ticket as requiring safety hand-off before any booking or refund."""
        self.safety_ticket_ids.add(ticket_id)

    def _record(self, record: ToolCallRecord) -> ToolCallRecord:
        self.ledger.tool_calls.append(record)
        return record

    def _reject(
        self,
        *,
        ticket: SupportTicket,
        agent_role: AgentRole,
        tool_name: str,
        reason: str,
        error_cls: type[PolicyViolationError],
        listing_id: str | None = None,
        refund_amount: Decimal | None = None,
        safety_conditions: tuple[SafetyCondition, ...] = (),
    ) -> None:
        self._record(
            ToolCallRecord(
                ticket_id=ticket.ticket_id,
                reservation_id=ticket.reservation_id,
                agent_role=agent_role,
                tool_name=tool_name,
                allowed=False,
                listing_id=listing_id,
                refund_amount=refund_amount,
                safety_conditions=safety_conditions,
                rejection_reason=reason,
            )
        )
        raise error_cls(reason)

    def _require_role(
        self,
        agent_role: AgentRole,
        expected_role: AgentRole,
        tool_name: str,
        ticket: SupportTicket,
        *,
        listing_id: str | None = None,
        refund_amount: Decimal | None = None,
        safety_conditions: tuple[SafetyCondition, ...] = (),
    ) -> None:
        if agent_role != expected_role:
            reason = (
                f"Agent role '{agent_role.value}' is not permitted to invoke '{tool_name}'; "
                f"permitted tool is '{ROLE_PERMITTED_TOOL[agent_role]}'"
            )
            self._reject(
                ticket=ticket,
                agent_role=agent_role,
                tool_name=tool_name,
                reason=reason,
                error_cls=UnauthorizedToolError,
                listing_id=listing_id,
                refund_amount=refund_amount,
                safety_conditions=safety_conditions,
            )

    def _require_safety_clearance(
        self,
        agent_role: AgentRole,
        tool_name: str,
        ticket: SupportTicket,
        *,
        listing_id: str | None = None,
        refund_amount: Decimal | None = None,
    ) -> None:
        if (
            ticket.ticket_id in self.safety_ticket_ids
            and ticket.ticket_id not in self.ledger.safety_handoffs_completed
        ):
            reason = (
                f"Safety ticket {ticket.ticket_id} requires handoff_to_safety_agent "
                f"before calling '{tool_name}'"
            )
            self._reject(
                ticket=ticket,
                agent_role=agent_role,
                tool_name=tool_name,
                reason=reason,
                error_cls=SafetyHandoffRequiredError,
                listing_id=listing_id,
                refund_amount=refund_amount,
            )

    def _require_single_remedy(
        self,
        agent_role: AgentRole,
        tool_name: str,
        ticket: SupportTicket,
        *,
        listing_id: str | None = None,
        refund_amount: Decimal | None = None,
    ) -> None:
        existing = self.ledger.remedies_by_reservation.get(ticket.reservation_id)
        if existing is not None:
            reason = (
                f"Reservation {ticket.reservation_id} already has remedy '{existing}'; "
                "one remedy per stay policy forbids combining actions"
            )
            self._reject(
                ticket=ticket,
                agent_role=agent_role,
                tool_name=tool_name,
                reason=reason,
                error_cls=PolicyViolationError,
                listing_id=listing_id,
                refund_amount=refund_amount,
            )

    def handoff_to_safety_agent(
        self,
        agent_role: AgentRole,
        ticket: SupportTicket,
        conditions: tuple[SafetyCondition, ...],
    ) -> ToolCallRecord:
        """Hand off a safety ticket to a live Trust and Safety agent."""
        self._require_role(
            agent_role,
            AgentRole.SAFETY_AGENT,
            "handoff_to_safety_agent",
            ticket,
            safety_conditions=conditions,
        )
        if not conditions:
            self._reject(
                ticket=ticket,
                agent_role=agent_role,
                tool_name="handoff_to_safety_agent",
                reason=f"Safety hand-off for {ticket.ticket_id} requires at least one safety condition",
                error_cls=PolicyViolationError,
            )

        self.register_safety_ticket(ticket.ticket_id)
        self.ledger.safety_handoffs_completed.add(ticket.ticket_id)
        self.ledger.remedies_by_reservation[ticket.reservation_id] = "safety_handoff"
        return self._record(
            ToolCallRecord(
                ticket_id=ticket.ticket_id,
                reservation_id=ticket.reservation_id,
                agent_role=agent_role,
                tool_name="handoff_to_safety_agent",
                allowed=True,
                safety_conditions=conditions,
            )
        )

    def hold_booking(
        self,
        agent_role: AgentRole,
        ticket: SupportTicket,
        listing: OpenListing,
    ) -> ToolCallRecord:
        """Hold a comparable open listing for a qualifying guest."""
        self._require_role(
            agent_role,
            AgentRole.REBOOKING_AGENT,
            "hold_booking",
            ticket,
            listing_id=listing.listing_id,
        )
        self._require_safety_clearance(
            agent_role,
            "hold_booking",
            ticket,
            listing_id=listing.listing_id,
        )
        self._require_single_remedy(
            agent_role,
            "hold_booking",
            ticket,
            listing_id=listing.listing_id,
        )
        if not qualifies_for_rebooking(ticket):
            self._reject(
                ticket=ticket,
                agent_role=agent_role,
                tool_name="hold_booking",
                reason=f"Ticket {ticket.ticket_id} does not meet locked-out qualifying conditions",
                error_cls=PolicyViolationError,
                listing_id=listing.listing_id,
            )
        if not is_comparable_home(ticket, listing):
            self._reject(
                ticket=ticket,
                agent_role=agent_role,
                tool_name="hold_booking",
                reason=(
                    f"Listing {listing.listing_id} fails comparable-home policy tests "
                    f"(max nightly ceiling EUR {ticket.max_rebook_nightly_price})"
                ),
                error_cls=PolicyViolationError,
                listing_id=listing.listing_id,
            )

        uplift = calculate_uplift(ticket, listing)
        if self.ledger.uplift_spent + uplift > self.ledger.total_uplift_budget:
            self._reject(
                ticket=ticket,
                agent_role=agent_role,
                tool_name="hold_booking",
                reason=(
                    f"Hold uplift EUR {uplift} exceeds remaining incident budget "
                    f"(spent EUR {self.ledger.uplift_spent} / EUR {self.ledger.total_uplift_budget})"
                ),
                error_cls=PolicyViolationError,
                listing_id=listing.listing_id,
            )

        listing.status = ListingStatus.ON_HOLD
        self.ledger.uplift_spent += uplift
        self.ledger.remedies_by_reservation[ticket.reservation_id] = "rebooking"
        return self._record(
            ToolCallRecord(
                ticket_id=ticket.ticket_id,
                reservation_id=ticket.reservation_id,
                agent_role=agent_role,
                tool_name="hold_booking",
                allowed=True,
                listing_id=listing.listing_id,
            )
        )

    def issue_refund(
        self,
        agent_role: AgentRole,
        ticket: SupportTicket,
        amount: Decimal | None = None,
    ) -> ToolCallRecord:
        """Issue a policy-capped refund up to total_paid."""
        effective_amount = (
            ticket.total_paid if amount is None else amount.quantize(Decimal("0.01"))
        )
        self._require_role(
            agent_role,
            AgentRole.REFUND_AGENT,
            "issue_refund",
            ticket,
            refund_amount=effective_amount,
        )
        self._require_safety_clearance(
            agent_role,
            "issue_refund",
            ticket,
            refund_amount=effective_amount,
        )
        self._require_single_remedy(
            agent_role,
            "issue_refund",
            ticket,
            refund_amount=effective_amount,
        )
        if effective_amount < Decimal("0.01") or effective_amount > ticket.total_paid:
            self._reject(
                ticket=ticket,
                agent_role=agent_role,
                tool_name="issue_refund",
                reason=(
                    f"Refund amount EUR {effective_amount} is outside allowed policy bounds "
                    f"[EUR 0.01, EUR {ticket.total_paid}]"
                ),
                error_cls=PolicyViolationError,
                refund_amount=effective_amount,
            )

        self.ledger.remedies_by_reservation[ticket.reservation_id] = "refund"
        return self._record(
            ToolCallRecord(
                ticket_id=ticket.ticket_id,
                reservation_id=ticket.reservation_id,
                agent_role=agent_role,
                tool_name="issue_refund",
                allowed=True,
                refund_amount=effective_amount,
            )
        )
