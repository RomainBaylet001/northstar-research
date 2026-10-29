"""Offline integration and adversarial tests. No mock records are committed as real holdings."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from northstar.__main__ import run
from northstar.compare import compare, latest, snapshots
from northstar.vanguard import FUNDS, IntegrityError, collect, fingerprint, normalize, store


def securities(date="2026-08-31", count=120):
    return [{
        "isin": f"US{i:09d}0", "sedol1": f"{i:07d}", "issuerName": f"Issuer {i}",
        "ticker": f"T{i}", "securityType": "EQ.STOCK",
        "marketValuePercentage": "0.83", "quantity": str(100 + i),
        "effectiveDate": date, "gicsSectorDescription": "Technology",
        "bloombergIsoCountry": "US",
    } for i in range(count)]


def response(rows, fund="VWCE", cursor=None, total=None):
    config = FUNDS[fund]
    return {"data": {
        "funds": [{"profile": {"portId": config["port_id"],
                               "identifiers": [{"altId": "ISIN", "altIdValue": config["isin"]}]}}],
        "borHoldings": [{"holdings": {
            "items": rows, "totalHoldings": len(rows) if total is None else total,
            "lastItemKey": cursor,
        }}],
    }}


def sample(fund="VWCE", date="2026-08-31", rows=None):
    data = securities(date) if rows is None else rows
    snap = collect(fund, fetch=lambda endpoint, payload: response(data, fund))
    return snap


class CollectorTests(unittest.TestCase):
    def test_complete_two_page_collection(self):
        data = securities()
        calls = []
        def fetch(_, payload):
            cursor = payload["variables"]["cursor"]
            calls.append(cursor)
            return response(data[:65], cursor="page2", total=120) if cursor is None else response(data[65:], total=120)
        result = collect("VWCE", fetch=fetch)
        self.assertEqual(calls, [None, "page2"])
        self.assertEqual(result["total_holdings"], 120)
        self.assertEqual(len(result["equities"]), 120)

    def test_reject_partial_page(self):
        with self.assertRaisesRegex(IntegrityError, "Incomplete"):
            collect("VWCE", fetch=lambda *args: response(securities()[:119], total=120))

    def test_reject_wrong_isin(self):
        def wrong(*args):
            r = response(securities())
            r["data"]["funds"][0]["profile"]["identifiers"][0]["altIdValue"] = "IE00INVALID"
            return r
        with self.assertRaisesRegex(IntegrityError, "ISIN"):
            collect("VWCE", fetch=wrong)

    def test_reject_mixed_dates(self):
        rows = securities()
        rows[5]["effectiveDate"] = "2026-09-30"
        with self.assertRaisesRegex(IntegrityError, "Mixed"):
            collect("VWCE", fetch=lambda *args: response(rows))

    def test_reject_circular_cursor(self):
        with self.assertRaisesRegex(IntegrityError, "cursor"):
            collect("VWCE", fetch=lambda *args: response(securities()[:60], cursor="repeat", total=120))

    def test_reject_unidentified_equity(self):
        data = securities()
        data[3]["isin"] = ""
        data[3]["sedol1"] = ""
        with self.assertRaisesRegex(IntegrityError, "neither"):
            normalize(data)

    def test_source_fingerprint_ignores_row_order(self):
        rows = securities()
        self.assertEqual(fingerprint(rows), fingerprint(list(reversed(rows))))

    def test_cash_retained_raw_and_not_joined(self):
        rows = securities()
        rows.append({"effectiveDate": "2026-08-31", "securityType": "CRNY",
                     "marketValuePercentage": "0.1"})
        snap = collect("VFEA", fetch=lambda *a: response(rows, "VFEA"))
        self.assertEqual(snap["total_holdings"], 121)
        self.assertEqual(len(snap["equities"]), 120)

    def test_invalid_weights_block(self):
        rows = securities()
        rows[0]["marketValuePercentage"] = "-1"
        with self.assertRaisesRegex(IntegrityError, "weight"):
            collect("VWCE", fetch=lambda *args: response(rows))


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.a = sample()
        changed = securities("2026-09-30")
        changed[0]["ticker"] = "T0NEW"
        changed[1]["quantity"] = "999"
        changed[2]["marketValuePercentage"] = "0.85"
        changed.pop(3)
        new = dict(changed[5], isin="US9999999990", sedol1="9999999",
                   ticker="NEW", issuerName="New issuer")
        changed.append(new)
        self.b = sample(date="2026-09-30", rows=changed)

    def test_additions_removals_share_counts(self):
        diff = compare(self.a, self.b)
        self.assertEqual(len(diff["additions"]), 1)
        self.assertEqual(len(diff["removals"]), 1)
        rename = next(r for r in diff["matched_changes"] if r["ticker_new"] == "T0NEW")
        self.assertEqual(rename["ticker_old"], "T0")
        self.assertEqual(rename["delta_bps"], "0.00")
        share = next(r for r in diff["matched_changes"] if r["ticker_new"] == "T1")
        self.assertEqual(share["shares_delta"], "898")

    def test_immutable_idempotent_archives(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            a, created = store(self.a, root)
            b, repeat = store(self.a, root)
            self.assertEqual(a, b)
            self.assertTrue(created)
            self.assertFalse(repeat)
            self.assertEqual(len(snapshots(root, "VWCE")), 1)

    def test_same_date_conflicting_source_quarantined(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            store(self.a, root)
            other = deepcopy(self.a)
            other["raw_items"][0]["ticker"] = "DIFFERENT"
            other["source_sha256"] = fingerprint(other["raw_items"])
            store(other, root)
            store(self.b, root)
            with self.assertRaisesRegex(IntegrityError, "Multiple"):
                latest(root, "VWCE")

    def test_stable_sedol_reconciles_missing_isin(self):
        old = deepcopy(self.a)
        old["equities"][0]["isin"] = ""
        old["equities"][0]["id"] = "SEDOL:" + old["equities"][0]["sedol"]
        diff = compare(old, self.b)
        self.assertEqual(len(diff["additions"]), 1)

    def test_sedol_conflict_quarantined(self):
        newer = deepcopy(self.b)
        newer["equities"][0]["isin"] = "US1234567890"
        newer["equities"][0]["id"] = "ISIN:US1234567890"
        with self.assertRaisesRegex(IntegrityError, "different known ISINs"):
            compare(self.a, newer)

    def test_ticker_collision_quarantined(self):
        newer = deepcopy(self.b)
        row = next(x for x in newer["equities"] if x["ticker"] == "T4")
        row["isin"] = "US1234567890"
        row["sedol"] = "7654321"
        row["id"] = "ISIN:US1234567890"
        with self.assertRaisesRegex(IntegrityError, "share a ticker"):
            compare(self.a, newer)

    def test_end_to_end_cli_archive_and_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for snap in (self.a, self.b):
                data = snap["raw_items"]
                rc = run(["collect", "--fund", "VWCE", "--root", d],
                         fetch=lambda endpoint, payload, data=data: response(data))
                self.assertEqual(rc, 0)
            output = latest(root, "VWCE")
            self.assertEqual(output["status"], "verified_identifier_comparison")
            self.assertTrue((root / output["report_path"]).is_file())
            self.assertEqual(len(list((root / "logs" / "runs").glob("*.json"))), 2)
            self.assertEqual(run(["status", "--fund", "VWCE", "--root", d]), 0)


if __name__ == "__main__":
    unittest.main()
