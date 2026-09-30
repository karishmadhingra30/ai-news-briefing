#!/usr/bin/env python3
"""Deterministic helpers for a host-agent news skill. No AI calls or email sends."""
from __future__ import annotations

import argparse
import concurrent.futures
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

REFS = Path(__file__).resolve().parent.parent / "references"
DIMENSIONS = {"impact": .25, "novelty": .15, "evidence": .20,
              "technical_se": .20, "customer_se": .20}
TRACKING = {"fbclid", "gclid", "mc_cid", "mc_eid"}
MAX_BYTES = 3_000_000
RECORD_MARKER = "AI-BRIEFING-RECORD "


def canonical_url(url: str) -> str:
    p = urlsplit(url.strip())
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("Expected an HTTP(S) URL without credentials")
    # Preserve meaningful query parameters and path/version distinctions.
    query = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                   if not k.lower().startswith("utm_") and k.lower() not in TRACKING)
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or "/",
                       urlencode(query), ""))


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def clean_text(value: str) -> str:
    parser = TextOnly()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamp must have a timezone")
    return dt.astimezone(timezone.utc)


def feed_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for parser in (timestamp, parsedate_to_datetime):
        try:
            dt = parser(value)
            if dt.tzinfo is not None:
                return dt.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
    return None


def tagname(element):
    return element.tag.rsplit("}", 1)[-1]


def child_text(element, names):
    for child in element:
        if tagname(child) in names:
            return "".join(child.itertext()).strip()
    return ""


def parse_feed(data: bytes, source: str) -> list[dict]:
    if len(data) > MAX_BYTES:
        raise ValueError("Feed exceeded size limit")
    root = ET.fromstring(data)
    if tagname(root) not in {"rss", "feed", "RDF"}:
        raise ValueError("Response is not RSS or Atom")
    items = []
    for node in root.iter():
        if tagname(node) not in {"item", "entry"}:
            continue
        url = ""
        for child in node:
            if tagname(child) == "link" and child.attrib.get("rel", "alternate") == "alternate":
                url = child.attrib.get("href") or (child.text or "").strip()
                if url:
                    break
        try:
            url = canonical_url(url)
        except ValueError:
            continue
        published = feed_date(child_text(node, {"pubDate", "published", "date"}))
        # Atom updated time is deliberately not treated as original publication.
        items.append({
            "title": clean_text(child_text(node, {"title"})), "url": url,
            "published_at": published.isoformat() if published else None,
            "source": source,
            "excerpt": clean_text(child_text(node, {"description", "summary", "content", "encoded"}))[:1600],
        })
    return items


