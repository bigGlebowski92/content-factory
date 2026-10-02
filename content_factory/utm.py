"""UTM helpers for Stage 2 link tracking."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def build_utm_url(
    base_url: str,
    *,
    source: str = "telegram",
    medium: str = "social",
    campaign: str,
    content: str | None = None,
) -> str:
    """Append standard UTM params to a landing URL without dropping existing query."""
    if not base_url:
        raise ValueError("base_url is required for UTM tracking")

    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["utm_source"] = source
    query["utm_medium"] = medium
    query["utm_campaign"] = campaign
    if content:
        query["utm_content"] = content

    return urlunparse(parsed._replace(query=urlencode(query)))
