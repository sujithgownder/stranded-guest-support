"""Specialist support agents and safety-first ticket orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from .eligibility import calculate_uplift, qualifies_for_rebooking, select_comparable_listings
from .models import (
    AgentRole,
    OpenListing,
    PolicyViolationError,
    SafetyCondition,
    SupportTicket,
    TicketResolution,
    TicketType,
)
from .safety import classify_ticket
from .tools import PolicyToolGateway


@dataclass
class SafetyAgent:
    """Specialist agent permitted only to invoke handoff_to_safety_agent."""

    gateway: PolicyToolGateway
    role: AgentRole = AgentRole.SAFETY_AGENT

    def handle(
        self,
        ticket: SupportTicket,
        conditions: tuple[SafetyCondition, ...],
    ) -> TicketResolution:
        """Transfer the safety ticket to a live Trust and Safety agent."""
        self.gateway.handoff_to_safety_agent(self.role, ticket, conditions)
        return TicketResolution(
            ticket_id=ticket.ticket_id,
            reservation_id=ticket.reservation_id,
            ticket_type=TicketType.SAFETY,
            agent_role=self.role,
            tool_used="handoff_to_safety_agent",
            safety_conditions=conditions,
            handoff_completed=True,
        )


@dataclass
class RebookingAgent:
    """Specialist agent permitted to invoke hold_booking on comparable homes."""

    gateway: PolicyToolGateway
    role: AgentRole = AgentRole.REBOOKING_AGENT

    def handle(
        self,
        ticket: SupportTicket,
        open_listings: Sequence[OpenListing],
        *,
        excluded_listing_ids: frozenset[str] = frozenset(),
    ) -> TicketResolution:
        """Attempt to hold the best comparable open listing, or signal refund fallback."""
        if not qualifies_for_rebooking(ticket):
            raise PolicyViolationError(
                f"Ticket {ticket.ticket_id} does not qualify for rebooking support"
            )

        candidates = select_comparable_listings(
            ticket,
            open_listings,
            excluded_listing_ids=excluded_listing_ids,
        )
        for listing in candidates:
            uplift = calculate_uplift(ticket, listing)
            if self.gateway.ledger.uplift_spent + uplift <= self.gateway.ledger.total_uplift_budget:
                self.gateway.hold_booking(self.role, ticket, listing)
                return TicketResolution(
                    ticket_id=ticket.ticket_id,
                    reservation_id=ticket.reservation_id,
                    ticket_type=TicketType.REBOOKING,
                    agent_role=self.role,
                    tool_used="hold_booking",
                    listing_id=listing.listing_id,
                    uplift=uplift,
                )

        return TicketResolution(
            ticket_id=ticket.ticket_id,
            reservation_id=ticket.reservation_id,
            ticket_type=TicketType.REBOOKING,
            agent_role=self.role,
            tool_used="none",
            uplift=Decimal("0.00"),
            fallback_to_refund=True,
        )


@dataclass
class RefundAgent:
    """Specialist agent permitted to invoke issue_refund up to total_paid."""

    gateway: PolicyToolGateway
    role: AgentRole = AgentRole.REFUND_AGENT

    def handle(
        self,
        ticket: SupportTicket,
        *,
        amount: Decimal | None = None,
        ticket_type: TicketType = TicketType.REFUND,
        fallback_to_refund: bool = False,
    ) -> TicketResolution:
        """Issue a refund capped at total_paid and close the stay."""
        record = self.gateway.issue_refund(self.role, ticket, amount)
        return TicketResolution(
            ticket_id=ticket.ticket_id,
            reservation_id=ticket.reservation_id,
            ticket_type=ticket_type,
            agent_role=self.role,
            tool_used="issue_refund",
            refund_amount=record.refund_amount,
            fallback_to_refund=fallback_to_refund,
        )


@dataclass
class SupportTeamOrchestrator:
    """Routes stranded guest tickets with safety triage enforced before any action."""

    gateway: PolicyToolGateway = field(default_factory=PolicyToolGateway)
    safety_agent: SafetyAgent = field(init=False)
    rebooking_agent: RebookingAgent = field(init=False)
    refund_agent: RefundAgent = field(init=False)

    def __post_init__(self) -> None:
        self.safety_agent = SafetyAgent(gateway=self.gateway)
        self.rebooking_agent = RebookingAgent(gateway=self.gateway)
        self.refund_agent = RefundAgent(gateway=self.gateway)

    def handle_ticket(
        self,
        ticket: SupportTicket,
        open_listings: Sequence[OpenListing] = (),
        *,
        excluded_listing_ids: frozenset[str] = frozenset(),
        guest_declines_rebooking: bool = False,
    ) -> TicketResolution:
        """Triage a ticket and dispatch it to the responsible specialist agent."""
        ticket_type, safety_conditions = classify_ticket(ticket)
        if ticket_type == TicketType.SAFETY:
            self.gateway.register_safety_ticket(ticket.ticket_id)
            return self.safety_agent.handle(ticket, safety_conditions)

        if ticket_type == TicketType.REFUND:
            return self.refund_agent.handle(ticket, ticket_type=TicketType.REFUND)

        if guest_declines_rebooking:
            return self.refund_agent.handle(
                ticket,
                ticket_type=TicketType.REBOOKING,
                fallback_to_refund=True,
            )

        rebooking_resolution = self.rebooking_agent.handle(
            ticket,
            open_listings,
            excluded_listing_ids=excluded_listing_ids,
        )
        if rebooking_resolution.fallback_to_refund:
            return self.refund_agent.handle(
                ticket,
                ticket_type=TicketType.REBOOKING,
                fallback_to_refund=True,
            )
        return rebooking_resolution