def fetch_feed(source: dict) -> tuple[list[dict], dict]:
    try:
        url = canonical_url(source["url"])
        req = Request(url, headers={"User-Agent": "AI-News-Briefing/0.1 (+RSS reader)",
                                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
        with urlopen(req, timeout=20) as response:
            data = response.read(MAX_BYTES + 1)
        items = parse_feed(data, source["name"])
        return items, {"source": source["name"], "url": url,
                       "status": "ok", "fetched": len(items)}
    except Exception as exc:
        return [], {"source": source.get("name", "Unknown"), "url": source.get("url", ""),
                    "status": "error", "error": str(exc)[:250], "fetched": 0}


def collect(config: dict, since: datetime, now: datetime) -> dict:
    items, coverage, seen = [], [], set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for rows, report in pool.map(fetch_feed, config["feeds"]):
            report["in_window"] = 0
            for row in rows:
                dt = timestamp(row["published_at"]) if row["published_at"] else None
                if dt and not since <= dt <= now + timedelta(minutes=5):
                    continue
                report["in_window"] += 1
                if row["url"] not in seen:
                    seen.add(row["url"])
                    items.append(row)
            coverage.append(report)
    items.sort(key=lambda item: item["published_at"] or "", reverse=True)
    return {"collected_at": now.isoformat(), "since": since.isoformat(),
            "items": items, "coverage": coverage}


def required_text(obj, key):
    val = obj.get(key)
    if not isinstance(val, str) or not val.strip():
        raise ValueError(f"{key} must be a nonempty string")
    return val


def validate_digest(d: dict):
    date.fromisoformat(required_text(d, "date"))
    ZoneInfo(required_text(d, "timezone"))
    start, end = timestamp(required_text(d, "coverage_start")), timestamp(required_text(d, "coverage_end"))
    if end < start:
        raise ValueError("Coverage end precedes start")
    if type(d.get("preview")) is not bool:
        raise ValueError("preview must be an explicit boolean")
    if not isinstance(d.get("coverage_notes"), list) or not all(isinstance(x, str) for x in d["coverage_notes"]):
        raise ValueError("coverage_notes must be a list of strings")
    stories = d.get("stories")
    if not isinstance(stories, list) or len(stories) > 8:
        raise ValueError("stories must be a list of at most eight events")
    seen = set()
    for s in stories:
        event, revision = required_text(s, "event_key"), required_text(s, "revision_key")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,159}", event + ""):
            raise ValueError("event_key must use lowercase letters, digits, dots, underscores or hyphens")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,159}", revision):
            raise ValueError("revision_key has invalid characters")
        if event in seen:
            raise ValueError("Duplicate event in digest")
        seen.add(event)
        required_text(s, "title")
        required_text(s, "score_reason")
        scores = s.get("scores", {})
        for dimension in DIMENSIONS:
            score = scores.get(dimension)
            if type(score) not in (int, float) or not 0 <= score <= 5:
                raise ValueError(f"Invalid score: {dimension}")
        sources = s.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("Every event requires a source")
        for source in sources:
            required_text(source, "title")
            canonical_url(required_text(source, "url"))
        for section, keys in {
            "plain": ["what_happened", "why_it_matters", "customer_angle"],
            "technical": ["what_changed", "implementation", "availability_and_limits", "try_or_ask"],
        }.items():
            for key in keys:
                required_text(s.get(section, {}), key)
    for extra in d.get("extras", []):
        if extra.get("label") not in {"Worth trying", "Coming up"}:
            raise ValueError("Invalid extra label")
        required_text(extra, "text")
        canonical_url(required_text(extra, "url"))


def event_score(s: dict) -> float:
    return round(sum(s["scores"][k] * weight for k, weight in DIMENSIONS.items()), 2)


def render_edition(d: dict, edition: str) -> dict:
    label = "Technical" if edition == "technical" else "Plain English"
    subject = f"AI Briefing | {label} | {d['date']}"
    if d["preview"]:
        subject = "PREVIEW | " + subject
    html = ["<!doctype html><html lang='en'><head><meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width,initial-scale=1'>",
            f"<title>{escape(subject)}</title></head>",
            "<body style='margin:0;background:#f3f5f8;color:#182638;font-family:Arial,sans-serif'>",
            "<main style='max-width:720px;margin:24px auto;padding:32px;background:white;border-radius:12px'>",
            "<p style='font-size:12px;letter-spacing:2px;color:#50647d'>AI + SOLUTIONS ENGINEERING</p>",
            f"<h1 style='font-size:30px;margin-bottom:8px'>{escape(label)} briefing</h1>",
            f"<p style='color:#50647d'>{escape(d['date'])} · {escape(d['timezone'])}</p>"]
    text = [subject, f"Coverage: {d['coverage_start']} to {d['coverage_end']}", ""]
    if d["preview"]:
        html.append("<p style='padding:12px;background:#fff1d6'>Preview — review before activating delivery.</p>")
    if not d["stories"]:
        quiet = "No new verified stories met the briefing threshold in this coverage window."
        html.append(f"<p>{quiet}</p>")
        text.append(quiet)
    for n, s in enumerate(d["stories"], 1):
        html.append(f"<section style='border-top:1px solid #dce3ec;padding-top:18px;margin-top:24px'><h2 style='font-size:21px'>{n}. {escape(s['title'])}</h2>")
        text.extend([f"{n}. {s['title']}", ""])
        keys = [("what_changed", "What changed"), ("implementation", "Implementation implications"),
                ("availability_and_limits", "Availability and limits"), ("try_or_ask", "Try or ask")] if edition == "technical" else [
                ("what_happened", "What happened"), ("why_it_matters", "Why it matters"), ("customer_angle", "Customer talking point")]
        section = s["technical" if edition == "technical" else "plain"]
        for key, heading in keys:
            html.append(f"<p style='line-height:1.6'><strong>{heading}:</strong> {escape(section[key])}</p>")
            text.extend([f"{heading}: {section[key]}", ""])
        links = []
        for source in s["sources"]:
            url = canonical_url(source["url"])
            links.append(f"<a style='color:#1756ad' href='{escape(url, quote=True)}'>{escape(source['title'])}</a>")
            text.append(f"Source: {source['title']} — {url}")
        html.append("<p style='font-size:13px'>" + " · ".join(links) + "</p></section>")
        text.append("")
    for extra in d.get("extras", []):
        html.append(f"<h2>{escape(extra['label'])}</h2><p>{escape(extra['text'])} <a href='{escape(canonical_url(extra['url']), quote=True)}'>Source</a></p>")
        text.append(f"{extra['label']}: {extra['text']} — {extra['url']}")
    html.append("<footer style='border-top:1px solid #dce3ec;margin-top:28px;padding-top:16px;color:#50647d;font-size:12px'>")
    for note in d["coverage_notes"]:
        html.append(f"<p>{escape(note)}</p>")
        text.append("Coverage note: " + note)
    record = {"version": 1, "date": d["date"], "edition": edition, "preview": d["preview"],
              "coverage_start": d["coverage_start"], "coverage_end": d["coverage_end"],
              "events": [{"event_key": s["event_key"], "revision_key": s["revision_key"]} for s in d["stories"]]}
    line = RECORD_MARKER + json.dumps(record, separators=(",", ":"))
    html.append("<p>Coverage record — helps prevent repeated stories.</p>"
                f"<p style='font-size:10px;overflow-wrap:anywhere'>{escape(line)}</p></footer></main></body></html>")
    text.extend(["", line])
    html_body, text_body = "\n".join(html), "\n".join(text)
    return {"edition": edition, "subject": subject, "record": record,
            "payload": {"mime_type": "multipart/alternative", "parts": [
                {"mime_type": "text/plain", "charset": "utf-8", "body": {"content": text_body}},
                {"mime_type": "text/html", "charset": "utf-8", "body": {"content": html_body}}]}}


