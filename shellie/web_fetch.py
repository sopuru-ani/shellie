"""Fetch a public http(s) URL and return readable text for the agent.

v1: GET only (no HEAD). Blocks private/loopback/link-local hosts (SSRF).
Supports HTML (BeautifulSoup), plain text, and JSON. No PDF/binary.

Long pages are returned in windows of _MAX_TEXT_CHARS. Pass start= to continue
from a cached parse of the same URL (no re-download when possible).
"""

from __future__ import annotations

import ipaddress
import json
import socket
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB download cap
_MAX_TEXT_CHARS = 80_000  # window size returned to the model
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)
_USER_AGENT = "Shellie/0.1 (+local research assistant; httpx)"

# Last successful parse — used for start= "fetch more" without re-downloading.
_cache_request_url: str | None = None
_cache_final_url: str | None = None
_cache_body: str | None = None
_cache_ctype: str | None = None
_cache_status: int | None = None


def clear_web_fetch_cache() -> None:
    """Drop the cached page. Call at the start of each new user turn."""
    global _cache_request_url, _cache_final_url, _cache_body, _cache_ctype, _cache_status
    _cache_request_url = None
    _cache_final_url = None
    _cache_body = None
    _cache_ctype = None
    _cache_status = None


def _set_cache(
    *,
    request_url: str,
    final_url: str,
    body: str,
    ctype: str,
    status: int,
) -> None:
    global _cache_request_url, _cache_final_url, _cache_body, _cache_ctype, _cache_status
    _cache_request_url = request_url
    _cache_final_url = final_url
    _cache_body = body
    _cache_ctype = ctype
    _cache_status = status


