import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("briefing", ROOT / "skills/daily-briefing/scripts/briefing.py")
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.digest = json.loads((ROOT / "examples/digest.json").read_text())

    def test_tracking_removed_but_product_versions_preserved(self):
        self.assertEqual(b.canonical_url("https://example.com/release?v=2&utm_source=x#top"), "https://example.com/release?v=2")
        self.assertNotEqual(b.canonical_url("https://example.com/?v=1"), b.canonical_url("https://example.com/?v=2"))

    def test_unsafe_link_rejected(self):
        for url in ("javascript:alert(1)", "file:///etc/passwd", "https://user:secret@example.com/"):
            with self.assertRaises(ValueError):
                b.canonical_url(url)

    def test_rss_and_atom_dates(self):
        rss = b'<rss><channel><item><title>Launch</title><link>https://example.com/a</link><pubDate>Tue, 29 Sep 2026 12:00:00 GMT</pubDate><description>&lt;b&gt;Hello&lt;/b&gt;</description></item></channel></rss>'
        atom = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Launch</title><link rel="self" href="https://example.com/feed"/><link href="https://example.com/a"/><published>2026-09-29T12:00:00Z</published><summary>Hello</summary></entry></feed>'
        self.assertEqual(b.parse_feed(rss, "A")[0]["published_at"], b.parse_feed(atom, "B")[0]["published_at"])
        self.assertEqual(b.parse_feed(atom, "B")[0]["url"], "https://example.com/a")
        self.assertEqual(b.parse_feed(rss, "A")[0]["excerpt"], "Hello")

    def test_atom_updated_is_not_publication(self):
        atom = b'<feed><entry><title>Old</title><link href="https://example.com/a"/><updated>2026-09-29T12:00:00Z</updated></entry></feed>'
        self.assertIsNone(b.parse_feed(atom, "A")[0]["published_at"])

    def test_partial_collection_and_time_window(self):
        def fake(source):
            if source["name"] == "B":
                return [], {"source": "B", "status": "error", "fetched": 0}
            return [{"url": f"https://example.com/{i}", "published_at": dt} for i, dt in enumerate([
                "2026-09-29T12:00:00+00:00", "2026-09-20T12:00:00+00:00", "2026-10-01T12:00:00+00:00", None])], {"source": "A", "status": "ok", "fetched": 4}
        with patch.object(b, "fetch_feed", side_effect=fake):
            out = b.collect({"feeds": [{"name": "A"}, {"name": "B"}, {"name": "A"}]}, b.timestamp("2026-09-29T00:00:00Z"), b.timestamp("2026-09-30T00:00:00Z"))
        self.assertEqual(len(out["items"]), 2)
        self.assertEqual(out["coverage"][1]["status"], "error")

    def test_bad_response_not_quiet_success(self):
        with self.assertRaises(ValueError):
            b.parse_feed(b"<html><body>Blocked</body></html>", "A")

    def test_both_editions_share_events(self):
        b.validate_digest(self.digest)
        a, c = [b.render_edition(self.digest, edition) for edition in ("technical", "plain-english")]
        self.assertEqual(a["record"]["events"], c["record"]["events"])
        self.assertNotEqual(a["subject"], c["subject"])

    def test_duplicate_event_rejected(self):
        self.digest["stories"].append(copy.deepcopy(self.digest["stories"][0]))
        with self.assertRaises(ValueError):
            b.validate_digest(self.digest)

    def test_missing_evidence_rejected(self):
        self.digest["stories"][0]["sources"] = []
        with self.assertRaises(ValueError):
            b.validate_digest(self.digest)

    def test_boolean_is_not_numeric_score(self):
        self.digest["stories"][0]["scores"]["impact"] = True
        with self.assertRaises(ValueError):
            b.validate_digest(self.digest)

    def test_markup_escaped(self):
        self.digest["stories"][0]["title"] = '<script>alert("x")</script>'
        msg = b.render_edition(self.digest, "technical")
        html = msg["payload"]["parts"][1]["body"]["content"]
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_preview_not_delivery_history(self):
        msg = b.render_edition(self.digest, "technical")
        self.assertEqual(b.extract_records(msg["payload"]["parts"][0]["body"]["content"]), [])
        self.digest["preview"] = False
        msg = b.render_edition(self.digest, "technical")
        for part in msg["payload"]["parts"]:
            self.assertEqual(b.extract_records(part["body"]["content"])[0]["edition"], "technical")

    def test_equal_se_weights(self):
        a = copy.deepcopy(self.digest["stories"][0])
        c = copy.deepcopy(a)
        a["scores"].update(technical_se=5, customer_se=0)
        c["scores"].update(technical_se=0, customer_se=5)
        self.assertEqual(b.event_score(a), b.event_score(c))

    def test_invalid_window(self):
        self.digest["coverage_start"] = "2026-10-10T00:00:00Z"
        with self.assertRaises(ValueError):
            b.validate_digest(self.digest)


if __name__ == "__main__":
    unittest.main()
