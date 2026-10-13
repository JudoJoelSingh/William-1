"""
Memory Policy Module for William-1 Persistent Memory Layer (v0.3).

Enforces security, privacy, and quality standards for memory capture:
  1. Secret and credential filtering — refuses to store API keys, tokens,
     passwords, private keys, and credential-looking strings, with a spoken
     explanation.  Sensitive-seeming personal info (e.g. SSN, full address)
     is flagged and requires explicit confirmation before storage.
  2. Content evaluation — filters out transient commands and noise.
  3. Text normalization and near-duplicate / contradiction detection.
"""

import re
from typing import Tuple, List, Set, Optional


# ---------------------------------------------------------------------------
# Hard-block: these patterns are ALWAYS rejected with no override path.
# ---------------------------------------------------------------------------
SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("OpenAI API Key",
     re.compile(r"sk-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE)),
    ("Anthropic API Key",
     re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}", re.IGNORECASE)),
    ("GitHub Token",
     re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{20,}|github_pat_[a-zA-Z0-9_\-]{20,}", re.IGNORECASE)),
    ("AWS Access Key",
     re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}")),
    ("AWS Secret Key",
     re.compile(r"(?:aws[_\-]?secret|aws[_\-]?access)[_\-]?key\s*[=:]\s*\S{20,}", re.IGNORECASE)),
    ("Generic Bearer / JWT",
     re.compile(r"(?:bearer|token)\s+[a-zA-Z0-9_\-\.]{25,}", re.IGNORECASE)),
    ("Hex Token / Secret (long)",
     re.compile(r"\b[0-9a-f]{32,64}\b")),               # long hex blobs
    ("Base64 Credential Block",
     re.compile(r"(?:[A-Za-z0-9+/]{40,}={0,2})")),      # long base64
    ("Private Key Block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE)),
    ("Explicit Password Assignment",
     re.compile(r"(?:password|passwd|pwd|passcode|secret_key|api_key|apikey|access_token)"
                r"\s*(?:is|:|=)\s*['\"]?\S{4,}['\"]?", re.IGNORECASE)),
    ("Connection String with Credentials",
     re.compile(r"(?:mysql|postgres|mongodb|redis|amqp|ftp)s?://[^:@\s]+:[^@\s]+@", re.IGNORECASE)),
    ("Credit Card Number",
     re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")),
]

# ---------------------------------------------------------------------------
# Soft-block: these are flagged and require explicit confirmation.
# They won't be stored silently; the caller must pass confirmed=True.
# ---------------------------------------------------------------------------
SENSITIVE_PERSONAL_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("SSN / National ID",
     re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b")),
    ("Phone Number",
     re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("Full Street Address",
     re.compile(r"\b\d{1,5}\s+\w+\s+(?:st(?:reet)?|ave(?:nue)?|rd|road|blvd|ln|lane|dr|drive|ct|court|pl|place)\b",
                re.IGNORECASE)),
    ("Date of Birth",
     re.compile(r"\b(?:born|dob|birth(?:day|date)?)\s*[:\-]?\s*\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}\b",
                re.IGNORECASE)),
    ("Passport / License",
     re.compile(r"\b(?:passport|drivers?[\s\-]?license|dl)\s*(?:no|number|#|:)?\s*[A-Z0-9]{6,15}\b",
                re.IGNORECASE)),
]

# ---------------------------------------------------------------------------
# Transient / non-memorable phrases
# ---------------------------------------------------------------------------
TRANSIENT_PATTERNS: List[re.Pattern] = [
    re.compile(r"^(?:what time is it|what is the time|what date|what day)\b", re.IGNORECASE),
    re.compile(r"^(?:open|close|launch|start|stop|mute|unmute|set volume|turn off|shut down)\b", re.IGNORECASE),
    re.compile(r"^(?:hello|hi|hey|good morning|good evening|good night|goodbye|bye)\b", re.IGNORECASE),
    re.compile(r"^(?:how are you|how is it going|what is your name)\b", re.IGNORECASE),
    re.compile(r"^(?:what did you just do|explain your last action)\b", re.IGNORECASE),
    re.compile(r"^(?:how(?:'s| is) my computer|how is the computer)\b", re.IGNORECASE),
    re.compile(r"^(?:ok(?:ay)?|sure|thanks?|thank you|got it|never mind)\b", re.IGNORECASE),
]

ALLOWED_CATEGORIES: Set[str] = {
    "personal",
    "preference",
    "fact",
    "project",
    "decision",
    "milestone",
    "episodic",
}

# ---------------------------------------------------------------------------
# Keywords that signal a preference *update* (for contradiction detection)
# ---------------------------------------------------------------------------
PREFERENCE_UPDATE_SIGNALS: List[re.Pattern] = [
    re.compile(r"\b(?:now|actually|instead|switched?\s+to|no\s+longer)\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:now|actually|recently)\s+(?:prefer|use|work with|switched to)\b", re.IGNORECASE),
    re.compile(r"\bchanged?\s+(?:from|my\s+preference|to)\b", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def contains_secrets(content: str) -> Tuple[bool, str]:
    """
    Scans content for hard-blocked credentials.
    Returns (has_secret, human-readable description).
    """
    if not content:
        return False, ""
    for secret_type, pattern in SECRET_PATTERNS:
        if pattern.search(content):
            return True, secret_type
    return False, ""


def contains_sensitive_personal_info(content: str) -> Tuple[bool, str]:
    """
    Scans for sensitive-but-not-credential personal info that should be
    stored only with explicit user confirmation.
    Returns (is_sensitive, category_description).
    """
    if not content:
        return False, ""
    for category, pattern in SENSITIVE_PERSONAL_PATTERNS:
        if pattern.search(content):
            return True, category
    return False, ""


def sanitize_content(content: str) -> str:
    """Redacts any detected secrets with a placeholder."""
    if not content:
        return ""
    sanitized = content
    for _, pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED_SECRET]", sanitized)
    return sanitized


def is_valid_memory_candidate(
    content: str,
    category: str = "personal",
    confirmed: bool = False,
) -> Tuple[bool, str, bool]:
    """
    Evaluates whether the content is suitable for persistent storage.

    Returns:
        (is_valid, reason_string, requires_confirmation)
        - If requires_confirmation is True and confirmed is False, the caller
          must obtain explicit user confirmation before proceeding.
    """
    if not content or not content.strip():
        return False, "Content cannot be empty.", False

    trimmed = content.strip()

    if len(trimmed) < 3:
        return False, "Content is too short to be meaningful.", False

    if len(trimmed) > 2000:
        return False, "Content exceeds maximum memory record size (2000 characters).", False

    cat_norm = category.lower().strip()
    if cat_norm not in ALLOWED_CATEGORIES:
        return (
            False,
            f"Category '{category}' is not recognized. Allowed: {sorted(ALLOWED_CATEGORIES)}",
            False,
        )

    # 1. Hard-block: secrets (no override)
    has_secret, secret_desc = contains_secrets(trimmed)
    if has_secret:
        return (
            False,
            f"I won't store that — it looks like a credential ({secret_desc}). "
            f"Passwords and keys must never be saved to memory.",
            False,
        )

    # 2. Soft-block: sensitive personal info (requires confirmation)
    is_sensitive, sensitive_desc = contains_sensitive_personal_info(trimmed)
    if is_sensitive and not confirmed:
        return (
            False,
            f"This contains sensitive personal information ({sensitive_desc}). "
            f"Do you confirm you want me to remember this?",
            True,  # requires_confirmation
        )

    # 3. Transient-content filter (skip for project/decision/milestone/episodic)
    if cat_norm in {"personal", "preference", "fact"}:
        for pat in TRANSIENT_PATTERNS:
            if pat.match(trimmed):
                return (
                    False,
                    "That looks like a transient command or greeting, not a persistent fact or preference.",
                    False,
                )

    return True, "", False


def normalize_memory_content(content: str) -> str:
    """
    Cleans and canonicalises memory string for storage and deduplication.
    """
    if not content:
        return ""
    normalized = re.sub(r"\s+", " ", content).strip()
    # Remove command prefixes like "Remember that", "Please remember", etc.
    normalized = re.sub(
        r"^(?:please\s+)?(?:remember\s+that|remember\s+this|remember|note\s+that|keep\s+in\s+mind\s+that)\s+",
        "",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"^(?:user\s+prefers|i\s+prefer)\s+",
        "prefers ",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = normalized.rstrip(". ") + "." if normalized else ""
    return normalized.strip()


def calculate_jaccard_similarity(text1: str, text2: str) -> float:
    """
    Token-level Jaccard similarity between two texts (0.0–1.0) with basic stemming.
    """
    def _stem_tokens(text: str) -> set:
        tokens = re.findall(r"\w+", text.lower())
        stemmed = set()
        for t in tokens:
            if t.endswith("ing") and len(t) > 5:
                stemmed.add(t[:-3])
            elif t.endswith("s") and len(t) > 3:
                stemmed.add(t[:-1])
            else:
                stemmed.add(t)
        return stemmed

    tokens1 = _stem_tokens(text1)
    tokens2 = _stem_tokens(text2)
    if not tokens1 or not tokens2:
        return 0.0
    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)
    return intersection / union if union > 0 else 0.0


def is_preference_update(new_content: str) -> bool:
    """
    Returns True if the new content signals an update / change to an existing
    preference (e.g., "I now prefer TypeScript", "switched to Neovim").
    """
    for pat in PREFERENCE_UPDATE_SIGNALS:
        if pat.search(new_content):
            return True
    return False
