"""FastMCP server exposing the six stranded guest support tools."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .loaders import load_open_listings_csv, load_tickets_csv
from .models import ListingStatus, OpenListing, SupportTicket, TWO_PLACES

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPEN_LISTINGS_CSV = REPO_ROOT / "Lisbon Open Listings Export (16 Nov 2026).csv"
DEFAULT_TICKETS_CSV = REPO_ROOT / "Lisbon Stranded Guest Tickets (16 Nov 2026).csv"


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
    holds: dict[str, str] = field(default_factory=dict)
    refunds: dict[str, dict[str, Any]] = field(default_factory=dict)
    host_messages: list[dict[str, str]] = field(default_factory=list)
    safety_handoffs: dict[str, dict[str, str]] = field(default_factory=dict)


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

    state = SupportServerState(
        listings_by_id={listing.listing_id: listing for listing in listings},
        tickets_by_reservation={ticket.reservation_id: ticket for ticket in tickets},
        tickets_by_id={ticket.ticket_id: ticket for ticket in tickets},
    )

    server = FastMCP("stranded-guest-support")

    @server.tool()
    def lookup_reservation(reservation_id: str) -> dict[str, Any]:
        """Look up a reservation record by reservation_id."""
        ticket = state.tickets_by_reservation.get(reservation_id)
        if ticket is None:
            return {"found": False, "reservation_id": reservation_id}
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
            "total_paid": float(ticket.total_paid),
            "host_id": ticket.host_id,
        }

    @server.tool()
    def search_open_listings(
        check_in_date: str,
        check_out_date: str,
        party_size: int,
        bedrooms: int,
        max_nightly_price: float,
    ) -> dict[str, Any]:
        """Search loaded open listings matching dates, party_size, bedrooms, and price ceiling."""
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
        """Place a temporary hold on an available open listing for a reservation."""
        listing = state.listings_by_id.get(listing_id)
        if listing is None:
            return {"ok": False, "status": "rejected", "reason": "listing_not_found"}
        if listing.status != ListingStatus.AVAILABLE:
            return {
                "ok": False,
                "status": "rejected",
                "reason": f"listing_not_available:{listing.status.value}",
            }

        listing.status = ListingStatus.ON_HOLD
        state.holds[reservation_id] = listing_id
        return {
            "ok": True,
            "status": "on_hold",
            "reservation_id": reservation_id,
            "listing_id": listing_id,
            "nightly_price": float(listing.nightly_price),
        }

    @server.tool()
    def issue_refund(reservation_id: str, amount: float, reason: str = "") -> dict[str, Any]:
        """Issue a refund for a reservation, bounded by total_paid when known."""
        refund_decimal = Decimal(str(amount)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        if refund_decimal < Decimal("0.01"):
            return {"ok": False, "status": "rejected", "reason": "amount_must_be_positive"}

        ticket = state.tickets_by_reservation.get(reservation_id)
        if ticket is not None and refund_decimal > ticket.total_paid:
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
        """Send a message to a host regarding a reservation."""
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
        """Hand off a case to a live Trust and Safety agent."""
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