def extract_records(text: str) -> list[dict]:
    decoder, records = json.JSONDecoder(), []
    # Supports plain text and escaped HTML exports.
    text = unescape(text)
    for match in re.finditer(re.escape(RECORD_MARKER), text):
        try:
            obj, _ = decoder.raw_decode(text[match.end():].lstrip())
            if (obj.get("version") == 1 and obj.get("preview") is False
                    and obj.get("edition") in {"technical", "plain-english"}
                    and isinstance(obj.get("events"), list)):
                date.fromisoformat(obj["date"])
                timestamp(obj["coverage_end"])
                records.append(obj)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return records


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    col = sub.add_parser("collect")
    col.add_argument("--sources", type=Path, default=REFS / "sources.json")
    col.add_argument("--hours", type=float, default=30)
    col.add_argument("--out", type=Path, required=True)
    ren = sub.add_parser("render")
    ren.add_argument("--input", type=Path, required=True)
    ren.add_argument("--out", type=Path, required=True)
    hist = sub.add_parser("history")
    hist.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "collect":
        if not 0 < args.hours <= 168:
            parser.error("--hours must be greater than 0 and at most 168")
        now = datetime.now(timezone.utc)
        result = collect(json.loads(args.sources.read_text()), now - timedelta(hours=args.hours), now)
        write_json(args.out, result)
        ok = sum(c["status"] == "ok" for c in result["coverage"])
        print(f"Collected {len(result['items'])} candidates; {ok}/{len(result['coverage'])} feeds succeeded. Written to {args.out}")
        return 0 if ok else 2
    if args.command == "history":
        text = args.input.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
            if isinstance(data, list):
                text = "\n".join(row["body"] for row in data)
        except ValueError:
            pass
        print(json.dumps(extract_records(text), indent=2))
        return 0
    data = json.loads(args.input.read_text(encoding="utf-8"))
    validate_digest(data)
    args.out.mkdir(parents=True, exist_ok=True)
    messages = [render_edition(data, e) for e in ("technical", "plain-english")]
    for m in messages:
        for extension, part in zip(("txt", "html"), m["payload"]["parts"]):
            (args.out / f"{m['edition']}.{extension}").write_text(part["body"]["content"], encoding="utf-8")
    write_json(args.out / "messages.json", messages)
    print(f"Validated and rendered two editions to {args.out}. No email was sent.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError) as error:
        print(f"Validation error: {error}", file=sys.stderr)
        sys.exit(2)
