"""Unit tests for locked-out guest eligibility, 5 comparable-home tests, and neighborhood ranking."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from stranded_guest_support.eligibility import (
    calculate_uplift,
    is_comparable_home,
    qualifies_for_rebooking,
    select_comparable_listings,
)
from stranded_guest_support.models import ListingStatus, OpenListing, SupportTicket


def make_ticket(**overrides: object) -> SupportTicket:
    defaults: dict[str, object] = {
        "ticket_id": "LIS-TKT-0100",
        "opened_at": datetime(2026, 11, 16, 14, 0, tzinfo=timezone.utc),
        "reservation_id": "RES-2026-10100",
        "guest_name": "Guest",
        "guest_language": "en",
        "original_listing_id": "LST-200001",
        "original_listing_title": "Original Flat",
        "neighborhood": "Alfama",
        "property_type": "Entire apartment",
        "bedrooms": 1,
        "party_size": 2,
        "check_in_date": date(2026, 11, 16),
        "check_out_date": date(2026, 11, 20),
        "nightly_price": Decimal("110.00"),
        "total_paid": Decimal("440.00"),
        "host_id": "HOST-4001",
        "host_cancelled_at": datetime(2026, 11, 16, 8, 12, tzinfo=timezone.utc),
        "host_last_reply_at": None,
        "guest_requested": "rebooking",
        "guest_message": "Booking was cancelled at the door.",
    }
    defaults.update(overrides)
    return SupportTicket(**defaults)  # type: ignore[arg-type]


def make_listing(**overrides: object) -> OpenListing:
    defaults: dict[str, object] = {
        "listing_id": "LST-100001",
        "neighborhood": "Alfama",
        "property_type": "Entire apartment",
        "bedrooms": 1,
        "max_guests": 2,
        "available_from": date(2026, 11, 16),
        "available_to": date(2026, 11, 20),
        "nightly_price": Decimal("132.00"),
        "status": ListingStatus.AVAILABLE,
    }
    defaults.update(overrides)
    return OpenListing(**defaults)  # type: ignore[arg-type]


class EligibilityTests(unittest.TestCase):
    def test_qualifies_for_each_locked_out_condition(self) -> None:
        # 1. Host cancelled within 30 days of check-in
        cancelled = make_ticket(
            host_cancelled_at=datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc),
            host_last_reply_at=datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc),
            guest_message="Host cancelled.",
        )
        self.assertTrue(qualifies_for_rebooking(cancelled))

        # 2. No working access at check-in (no cancellation)
        no_access = make_ticket(
            host_cancelled_at=None,
            host_last_reply_at=datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc),
            guest_message="The lockbox is empty and code does not work.",
        )
        self.assertTrue(qualifies_for_rebooking(no_access))

        # 3. Host unreachable
        unreachable = make_ticket(
            host_cancelled_at=None,
            host_last_reply_at=datetime(2026, 11, 14, 16, 22, tzinfo=timezone.utc),
            guest_message="Please help find another flat.",
        )
        self.assertTrue(qualifies_for_rebooking(unreachable))

        # Non-qualifying: cancelled 45 days before, host replied after ticket opened, no access issue
        non_qualifying = make_ticket(
            host_cancelled_at=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc),
            host_last_reply_at=datetime(2026, 11, 16, 15, 0, tzinfo=timezone.utc),
            guest_message="Just wondering about check-in instructions.",
        )
        self.assertFalse(qualifies_for_rebooking(non_qualifying))

    def test_five_comparable_home_tests_and_120_percent_boundary(self) -> None:
        ticket = make_ticket(nightly_price=Decimal("110.00"))
        self.assertTrue(is_comparable_home(ticket, make_listing(nightly_price=Decimal("132.00"))))
        self.assertFalse(is_comparable_home(ticket, make_listing(nightly_price=Decimal("132.01"))))

        # Date gap fails
        self.assertFalse(is_comparable_home(ticket, make_listing(available_to=date(2026, 11, 19))))
        # Party size fails
        self.assertFalse(is_comparable_home(ticket, make_listing(max_guests=1)))
        # Bedrooms fails
        self.assertFalse(is_comparable_home(ticket, make_listing(bedrooms=0)))
        # Status fails
        self.assertFalse(is_comparable_home(ticket, make_listing(status=ListingStatus.ON_HOLD)))
        self.assertFalse(is_comparable_home(ticket, make_listing(status=ListingStatus.BOOKED)))
        # Original listing range fails
        self.assertFalse(is_comparable_home(ticket, make_listing(listing_id="LST-200001")))

    def test_studio_zero_bedrooms_accepts_zero_or_more(self) -> None:
        studio_ticket = make_ticket(bedrooms=0, property_type="Entire studio")
        self.assertTrue(is_comparable_home(studio_ticket, make_listing(bedrooms=0)))
        self.assertTrue(is_comparable_home(studio_ticket, make_listing(bedrooms=1)))

    def test_neighborhood_is_preference_not_gate(self) -> None:
        ticket = make_ticket(neighborhood="Alfama", nightly_price=Decimal("100.00"))
        far = make_listing(listing_id="LST-100010", neighborhood="Belem", nightly_price=Decimal("100.00"))
        neighbour = make_listing(listing_id="LST-100011", neighborhood="Graca", nightly_price=Decimal("115.00"))
        exact = make_listing(listing_id="LST-100012", neighborhood="Alfama", nightly_price=Decimal("118.00"))

        ranked = select_comparable_listings(ticket, [far, neighbour, exact])
        self.assertEqual([l.listing_id for l in ranked], ["LST-100012", "LST-100011", "LST-100010"])
        self.assertEqual(select_comparable_listings(ticket, [far]), [far])

    def test_calculate_uplift_clamps_below_original_to_zero(self) -> None:
        ticket = make_ticket(nightly_price=Decimal("110.00"))  # 4 nights
        higher = make_listing(nightly_price=Decimal("125.00"))
        cheaper = make_listing(nightly_price=Decimal("95.00"))
        self.assertEqual(calculate_uplift(ticket, higher), Decimal("60.00"))
        self.assertEqual(calculate_uplift(ticket, cheaper), Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
