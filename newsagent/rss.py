from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Iterable

import httpx


_TAG_STRIP_RE = re.compile(r"<[^>]+>")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/133.0.0.0 Safari/537.36 NewsAgent/0.1"
)


@dataclass
class FeedItem:
    title: str
    link: str
    summary: str
    source: str
    feed_url: str
    published_at: datetime | None


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    raw = "".join(node.itertext()).strip()
    return html.unescape(_TAG_STRIP_RE.sub("", raw)).strip()


def _child_text(parent: ET.Element, names: Iterable[str]) -> str:
    for name in names:
        child = parent.find(name)
        if child is not None:
            value = _text(child)
            if value:
                return value
    return ""


def _parse_date(date_text: str) -> datetime | None:
    if not date_text:
        return None
    try:
        return parsedate_to_datetime(date_text)
    except (TypeError, ValueError):
        pass

    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(date_text, fmt)
            if parsed.tzinfo is None and fmt.endswith("Z"):
                parsed = parsed.replace(tzinfo=datetime.UTC)
            return parsed
        except ValueError:
            continue
    return None


def _fetch_xml(url: str, timeout_sec: int = 15) -> bytes:
    with httpx.Client(
        timeout=timeout_sec,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def parse_feed(url: str) -> list[FeedItem]:
    try:
        xml_data = _fetch_xml(url)
        root = ET.fromstring(xml_data)
    except Exception:
        return []

    tag = root.tag.lower()
    if tag.endswith("rss"):
        return _parse_rss(root, url)
    if tag.endswith("feed"):
        return _parse_atom(root, url)
    return []


def _parse_rss(root: ET.Element, feed_url: str) -> list[FeedItem]:
    channel = root.find("channel")
    if channel is None:
        return []

    source = _child_text(channel, ["title"]) or feed_url
    items: list[FeedItem] = []

    for item in channel.findall("item"):
        title = _child_text(item, ["title"])
        link = _child_text(item, ["link"])
        summary = _child_text(item, ["description", "summary"])
        published_raw = _child_text(item, ["pubDate", "published", "{*}date"])

        if not title or not link:
            continue

        items.append(
            FeedItem(
                title=title,
                link=link,
                summary=summary,
                source=source,
                feed_url=feed_url,
                published_at=_parse_date(published_raw),
            )
        )

    return items


def _parse_atom(root: ET.Element, feed_url: str) -> list[FeedItem]:
    source = _child_text(root, ["{*}title"]) or feed_url
    items: list[FeedItem] = []

    for entry in root.findall("{*}entry"):
        title = _child_text(entry, ["{*}title"])
        summary = _child_text(entry, ["{*}summary", "{*}content"])
        published_raw = _child_text(entry, ["{*}published", "{*}updated", "{*}date"])

        link = ""
        for link_node in entry.findall("{*}link"):
            href = link_node.attrib.get("href", "").strip()
            rel = link_node.attrib.get("rel", "").strip().lower()
            if href and rel in {"", "alternate"}:
                link = href
                break

        if not title or not link:
            continue

        items.append(
            FeedItem(
                title=title,
                link=link,
                summary=summary,
                source=source,
                feed_url=feed_url,
                published_at=_parse_date(published_raw),
            )
        )

    return items