def _cache_matches(url: str) -> bool:
    return bool(
        _cache_body is not None
        and (url == _cache_request_url or url == _cache_final_url)
    )


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _host_resolves_to_blocked_ip(hostname: str) -> str | None:
    """Return an error string if hostname resolves to a blocked address."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        return f"could not resolve host {hostname!r}: {exc}"
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _is_blocked_ip(ip):
            return (
                f"refusing to fetch {hostname!r}: resolves to blocked address "
                f"{ip} (private/loopback/link-local)."
            )
    return None


def _validate_url(url: str) -> tuple[str, str] | tuple[None, str]:
    """Return (normalized_url, '') or (None, error)."""
    raw = (url or "").strip()
    if not raw:
        return None, "Error: url is empty."
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return None, "Error: only http(s) URLs are allowed."
    if not parsed.hostname:
        return None, "Error: URL has no hostname."
    host = parsed.hostname
    # Literal IPs in the URL — check without DNS.
    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip):
            return None, (
                f"Error: refusing to fetch blocked address {ip} "
                "(private/loopback/link-local)."
            )
    except ValueError:
        blocked = _host_resolves_to_blocked_ip(host)
        if blocked:
            return None, f"Error: {blocked}"
    return raw, ""


def _content_type_base(header: str | None) -> str:
    if not header:
        return ""
    return header.split(";", 1)[0].strip().casefold()


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    text = soup.get_text(separator="\n", strip=True)
    # Collapse long runs of blank lines.
    lines = [ln for ln in (line.strip() for line in text.splitlines()) if ln]
    body = "\n".join(lines)
    if title:
        return f"Title: {title}\n\n{body}"
    return body


def _download_and_parse(normalized: str) -> tuple[str, str, str, int] | str:
    """
    GET + parse. On success return (final_url, ctype, body, status).
    On failure return an Error: string.
    """
    try:
        with httpx.Client(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            with client.stream("GET", normalized) as resp:
                status = resp.status_code
                ctype = _content_type_base(resp.headers.get("content-type"))
                final_url = str(resp.url)

                redirect_err = _validate_url(final_url)[1]
                if redirect_err:
                    return redirect_err

                if status < 200 or status >= 300:
                    return (
                        f"Error: HTTP {status} for {final_url}\n"
                        f"Content-Type: {ctype or '(none)'}"
                    )

                if ctype in {"application/pdf", "application/octet-stream"} or (
                    ctype.startswith("image/")
                    or ctype.startswith("audio/")
                    or ctype.startswith("video/")
                    or ctype.startswith("font/")
                ):
                    return (
                        f"Error: unsupported Content-Type {ctype!r} for {final_url}.\n"
                        "web_fetch supports HTML, plain text, and JSON only (no PDF/binary)."
                    )

                chunks: list[bytes] = []
                total = 0
                for chunk in resp.iter_bytes():
                    total += len(chunk)
                    if total > _MAX_BODY_BYTES:
                        return (
                            f"Error: response from {final_url} exceeds "
                            f"{_MAX_BODY_BYTES} byte download limit."
                        )
                    chunks.append(chunk)
                raw = b"".join(chunks)
    except httpx.TimeoutException:
        return f"Error: timed out fetching {normalized}."
    except httpx.HTTPError as exc:
        return f"Error: could not fetch {normalized}: {exc}"

    if not ctype:
        head = raw[:256].lstrip().casefold()
        if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            ctype = "text/html"
        elif head.startswith(b"{") or head.startswith(b"["):
            ctype = "application/json"
        else:
            ctype = "text/plain"

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    if ctype in {"text/html", "application/xhtml+xml"} or ctype.endswith("+html"):
        body = _html_to_text(text)
    elif ctype in {"application/json", "text/json"} or ctype.endswith("+json"):
        try:
            body = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            body = text
    elif ctype.startswith("text/") or ctype in {"application/xml", "text/xml"}:
        body = text
    else:
        return (
            f"Error: unsupported Content-Type {ctype!r} for {final_url}.\n"
            "web_fetch supports HTML, plain text, and JSON only (no PDF/binary)."
        )

    return final_url, ctype, body.strip(), status


def _format_window(
    *,
    final_url: str,
    ctype: str,
    status: int,
    body: str,
    start: int,
) -> str:
    total = len(body)
    if start < 0:
        return "Error: start must be >= 0."
    if start > total:
        return (
            f"Error: start={start} is past end of page ({total} characters). "
            "Use start=0 to re-fetch, or a smaller start."
        )

    end = min(start + _MAX_TEXT_CHARS, total)
    window = body[start:end]
    more = end < total
    header = (
        f"Fetched: {final_url}\n"
        f"Content-Type: {ctype}\n"
        f"HTTP: {status}\n"
        f"Characters: {start}-{end} of {total}\n"
    )
    if more:
        header += (
            f"More content available. Call web_fetch again with the same url and "
            f"start={end} to continue (uses cache; no re-download).\n"
        )
    else:
        header += "End of page.\n"
    return header + "\n" + window


def fetch_url(url: str, start: int = 0) -> str:
    """Download url (or slice a cached parse) and return a text report for the model.

    start: character offset into the parsed text. 0 = (re)download and return the
    first window. Larger values continue from the cached page for this url.
    """
    normalized, err = _validate_url(url)
    if err:
        return err
    assert normalized is not None

    try:
        start_i = int(start)
    except (TypeError, ValueError):
        return "Error: start must be an integer >= 0."

    if start_i < 0:
        return "Error: start must be >= 0."

    # Continue from cache when possible.
    if start_i > 0 and _cache_matches(normalized):
        assert _cache_body is not None
        assert _cache_final_url is not None
        assert _cache_ctype is not None
        assert _cache_status is not None
        return _format_window(
            final_url=_cache_final_url,
            ctype=_cache_ctype,
            status=_cache_status,
            body=_cache_body,
            start=start_i,
        )

    # Fresh download (start=0, or cache miss / different url).
    result = _download_and_parse(normalized)
    if isinstance(result, str):
        return result
    final_url, ctype, body, status = result
    _set_cache(
        request_url=normalized,
        final_url=final_url,
        body=body,
        ctype=ctype,
        status=status,
    )
    return _format_window(
        final_url=final_url,
        ctype=ctype,
        status=status,
        body=body,
        start=start_i,
    )
