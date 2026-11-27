"""Unit tests for the FastMCP stranded guest support server and spec.md guards."""

from __future__ import annotations

import asyncio
from decimal import Decimal
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fastmcp import Client

from stranded_guest_support.loaders import load_open_listings_csv
from stranded_guest_support.mcp_server import create_mcp_server
from stranded_guest_support.models import ListingStatus

REPO_ROOT = Path(__file__).resolve().parents[2]
LISTINGS_CSV = REPO_ROOT / "Lisbon Open Listings Export (16 Nov 2026).csv"
TICKETS_CSV = REPO_ROOT / "Lisbon Stranded Guest Tickets (16 Nov 2026).csv"


def _parse_tool_dict(result: object) -> dict[str, object]:
    if hasattr(result, "data") and isinstance(result.data, dict):
        return result.data
    content = getattr(result, "content", result)
    if isinstance(content, list) and content:
        text = getattr(content[0], "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"Unexpected MCP tool result shape: {result!r}")


class FastMCPServerTests(unittest.TestCase):
    def test_server_exposes_exact_six_tools_and_loads_csv_once(self) -> None:
        with patch(
            "stranded_guest_support.mcp_server.load_open_listings_csv",
            wraps=load_open_listings_csv,
        ) as mock_load_listings:
            server = create_mcp_server(listings_path=LISTINGS_CSV, tickets_path=TICKETS_CSV)
            self.assertEqual(mock_load_listings.call_count, 1)

            async def run_checks() -> None:
                async with Client(server) as client:
                    tools = await client.list_tools()
                    self.assertEqual(
                        sorted(tool.name for tool in tools),
                        sorted(
                            [
                                "lookup_reservation",
                                "search_open_listings",
                                "hold_booking",
                                "issue_refund",
                                "message_host",
                                "handoff_to_safety_agent",
                            ]
                        ),
                    )

                    # search_open_listings returns only available CSV listings fitting all 4 rules
                    search_data = _parse_tool_dict(
                        await client.call_tool(
                            "search_open_listings",
                            {
                                "check_in_date": "2026-11-16",
                                "check_out_date": "2026-11-19",
                                "party_size": 2,
                                "bedrooms": 1,
                                "max_nightly_price": 110.40,
                            },
                        )
                    )
                    returned_ids = search_data["listing_ids"]
                    self.assertIsInstance(returned_ids, list)
                    self.assertGreater(len(returned_ids), 0)

                    csv_listings = {l.listing_id: l for l in load_open_listings_csv(LISTINGS_CSV)}
                    for lid in returned_ids:
                        self.assertIn(lid, csv_listings)
                        listing = csv_listings[lid]
                        self.assertEqual(listing.status, ListingStatus.AVAILABLE)
                        self.assertLessEqual(listing.available_from.isoformat(), "2026-11-16")
                        self.assertGreaterEqual(listing.available_to.isoformat(), "2026-11-19")
                        self.assertGreaterEqual(listing.max_guests, 2)
                        self.assertGreaterEqual(listing.bedrooms, 1)
                        self.assertLessEqual(listing.nightly_price, Decimal("110.40"))

                    # lookup_reservation
                    res_lookup = _parse_tool_dict(
                        await client.call_tool(
                            "lookup_reservation", {"reservation_id": "RES-2026-10001"}
                        )
                    )
                    self.assertTrue(res_lookup["found"])
                    self.assertEqual(res_lookup["ticket_id"], "LIS-TKT-0001")

                    # hold_booking enforces 120% price ceiling, dates, capacity, bedrooms, status
                    # RES-2026-10001: check_in=2026-11-16, check_out=2026-11-19, party=2, beds=0, 120% max=110.40
                    # LST-100002 is available on 2026-11-15..2026-11-22, 3 beds, max 7 guests, price=417.84 (> 110.40)
                    over_cap = _parse_tool_dict(
                        await client.call_tool(
                            "hold_booking",
                            {"reservation_id": "RES-2026-10001", "listing_id": "LST-100002"},
                        )
                    )
                    self.assertFalse(over_cap["ok"])
                    self.assertIn("exceeds_120_percent_price_ceiling", str(over_cap["reason"]))

                    # LST-100016 has available_from=2026-11-17 (> 2026-11-16)
                    bad_dates = _parse_tool_dict(
                        await client.call_tool(
                            "hold_booking",
                            {"reservation_id": "RES-2026-10001", "listing_id": "LST-100016"},
                        )
                    )
                    self.assertFalse(bad_dates["ok"])
                    self.assertEqual(bad_dates["reason"], "dates_not_covered")

                    # RES-2026-10002 requires bedrooms=2, party_size=4, check_out=2026-11-21
                    # LST-100004 has bedrooms=1, max_guests=2
                    too_small = _parse_tool_dict(
                        await client.call_tool(
                            "hold_booking",
                            {"reservation_id": "RES-2026-10002", "listing_id": "LST-100004"},
                        )
                    )
                    self.assertFalse(too_small["ok"])

                    # Valid hold succeeds and blocks subsequent issue_refund (one remedy per stay)
                    first_id = returned_ids[0]
                    res_hold = _parse_tool_dict(
                        await client.call_tool(
                            "hold_booking",
                            {"reservation_id": "RES-2026-10001", "listing_id": first_id},
                        )
                    )
                    self.assertTrue(res_hold["ok"])
                    self.assertEqual(res_hold["status"], "on_hold")

                    refund_after_hold = _parse_tool_dict(
                        await client.call_tool(
                            "issue_refund",
                            {"reservation_id": "RES-2026-10001", "amount": 276.00},
                        )
                    )
                    self.assertFalse(refund_after_hold["ok"])
                    self.assertEqual(refund_after_hold["reason"], "active_hold_exists")

                    # Double hold rejected
                    second_hold = _parse_tool_dict(
                        await client.call_tool(
                            "hold_booking",
                            {"reservation_id": "RES-2026-10001", "listing_id": returned_ids[1]},
                        )
                    )
                    self.assertFalse(second_hold["ok"])
                    self.assertEqual(second_hold["reason"], "active_hold_exists")

                    # issue_refund rejects unknown reservation_id and amounts > total_paid
                    unknown_refund = _parse_tool_dict(
                        await client.call_tool(
                            "issue_refund",
                            {"reservation_id": "RES-UNKNOWN-999", "amount": 50.00},
                        )
                    )
                    self.assertFalse(unknown_refund["ok"])
                    self.assertEqual(unknown_refund["reason"], "reservation_not_found")

                    res_over = _parse_tool_dict(
                        await client.call_tool(
                            "issue_refund",
                            {"reservation_id": "RES-2026-10028", "amount": 480.00},
                        )
                    )
                    self.assertFalse(res_over["ok"])
                    res_ok = _parse_tool_dict(
                        await client.call_tool(
                            "issue_refund",
                            {"reservation_id": "RES-2026-10028", "amount": 432.00},
                        )
                    )
                    self.assertTrue(res_ok["ok"])
                    self.assertEqual(res_ok["amount"], 432.0)

                    # Hold after refund rejected (one remedy per stay)
                    hold_after_refund = _parse_tool_dict(
                        await client.call_tool(
                            "hold_booking",
                            {"reservation_id": "RES-2026-10028", "listing_id": returned_ids[1]},
                        )
                    )
                    self.assertFalse(hold_after_refund["ok"])
                    self.assertEqual(hold_after_refund["reason"], "already_refunded")

                    # Safety ticket blocks both hold_booking and issue_refund until handoff_to_safety_agent
                    # RES-2026-10007 (LIS-TKT-0007) has injury_or_medical_need
                    blocked_refund = _parse_tool_dict(
                        await client.call_tool(
                            "issue_refund",
                            {"reservation_id": "RES-2026-10007", "amount": 448.00},
                        )
                    )
                    self.assertFalse(blocked_refund["ok"])
                    self.assertEqual(blocked_refund["status"], "blocked")
                    self.assertEqual(blocked_refund["reason"], "safety_handoff_required")

                    blocked_hold = _parse_tool_dict(
                        await client.call_tool(
                            "hold_booking",
                            {"reservation_id": "RES-2026-10007", "listing_id": returned_ids[1]},
                        )
                    )
                    self.assertFalse(blocked_hold["ok"])
                    self.assertEqual(blocked_hold["status"], "blocked")
                    self.assertEqual(blocked_hold["reason"], "safety_handoff_required")

                    # Now hand off to live safety agent, which clears the pre-handoff block
                    res_safety = _parse_tool_dict(
                        await client.call_tool(
                            "handoff_to_safety_agent",
                            {
                                "ticket_id": "LIS-TKT-0007",
                                "reservation_id": "RES-2026-10007",
                                "safety_condition": "injury_or_medical_need",
                                "summary": "Guest slipped and knee is bleeding.",
                            },
                        )
                    )
                    self.assertTrue(res_safety["ok"])
                    self.assertEqual(res_safety["status"], "handed_off")

                    post_handoff_refund = _parse_tool_dict(
                        await client.call_tool(
                            "issue_refund",
                            {"reservation_id": "RES-2026-10007", "amount": 448.00},
                        )
                    )
                    self.assertTrue(post_handoff_refund["ok"])
                    self.assertEqual(post_handoff_refund["status"], "refunded")

                    # message_host
                    res_msg = _parse_tool_dict(
                        await client.call_tool(
                            "message_host",
                            {
                                "host_id": "HOST-4117",
                                "reservation_id": "RES-2026-10003",
                                "message": "Guest locked out, please confirm access.",
                            },
                        )
                    )
                    self.assertTrue(res_msg["ok"])
                    self.assertEqual(res_msg["status"], "sent")

            asyncio.run(run_checks())
            self.assertEqual(mock_load_listings.call_count, 1)


if __name__ == "__main__":
    unittest.main()
