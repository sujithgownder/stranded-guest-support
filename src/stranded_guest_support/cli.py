"""Command-line interface for stranded guest ticket triage and incident processing."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Sequence

from .agents import SupportTeamOrchestrator
from .eligibility import qualifies_for_rebooking
from .loaders import load_open_listings_csv, load_tickets_csv
from .models import PolicyViolationError, TicketType
from .safety import classify_ticket
from .tools import PolicyToolGateway

DEFAULT_TICKETS_PATH = Path("Lisbon Stranded Guest Tickets (16 Nov 2026).csv")


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="stranded-guest-support",
        description="Triage and process Stranded Guest Support incident tickets.",
    )
    parser.add_argument(
        "--tickets",
        type=Path,
        default=DEFAULT_TICKETS_PATH,
        help="Path to the stranded guest tickets CSV file.",
    )
    parser.add_argument(
        "--listings",
        type=Path,
        default=None,
        help="Optional path to the open Lisbon listings CSV file.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON output instead of a human-readable summary.",
    )
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    """Execute ticket triage/orchestration and return a POSIX exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.tickets.is_file():
        print(f"ERROR: Tickets file not found: {args.tickets}", file=sys.stderr)
        return 1
    if args.listings is not None and not args.listings.is_file():
        print(f"ERROR: Open listings file not found: {args.listings}", file=sys.stderr)
        return 1

    tickets = load_tickets_csv(args.tickets)
    counts: Counter[str] = Counter()
    mismatches: list[dict[str, str]] = []
    violations: list[str] = []
    results: list[dict[str, object]] = []

    if args.listings is not None:
        listings = load_open_listings_csv(args.listings)
        gateway = PolicyToolGateway()
        orchestrator = SupportTeamOrchestrator(gateway=gateway)
        for ticket in tickets:
            try:
                resolution = orchestrator.handle_ticket(ticket, listings)
                counts[resolution.ticket_type.value] += 1
                if ticket.expected_outcome and resolution.ticket_type.value != ticket.expected_outcome:
                    mismatches.append(
                        {
                            "ticket_id": ticket.ticket_id,
                            "expected": ticket.expected_outcome,
                            "actual": resolution.ticket_type.value,
                        }
                    )
                results.append(
                    {
                        "ticket_id": resolution.ticket_id,
                        "ticket_type": resolution.ticket_type.value,
                        "agent_role": resolution.agent_role.value,
                        "tool_used": resolution.tool_used,
                        "listing_id": resolution.listing_id,
                        "refund_amount": str(resolution.refund_amount)
                        if resolution.refund_amount is not None
                        else None,
                        "uplift": str(resolution.uplift),
                    }
                )
            except PolicyViolationError as exc:
                violations.append(f"{ticket.ticket_id}: {exc}")

        payload: dict[str, object] = {
            "mode": "full",
            "total_tickets": len(tickets),
            "counts": dict(counts),
            "uplift_spent": str(gateway.ledger.uplift_spent),
            "total_uplift_budget": str(gateway.ledger.total_uplift_budget),
            "expected_mismatches": mismatches,
            "policy_violations": len(violations),
            "violation_details": violations,
            "resolutions": results,
        }
    else:
        for ticket in tickets:
            ticket_type, conditions = classify_ticket(ticket)
            counts[ticket_type.value] += 1
            if ticket_type == TicketType.REBOOKING and not qualifies_for_rebooking(ticket):
                violations.append(f"{ticket.ticket_id}: does not meet locked-out qualifying criteria")
            if ticket.expected_outcome and ticket_type.value != ticket.expected_outcome:
                mismatches.append(
                    {
                        "ticket_id": ticket.ticket_id,
                        "expected": ticket.expected_outcome,
                        "actual": ticket_type.value,
                    }
                )
            results.append(
                {
                    "ticket_id": ticket.ticket_id,
                    "ticket_type": ticket_type.value,
                    "safety_conditions": [c.value for c in conditions],
                }
            )

        payload = {
            "mode": "triage",
            "total_tickets": len(tickets),
            "counts": dict(counts),
            "expected_mismatches": mismatches,
            "policy_violations": len(violations),
            "violation_details": violations,
            "tickets": results,
        }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"Processed {payload['total_tickets']} tickets ({payload['mode']}): "
            f"rebooking={counts.get('rebooking', 0)}, "
            f"refund={counts.get('refund', 0)}, "
            f"safety={counts.get('safety', 0)}, "
            f"mismatches={len(mismatches)}, violations={len(violations)}"
        )

    return 1 if (mismatches or violations) else 0


def main() -> None:
    """Console script entry point."""
    raise SystemExit(run_cli())
