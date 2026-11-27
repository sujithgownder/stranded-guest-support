# Quickstart Validation Guide: Stranded Guest Support

**Feature**: [spec.md](spec.md)  
**Plan**: [plan.md](plan.md)  
**Data Model**: [data-model.md](data-model.md)  
**Contracts**: [agent-tools-contract.md](contracts/agent-tools-contract.md)

## Prerequisites

- Python `3.11+` (verified on `Python 3.15.2`)
- Repository root (`stranded-guest-support/`) containing:
  - `Lisbon Stranded Guest Tickets (16 Nov 2026).csv`
  - `AirCover Rebooking and Refund Rules - Lisbon Check-In Incident.md`

## Setup

Install the package in editable mode from the repository root:

```powershell
python -m pip install -e .
```

## Validation Scenarios

### 1. Automated Unit, Contract, and Integration Suite

Run the full test suite using Python's built-in `unittest` discovery:

```powershell
python -m unittest discover -s tests -v
```

**Expected outcomes**:
- **Safety triage & pre-handoff lock**: All 6 safety tickets (`LIS-TKT-0007`, `LIS-TKT-0015`, `LIS-TKT-0023`, `LIS-TKT-0034`, `LIS-TKT-0046`, `LIS-TKT-0055`) trigger `handoff_to_safety_agent` only, regardless of `guest_requested` (`refund`, `callback`, `rebooking`, `other`); attempts to call `hold_booking` or `issue_refund` on safety tickets raise `SafetyHandoffRequiredError` / `UnauthorizedToolError`.
- **Angry & callback retention**: Angry-word tickets (`LIS-TKT-0005`, `LIS-TKT-0022`, `LIS-TKT-0041`) and non-safety `callback` / `other` tickets (`LIS-TKT-0017`, `LIS-TKT-0029`, `LIS-TKT-0039`, `LIS-TKT-0049`, `LIS-TKT-0059`, `LIS-TKT-0060`) remain classified as `rebooking`.
- **120% nightly price boundary**: Exact `1.20 * original nightly_price` passes (`EUR 132.00` for `EUR 110.00`), while `EUR 132.01` is rejected; `on_hold`, `booked`, under-capacity, under-bedroom, and partial-date listings fail comparability.
- **Refund cap & one remedy per stay**: Refunds greater than `total_paid` (including promo-code ticket `LIS-TKT-0028` where `total_paid = 432.00 < 4 * 120.00`) or less than `EUR 0.01` are rejected; stays with a hold cannot also be refunded.
- **60-ticket Lisbon incident benchmark**: Triage matches `expected_outcome` on all 60 rows (`34 rebooking`, `20 refund`, `6 safety`).

### 2. CLI Triage Verification Against Incident CSV

Run triage verification directly from the command line:

```powershell
python -m stranded_guest_support --tickets "Lisbon Stranded Guest Tickets (16 Nov 2026).csv" --json
```

**Expected outcome**: Exit code `0`, JSON summary reporting `total_tickets: 60`, `rebooking: 34`, `refund: 20`, `safety: 6`, and `0` policy violations.

### 3. End-to-End Run With Open Listings CSV

When `airbnb_lisbon_open_listings_2026-11-16.csv` is available, run full rebooking + refund + safety execution:

```powershell
python -m stranded_guest_support --tickets "Lisbon Stranded Guest Tickets (16 Nov 2026).csv" --listings "airbnb_lisbon_open_listings_2026-11-16.csv" --json
```

**Expected outcome**: Exit code `0`; every rebooking hold uses an open listing `LST-100001`–`LST-100450` within the 120% nightly ceiling, total uplift stays within `EUR 9000.00`, every refund is `<= total_paid`, and all 6 safety tickets execute `handoff_to_safety_agent` exclusively.
