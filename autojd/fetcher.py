"""
Fetch job description text from a URL.
Handles: static HTML, JS-rendered pages (via Playwright), and JSON API responses.
"""

import json
import re

import requests
from bs4 import BeautifulSoup


def _clean_text(raw: str) -> str:
    """Collapse whitespace and strip blank lines."""
    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        line = line.strip()
        if line:
            cleaned.append(line)
    return "\n".join(cleaned)


def _extract_from_html(html: str) -> str:
    """Extract visible text from HTML using BeautifulSoup."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script/style/nav/footer noise
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "img"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return _clean_text(text)


def _extract_from_json(data) -> str:
    """Recursively extract all string values from JSON."""
    parts = []

    def _recurse(obj):
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _recurse(v)
        elif isinstance(obj, list):
            for item in obj:
                _recurse(item)

    _recurse(data)
    return _clean_text("\n".join(parts))


def _fetch_with_requests(url: str) -> str | None:
    """Try a simple HTTP GET first."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")

    # JSON API response
    if "application/json" in content_type:
        return _extract_from_json(resp.json())

    html = resp.text
    text = _extract_from_html(html)

    # If very little text was extracted, the page is probably JS-rendered
    if len(text) < 200:
        return None

    return text


def _fetch_with_playwright(url: str) -> str:
    """Use Playwright (headless Chromium) for JS-rendered pages."""
    from playwright.sync_api import sync_playwright

    def _looks_like_placeholder(text: str) -> bool:
        low = text.lower()
        bad_signals = [
            "loading",
            "skip to main content",
            "follow us",
            "all rights reserved",
        ]
        hits = sum(1 for s in bad_signals if s in low)
        return len(text) < 500 or hits >= 3

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 2000},
        )
        page = context.new_page()

        # Retry the JS render path because some Workday pages initially render only shell text.
        for attempt in range(3):
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500 + attempt * 2000)

            # Try to trigger lazy-loaded text blocks.
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1200)
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(800)

            # Best-effort wait for common JD cues.
            try:
                page.wait_for_function(
                    """
                    () => {
                        const t = (document.body?.innerText || '').toLowerCase();
                        return (
                            t.includes('qualifications') ||
                            t.includes('responsibilities') ||
                            t.includes('about the role') ||
                            t.includes('role:') ||
                            t.includes('job requisition id')
                        ) && t.length > 1500;
                    }
                    """,
                    timeout=10000,
                )
            except Exception:
                # Continue with extraction and fallback checks below.
                pass

            html = page.content()
            text = _extract_from_html(html)
            if not _looks_like_placeholder(text):
                context.close()
                browser.close()
                return text

        # Final attempt uses whatever content is available after retries.
        html = page.content()
        context.close()
        browser.close()

    return _extract_from_html(html)


def fetch_jd(url: str) -> str:
    """
    Fetch job description from a URL.
    Tries simple HTTP first, falls back to Playwright for JS-heavy pages.
    """
    print(f"[*] Fetching JD from: {url}")

    # Try simple requests first
    try:
        text = _fetch_with_requests(url)
        if text:
            print(f"[+] Extracted {len(text)} chars via HTTP request")
            return text
        print("[*] Insufficient text from HTTP, trying Playwright...")
    except Exception as e:
        print(f"[*] HTTP fetch failed ({e}), trying Playwright...")

    # Fall back to Playwright
    try:
        text = _fetch_with_playwright(url)
        print(f"[+] Extracted {len(text)} chars via Playwright")
        if len(text) < 500:
            raise RuntimeError(
                "Playwright only captured page shell content. "
                "Please retry once, or try a direct job-details URL that contains full description text."
            )
        return text
    except Exception as e:
        raise RuntimeError(
            f"Failed to fetch JD from {url}. "
            f"Ensure the URL is valid and accessible. Error: {e}"
        )
