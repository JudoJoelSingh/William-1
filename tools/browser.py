"""
Browser Tool Module for William-1 (v0.2).
Handles opening web URLs (known site aliases, fuzzy phrasings, or validated http/https URLs)
and conducting web searches in the default web browser.
"""

import urllib.parse
import webbrowser
from typing import Dict, Any
from config import config


def _resolve_website_alias(site_query: str) -> str:
    """
    Resolves natural phrasing to canonical website key using config.SITE_ALIASES.
    Example: 'my mail' -> 'gmail', 'videos' -> 'youtube', 'movies' -> 'netflix'.
    """
    if not site_query:
        return ""
    cleaned = site_query.lower().strip()
    return config.SITE_ALIASES.get(cleaned, cleaned)


def _validate_and_format_url(url_or_name: str) -> Dict[str, Any]:
    """
    Resolves known site aliases or parses and validates a web URL.
    Ensures only http and https protocols are permitted.
    """
    if not url_or_name or not url_or_name.strip():
        return {"valid": False, "error": "Empty URL provided."}

    cleaned = url_or_name.strip()
    key = _resolve_website_alias(cleaned)

    # Check known websites allowlist
    if key in config.KNOWN_WEBSITES:
        return {"valid": True, "url": config.KNOWN_WEBSITES[key], "name": key.capitalize()}

    # Check direct URL
    if "://" not in cleaned:
        cleaned = "https://" + cleaned

    parsed = urllib.parse.urlparse(cleaned)

    # Restrict strictly to web protocols
    if parsed.scheme not in ("http", "https"):
        return {
            "valid": False,
            "error": f"Invalid protocol '{parsed.scheme}'. Only http and https URLs are permitted."
        }

    if not parsed.netloc:
        return {"valid": False, "error": "Invalid URL structure."}

    return {"valid": True, "url": cleaned, "name": parsed.netloc}


def open_url(url: str) -> Dict[str, Any]:
    """
    Opens a validated web URL or known website in the default browser.
    """
    result = _validate_and_format_url(url)
    if not result["valid"]:
        return {
            "success": False,
            "message": f"I couldn't open that URL: {result.get('error', 'invalid address')}.",
            "error": result.get("error")
        }

    target_url = result["url"]
    display_name = result.get("name", target_url)

    try:
        webbrowser.open(target_url)
        return {
            "success": True,
            "message": f"I've opened {display_name} in your browser.",
            "data": {"url": target_url, "name": display_name}
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"I encountered an error opening {display_name}.",
            "error": str(e)
        }


def search_web(query: str) -> Dict[str, Any]:
    """
    Executes a web search query in the default browser.
    """
    if not query or not query.strip():
        return {
            "success": False,
            "message": "Please specify what you would like to search for.",
            "error": "Empty search query."
        }

    encoded_query = urllib.parse.quote_plus(query.strip())
    search_url = f"https://www.google.com/search?q={encoded_query}"

    try:
        webbrowser.open(search_url)
        return {
            "success": True,
            "message": f"I've opened search results for '{query}'.",
            "data": {"query": query, "url": search_url}
        }
    except Exception as e:
        return {
            "success": False,
            "message": "I encountered an error while opening the web search.",
            "error": str(e)
        }
