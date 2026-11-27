"""Unit tests for the FastMCP stranded guest support server."""

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
        with (
            patch(
                "stranded_guest_support.mcp_server.load_open_listings_csv",
                wraps=load_open_listings_csv,
            ) as mock_load_listings,
        ):
            server = create_mcp_server(listings_path=LISTINGS_CSV, tickets_path=TICKETS_CSV)
            self.assertEqual(mock_load_listings.call_count, 1)

            async def run_checks() -> None:
                async with Client(server) as client:
                    tools = await client.list_tools()
                    names = sorted(tool.name for tool in tools)
                    self.assertEqual(
                        names,
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

                    # Search open listings and verify every returned listing_id exists in CSV & fits all 4
                    search_res = await client.call_tool(
                        "search_open_listings",
                        {
                            "check_in_date": "2026-11-16",
                            "check_out_date": "2026-11-20",
                            "party_size": 2,
                            "bedrooms": 1,
                            "max_nightly_price": 100.00,
                        },
                    )
                    search_data = _parse_tool_dict(search_res)
                    returned_ids = search_data["listing_ids"]
                    self.assertIsInstance(returned_ids, list)
                    self.assertGreater(len(returned_ids), 0)

                    csv_listings = {l.listing_id: l for l in load_open_listings_csv(LISTINGS_CSV)}
                    for lid in returned_ids:
                        self.assertIn(lid, csv_listings)
                        listing = csv_listings[lid]
                        self.assertEqual(listing.status, ListingStatus.AVAILABLE)
                        self.assertLessEqual(listing.available_from.isoformat(), "2026-11-16")
                        self.assertGreaterEqual(listing.available_to.isoformat(), "2026-11-20")
                        self.assertGreaterEqual(listing.max_guests, 2)
                        self.assertGreaterEqual(listing.bedrooms, 1)
                        self.assertLessEqual(listing.nightly_price, Decimal("100.00"))

                    # lookup_reservation
                    res_lookup = _parse_tool_dict(
                        await client.call_tool(
                            "lookup_reservation", {"reservation_id": "RES-2026-10001"}
                        )
                    )
                    self.assertTrue(res_lookup["found"])
                    self.assertEqual(res_lookup["ticket_id"], "LIS-TKT-0001")

                    # hold_booking
                    first_id = returned_ids[0]
                    res_hold = _parse_tool_dict(
                        await client.call_tool(
                            "hold_booking",
                            {"reservation_id": "RES-2026-10001", "listing_id": first_id},
                        )
                    )
                    self.assertTrue(res_hold["ok"])
                    self.assertEqual(res_hold["status"], "on_hold")

                    # Confirm held listing no longer returned in search_open_listings
                    search_after = _parse_tool_dict(
                        await client.call_tool(
                            "search_open_listings",
                            {
                                "check_in_date": "2026-11-16",
                                "check_out_date": "2026-11-20",
                                "party_size": 2,
                                "bedrooms": 1,
                                "max_nightly_price": 100.00,
                            },
                        )
                    )
                    self.assertNotIn(first_id, search_after["listing_ids"])

                    # issue_refund (respects total_paid cap)
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

                    # handoff_to_safety_agent
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

            asyncio.run(run_checks())
            # Ensure CSV was never re-read during tool calls
            self.assertEqual(mock_load_listings.call_count, 1)


if __name__ == "__main__":
    unittest.main()
