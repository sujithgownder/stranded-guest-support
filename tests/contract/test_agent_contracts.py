"""Contract tests for specialist agent role isolation and tool enforcement."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from stranded_guest_support.agents import RefundAgent, SafetyAgent, SupportTeamOrchestrator
from stranded_guest_support.models import (
    AgentRole,
    ListingStatus,
    OpenListing,
    SafetyCondition,
    SupportTicket,
    TicketType,
    UnauthorizedToolError,
)
from stranded_guest_support.tools import PolicyToolGateway


def make_safety_ticket(guest_requested: str = "refund") -> SupportTicket:
    return SupportTicket(
        ticket_id="LIS-TKT-0034",
        opened_at=datetime(2026, 11, 16, 16, 29, tzinfo=timezone.utc),
        reservation_id="RES-2026-10034",
        guest_name="Natalia Kowalczyk",
        guest_language="en",
        original_listing_id="LST-200034",
        original_listing_title="Alcantara Bridge View 1-Bed",
        neighborhood="Alcantara",
        property_type="Entire apartment",
        bedrooms=1,
        party_size=1,
        check_in_date=date(2026, 11, 16),
        check_out_date=date(2026, 11, 20),
        nightly_price=Decimal("94.00"),
        total_paid=Decimal("376.00"),
        host_id="HOST-4001",
        host_cancelled_at=datetime(2026, 11, 16, 9, 40, tzinfo=timezone.utc),
        host_last_reply_at=None,
        guest_requested=guest_requested,
        guest_message=(
            "Please just refund the four nights. A man has followed me from the metro "
            "and is standing across the street watching the door, I am scared to walk away."
        ),
    )


class SafetyAgentContractTests(unittest.TestCase):
    def test_safety_agent_only_invokes_handoff_to_safety_agent(self) -> None:
        ticket = make_safety_ticket(guest_requested="refund")
        gateway = PolicyToolGateway()
        orchestrator = SupportTeamOrchestrator(gateway=gateway)
        resolution = orchestrator.handle_ticket(ticket, open_listings=[])

        self.assertEqual(resolution.ticket_type, TicketType.SAFETY)
        self.assertEqual(resolution.agent_role, AgentRole.SAFETY_AGENT)
        self.assertEqual(resolution.tool_used, "handoff_to_safety_agent")
        self.assertTrue(resolution.handoff_completed)
        self.assertGreaterEqual(len(resolution.safety_conditions), 1)

        allowed_calls = [c for c in gateway.ledger.tool_calls if c.allowed]
        self.assertEqual(len(allowed_calls), 1)
        self.assertEqual(allowed_calls[0].tool_name, "handoff_to_safety_agent")

    def test_non_safety_agents_cannot_call_handoff_to_safety_agent(self) -> None:
        ticket = make_safety_ticket()
        gateway = PolicyToolGateway()
        with self.assertRaises(UnauthorizedToolError):
            gateway.handoff_to_safety_agent(
                AgentRole.REBOOKING_AGENT,
                ticket,
                (SafetyCondition.THREAT_OR_VIOLENCE,),
            )
        with self.assertRaises(UnauthorizedToolError):
            gateway.handoff_to_safety_agent(
                AgentRole.REFUND_AGENT,
                ticket,
                (SafetyCondition.THREAT_OR_VIOLENCE,),
            )

    def test_safety_agent_exposes_only_safety_role(self) -> None:
        agent = SafetyAgent(gateway=PolicyToolGateway())
        self.assertEqual(agent.role, AgentRole.SAFETY_AGENT)


class RefundAgentContractTests(unittest.TestCase):
    def _make_refund_or_rebooking_ticket(
        self,
        *,
        ticket_id: str = "LIS-TKT-0004",
        guest_requested: str = "refund",
    ) -> SupportTicket:
        return SupportTicket(
            ticket_id=ticket_id,
            opened_at=datetime(2026, 11, 16, 14, 1, tzinfo=timezone.utc),
            reservation_id=f"RES-{ticket_id}",
            guest_name="Beatriz Carvalho",
            guest_language="pt",
            original_listing_id="LST-200004",
            original_listing_title="Graca Viewpoint Flat",
            neighborhood="Graca",
            property_type="Entire apartment",
            bedrooms=1,
            party_size=2,
            check_in_date=date(2026, 11, 16),
            check_out_date=date(2026, 11, 18),
            nightly_price=Decimal("84.00"),
            total_paid=Decimal("168.00"),
            host_id="HOST-4001",
            host_cancelled_at=datetime(2026, 11, 16, 7, 58, tzinfo=timezone.utc),
            host_last_reply_at=None,
            guest_requested=guest_requested,
            guest_message="Cancelled this morning.",
        )

    def test_refund_agent_issues_full_total_paid_and_exposes_refund_role(self) -> None:
        gateway = PolicyToolGateway()
        agent = RefundAgent(gateway=gateway)
        self.assertEqual(agent.role, AgentRole.REFUND_AGENT)

        ticket = self._make_refund_or_rebooking_ticket(guest_requested="refund")
        resolution = SupportTeamOrchestrator(gateway=gateway).handle_ticket(ticket, open_listings=[])
        self.assertEqual(resolution.ticket_type, TicketType.REFUND)
        self.assertEqual(resolution.agent_role, AgentRole.REFUND_AGENT)
        self.assertEqual(resolution.tool_used, "issue_refund")
        self.assertEqual(resolution.refund_amount, Decimal("168.00"))

    def test_zero_comparable_homes_and_declined_rebooking_fall_back_to_refund(self) -> None:
        ticket_no_match = self._make_refund_or_rebooking_ticket(
            ticket_id="LIS-TKT-NOMATCH",
            guest_requested="rebooking",
        )
        over_budget_listing = OpenListing(
            listing_id="LST-100020",
            neighborhood="Graca",
            property_type="Entire apartment",
            bedrooms=1,
            max_guests=2,
            available_from=date(2026, 11, 16),
            available_to=date(2026, 11, 18),
            nightly_price=Decimal("100.81"),
            status=ListingStatus.AVAILABLE,
        )
        res_no_match = SupportTeamOrchestrator().handle_ticket(
            ticket_no_match,
            open_listings=[over_budget_listing],
        )
        self.assertEqual(res_no_match.tool_used, "issue_refund")
        self.assertEqual(res_no_match.agent_role, AgentRole.REFUND_AGENT)
        self.assertEqual(res_no_match.refund_amount, Decimal("168.00"))
        self.assertTrue(res_no_match.fallback_to_refund)

        ticket_declined = self._make_refund_or_rebooking_ticket(
            ticket_id="LIS-TKT-DECLINED",
            guest_requested="rebooking",
        )
        valid_listing = OpenListing(
            listing_id="LST-100021",
            neighborhood="Graca",
            property_type="Entire apartment",
            bedrooms=1,
            max_guests=2,
            available_from=date(2026, 11, 16),
            available_to=date(2026, 11, 18),
            nightly_price=Decimal("90.00"),
            status=ListingStatus.AVAILABLE,
        )
        res_declined = SupportTeamOrchestrator().handle_ticket(
            ticket_declined,
            open_listings=[valid_listing],
            guest_declines_rebooking=True,
        )
        self.assertEqual(res_declined.tool_used, "issue_refund")
        self.assertEqual(res_declined.refund_amount, Decimal("168.00"))
        self.assertEqual(valid_listing.status, ListingStatus.AVAILABLE)


if __name__ == "__main__":
    unittest.main()
