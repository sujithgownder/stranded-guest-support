"""FastMCP server exposing the six stranded guest support tools with spec.md guards."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .eligibility import calculate_uplift, is_comparable_home
from .loaders import load_open_listings_csv, load_tickets_csv
from .models import (
    DEFAULT_UPLIFT_BUDGET,
    ListingStatus,
    OpenListing,
    SafetyCondition,
    SupportTicket,
    TWO_PLACES,
)
from .safety import detect_safety_conditions

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPEN_LISTINGS_CSV = REPO_ROOT / "Lisbon Open Listings Export (16 Nov 2026).csv"
DEFAULT_TICKETS_CSV = REPO_ROOT / "Lisbon Stranded Guest Tickets (16 Nov 2026).csv"
VALID_SAFETY_CONDITIONS = frozenset(c.value for c in SafetyCondition)


def _resolve_csv_path(path: Path | str | None, default_path: Path) -> Path:
    """Resolve an explicit path or fall back to the repository-root dataset."""
    if path is not None:
        return Path(path)
    cwd_candidate = Path(default_path.name)
    return cwd_candidate if cwd_candidate.is_file() else default_path


@dataclass
class SupportServerState:
    """In-memory server state loaded once from CSV datasets at startup."""

    listings_by_id: dict[str, OpenListing]
    tickets_by_reservation: dict[str, SupportTicket]
    tickets_by_id: dict[str, SupportTicket]
    safety_reservations: set[str]
    safety_handoffs_by_reservation: set[str] = field(default_factory=set)
    holds: dict[str, str] = field(default_factory=dict)
    refunds: dict[str, dict[str, Any]] = field(default_factory=dict)
    host_messages: list[dict[str, str]] = field(default_factory=list)
    safety_handoffs: dict[str, dict[str, str]] = field(default_factory=dict)
    uplift_spent: Decimal = Decimal("0.00")
    total_uplift_budget: Decimal = DEFAULT_UPLIFT_BUDGET

    def safety_block_reason(self, reservation_id: str) -> dict[str, Any] | None:
        """Return a blocked payload if reservation is a safety ticket awaiting hand-off."""
        if (
            reservation_id in self.safety_reservations
            and reservation_id not in self.safety_handoffs_by_reservation
        ):
            return {
                "ok": False,
                "status": "blocked",
                "reservation_id": reservation_id,
                "reason": "safety_handoff_required",
            }
        return None


def _describe_comparability_failure(ticket: SupportTicket, listing: OpenListing) -> str:
    """Identify the specific comparable-home rule that failed for a ticket/listing pair."""
    if listing.status != ListingStatus.AVAILABLE:
        return f"listing_not_available:{listing.status.value}"
    if listing.available_from > ticket.check_in_date or listing.available_to < ticket.check_out_date:
        return "dates_not_covered"
    if listing.max_guests < ticket.party_size:
        return f"insufficient_capacity:{listing.max_guests}<{ticket.party_size}"
    if listing.bedrooms < ticket.bedrooms:
        return f"insufficient_bedrooms:{listing.bedrooms}<{ticket.bedrooms}"
    if listing.nightly_price > ticket.max_rebook_nightly_price:
        return f"exceeds_120_percent_price_ceiling:{listing.nightly_price}>{ticket.max_rebook_nightly_price}"
    return "listing_not_comparable"


def create_mcp_server(
    *,
    listings_path: Path | str | None = None,
    tickets_path: Path | str | None = None,
) -> FastMCP:
    """Create and configure the FastMCP server, loading CSV exports once at startup."""
    resolved_listings = _resolve_csv_path(listings_path, DEFAULT_OPEN_LISTINGS_CSV)
    resolved_tickets = _resolve_csv_path(tickets_path, DEFAULT_TICKETS_CSV)

    listings = load_open_listings_csv(resolved_listings)
    tickets = load_tickets_csv(resolved_tickets) if resolved_tickets.is_file() else []
    safety_reservations = {
        ticket.reservation_id
        for ticket in tickets
        if detect_safety_conditions(ticket.guest_message)
    }

    state = SupportServerState(
        listings_by_id={listing.listing_id: listing for listing in listings},
        tickets_by_reservation={ticket.reservation_id: ticket for ticket in tickets},
        tickets_by_id={ticket.ticket_id: ticket for ticket in tickets},
        safety_reservations=safety_reservations,
    )

    server = FastMCP("stranded-guest-support")

    @server.tool()
    def lookup_reservation(reservation_id: str) -> dict[str, Any]:
        """Look up a reservation by reservation_id to read stay dates, party_size, bedrooms, original nightly_price, total_paid, and safety status (spec.md FR-003/FR-009/FR-013)."""
        ticket = state.tickets_by_reservation.get(reservation_id)
        if ticket is None:
            return {"found": False, "reservation_id": reservation_id}
        conditions = detect_safety_conditions(ticket.guest_message)
        return {
            "found": True,
            "reservation_id": ticket.reservation_id,
            "ticket_id": ticket.ticket_id,
            "guest_name": ticket.guest_name,
            "neighborhood": ticket.neighborhood,
            "bedrooms": ticket.bedrooms,
            "party_size": ticket.party_size,
            "check_in_date": ticket.check_in_date.isoformat(),
            "check_out_date": ticket.check_out_date.isoformat(),
            "nightly_price": float(ticket.nightly_price),
            "max_rebook_nightly_price": float(ticket.max_rebook_nightly_price),
            "total_paid": float(ticket.total_paid),
            "host_id": ticket.host_id,
            "safety_conditions": [c.value for c in conditions],
        }

    @server.tool()
    def search_open_listings(
        check_in_date: str,
        check_out_date: str,
        party_size: int,
        bedrooms: int,
        max_nightly_price: float,
    ) -> dict[str, Any]:
        """Search loaded CSV open listings with status=available whose [available_from, available_to] covers check_in_date..check_out_date, max_guests>=party_size, bedrooms>=bedrooms, and nightly_price<=max_nightly_price (pass <=1.20x original nightly_price per spec.md FR-009/FR-010)."""
        start = date.fromisoformat(check_in_date)
        end = date.fromisoformat(check_out_date)
        if end <= start:
            return {"listing_ids": [], "count": 0, "error": "check_out_date must be after check_in_date"}
        if party_size < 1 or bedrooms < 0 or max_nightly_price <= 0:
            return {"listing_ids": [], "count": 0, "error": "invalid search constraints"}

        price_ceiling = Decimal(str(max_nightly_price)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        matches = [
            listing
            for listing in state.listings_by_id.values()
            if listing.status == ListingStatus.AVAILABLE
            and listing.available_from <= start
            and listing.available_to >= end
            and listing.max_guests >= party_size
            and listing.bedrooms >= bedrooms
            and listing.nightly_price <= price_ceiling
        ]
        matches.sort(key=lambda item: (item.nightly_price, item.listing_id))
        return {
            "listing_ids": [item.listing_id for item in matches],
            "count": len(matches),
        }

    @server.tool()
    def hold_booking(reservation_id: str, listing_id: str) -> dict[str, Any]:
        """Hold an available comparable listing for a known reservation. Enforces safety pre-handoff block (FR-005), one remedy per stay (FR-015), dates, party_size, bedrooms, status=available, and nightly_price<=1.20x original nightly_price (FR-009/FR-010)."""
        blocked = state.safety_block_reason(reservation_id)
        if blocked is not None:
            return blocked

        ticket = state.tickets_by_reservation.get(reservation_id)
        if ticket is None:
            return {"ok": False, "status": "rejected", "reason": "reservation_not_found"}

        if reservation_id in state.holds:
            return {"ok": False, "status": "rejected", "reason": "active_hold_exists"}
        if reservation_id in state.refunds:
            return {"ok": False, "status": "rejected", "reason": "already_refunded"}

        listing = state.listings_by_id.get(listing_id)
        if listing is None:
            return {"ok": False, "status": "rejected", "reason": "listing_not_found"}

        if not is_comparable_home(ticket, listing):
            return {
                "ok": False,
                "status": "rejected",
                "reason": _describe_comparability_failure(ticket, listing),
            }

        uplift = calculate_uplift(ticket, listing)
        if state.uplift_spent + uplift > state.total_uplift_budget:
            return {"ok": False, "status": "rejected", "reason": "exceeds_incident_uplift_budget"}

        listing.status = ListingStatus.ON_HOLD
        state.holds[reservation_id] = listing_id
        state.uplift_spent += uplift
        return {
            "ok": True,
            "status": "on_hold",
            "reservation_id": reservation_id,
            "listing_id": listing_id,
            "nightly_price": float(listing.nightly_price),
            "uplift": float(uplift),
        }

    @server.tool()
    def issue_refund(reservation_id: str, amount: float, reason: str = "") -> dict[str, Any]:
        """Issue a refund for a known reservation from EUR 0.01 up to total_paid (FR-013/FR-014). Enforces safety pre-handoff block (FR-005) and one remedy per stay (FR-015), rejecting unknown reservations and active holds."""
        blocked = state.safety_block_reason(reservation_id)
        if blocked is not None:
            return blocked

        ticket = state.tickets_by_reservation.get(reservation_id)
        if ticket is None:
            return {"ok": False, "status": "rejected", "reason": "reservation_not_found"}

        if reservation_id in state.holds:
            return {"ok": False, "status": "rejected", "reason": "active_hold_exists"}
        if reservation_id in state.refunds:
            return {"ok": False, "status": "rejected", "reason": "already_refunded"}

        refund_decimal = Decimal(str(amount)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        if refund_decimal < Decimal("0.01"):
            return {"ok": False, "status": "rejected", "reason": "amount_must_be_positive"}
        if refund_decimal > ticket.total_paid:
            return {
                "ok": False,
                "status": "rejected",
                "reason": f"exceeds_total_paid:{ticket.total_paid}",
            }

        record = {
            "ok": True,
            "status": "refunded",
            "reservation_id": reservation_id,
            "amount": float(refund_decimal),
            "reason": reason,
        }
        state.refunds[reservation_id] = record
        return record

    @server.tool()
    def message_host(host_id: str, reservation_id: str, message: str) -> dict[str, Any]:
        """Send an outreach message to a host; does not replace rebooking for unreachable hosts (FR-007/FR-016) or handoff_to_safety_agent on safety tickets (FR-004/FR-005/FR-016)."""
        entry = {
            "host_id": host_id,
            "reservation_id": reservation_id,
            "message": message,
        }
        state.host_messages.append(entry)
        return {
            "ok": True,
            "status": "sent",
            "host_id": host_id,
            "reservation_id": reservation_id,
        }

    @server.tool()
    def handoff_to_safety_agent(
        ticket_id: str,
        reservation_id: str,
        safety_condition: str,
        summary: str = "",
    ) -> dict[str, Any]:
        """Hand off any ticket exhibiting one of the five AirCover safety conditions (injury_or_medical_need, threat_or_violence, nowhere_safe_to_wait, unaccompanied_minor, stated_fear_of_person) to a live Trust and Safety agent before hold_booking or issue_refund (FR-002/FR-004/FR-005)."""
        if safety_condition not in VALID_SAFETY_CONDITIONS:
            return {
                "ok": False,
                "status": "rejected",
                "reason": f"invalid_safety_condition:{safety_condition}",
            }

        state.safety_reservations.add(reservation_id)
        state.safety_handoffs_by_reservation.add(reservation_id)
        record = {
            "ok": True,
            "status": "handed_off",
            "ticket_id": ticket_id,
            "reservation_id": reservation_id,
            "safety_condition": safety_condition,
        }
        state.safety_handoffs[ticket_id] = {**record, "summary": summary}
        return record

    return server


mcp = create_mcp_server()


def main(argv: list[str] | None = None) -> None:
    """Run the FastMCP server (defaults to stdio; supports --transport http/sse)."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the Stranded Guest Support FastMCP server.")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport protocol (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for HTTP/SSE transports.")
    parser.add_argument("--port", type=int, default=8000, help="Bind port for HTTP/SSE transports.")
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
