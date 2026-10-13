"""
Memory Retrieval Module for William-1 Persistent Memory Layer (v0.3+).

Improved ranking pipeline:
  1. Query intent analysis (skip pure factual questions).
  2. Keyword extraction.
  3. Composite scoring: keyword density + category match + recency
     (updated_at / last_accessed_at) + confidence.
  4. Token-budget cap so injected memory never bloats the prompt.
  5. Updates last_accessed_at on every retrieval.
  6. Cloud-transparency: terminal notice when memory goes to LLM.
  7. local_only guard: blocks memory context from leaving the machine.
"""

import re
import sys
import math
from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from memory.memory_store import MemoryStore
from memory.memory_settings import MemorySettings
from memory.project_memory import ProjectMemoryManager
from config import config

# ---------------------------------------------------------------------------
# Semantic Search Hook (DISABLED by default — Phase 5 plug-in point)
# ---------------------------------------------------------------------------
# When it becomes worth enabling:
#   - You have ≥500 memories (keyword search starts missing nuance)
#   - You've moved to a local LLM (Ollama/llama.cpp) so embeddings are free
#   - You want cross-lingual or paraphrase-robust retrieval
#
# To enable:
#   1. Set ENABLE_SEMANTIC_SEARCH=True in .env
#   2. Install: pip install sentence-transformers
#   3. Implement SemanticSearchBackend below.
#
# Interface contract (implement this class when ready):
#
# class SemanticSearchBackend:
#     def embed(self, text: str) -> List[float]: ...
#     def find_similar(self, query: str, candidates: List[Dict], top_k: int
#                     ) -> List[Tuple[float, Dict]]: ...
#
# Injecting it: pass an instance to MemoryRetrievalEngine(semantic_backend=...)
# The engine will call find_similar() before keyword scoring and merge results.

_SEMANTIC_BACKEND = None  # Populated at runtime if ENABLE_SEMANTIC_SEARCH=True


# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------
STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "did", "do",
    "does", "doing", "don't", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is",
    "isn't", "it", "its", "itself", "let's", "me", "more", "most", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "she", "should", "so",
    "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when", "where",
    "which", "while", "who", "whom", "why", "with", "would", "you", "your", "yours",
    "yourself", "yourselves", "tell", "william", "please", "just", "like",
}

# ---------------------------------------------------------------------------
# Query classification patterns
# ---------------------------------------------------------------------------
FACTUAL_QUERY_PATTERNS: List[re.Pattern] = [
    re.compile(r"^what\s+is\s+(?:a|an|the)\s+[\w\s]+(?:\?|$)", re.IGNORECASE),
    re.compile(r"^who\s+(?:is|was|were)\s+[\w\s]+(?:\?|$)", re.IGNORECASE),
    re.compile(r"^explain\s+(?:how|why|what|the)\s+[\w\s]+", re.IGNORECASE),
    re.compile(r"^why\s+(?:is|do|does|are)\s+[\w\s]+(?:\?|$)", re.IGNORECASE),
    re.compile(r"^how\s+(?:does|do|did|can)\s+[\w\s]+work(?:\?|$)", re.IGNORECASE),
    re.compile(r"^what\s+is\s+the\s+capital\s+of\b", re.IGNORECASE),
]

MEMORY_QUERY_PATTERNS: List[re.Pattern] = [
    re.compile(r"\b(?:remember|memory|memories|preference|preferences|recall)\b", re.IGNORECASE),
    re.compile(r"\b(?:continue|status|blocker|next task|milestone|decision)\b", re.IGNORECASE),
    re.compile(r"\b(?:should we|can we|what if we|how about|could we|switch to|let's use|use|consider)\b", re.IGNORECASE),
    re.compile(r"\b(?:why did we|why choose|why chose|why sqlite|why postgres|decision)\b", re.IGNORECASE),
    re.compile(r"\b(?:how is (?:my|the|our) project|how's my project|project health)\b", re.IGNORECASE),
    re.compile(r"\bwhat do you know about\b", re.IGNORECASE),
    re.compile(r"\bwhat was our last\b", re.IGNORECASE),
]

# Approximate chars-per-token ratio for budget estimation
_CHARS_PER_TOKEN = 4


class MemoryRetrievalEngine:
    """
    Search, score, cap, and format memories for LLM injection.
    Optionally integrates a semantic search backend (disabled by default).
    """

    def __init__(
        self,
        store: MemoryStore,
        project_manager: ProjectMemoryManager,
        settings: Optional[MemorySettings] = None,
        semantic_backend=None,  # SemanticSearchBackend instance or None
    ):
        self.store = store
        self.project_manager = project_manager
        self._settings = settings
        self._semantic = semantic_backend or _SEMANTIC_BACKEND

    @property
    def settings(self) -> MemorySettings:
        if self._settings is None:
            self._settings = MemorySettings(self.store)
        return self._settings

    # ------------------------------------------------------------------
    # Intent analysis
    # ------------------------------------------------------------------

    def should_retrieve_memory(self, user_query: str) -> bool:
        if not user_query or not user_query.strip():
            return False
        q = user_query.strip()
        for pat in MEMORY_QUERY_PATTERNS:
            if pat.search(q):
                return True
        for pat in FACTUAL_QUERY_PATTERNS:
            if pat.match(q):
                if not re.search(r"\b(?:my|our|i|me|we|william-1|this project)\b", q, re.IGNORECASE):
                    return False
        if re.search(r"\b(?:my|mine|our|remember|prefer|preference|favorite|project|william-1)\b", q, re.IGNORECASE):
            return True
        return False

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    def extract_keywords(self, query: str) -> List[str]:
        tokens = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", query.lower())
        return list(dict.fromkeys(t for t in tokens if t not in STOPWORDS))

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def score_memory(
        self,
        memory: Dict[str, Any],
        query_keywords: List[str],
        query_category: Optional[str] = None,
    ) -> float:
        """
        Composite score:
          - keyword match density (primary)
          - exact phrase bonus
          - category match bonus
          - recency (updated_at exponential decay)
          - access recency (last_accessed_at bonus)
          - confidence multiplier
        """
        content_lower = memory["content"].lower()
        matched = sum(1 for kw in query_keywords if kw in content_lower)
        if matched == 0:
            return 0.0

        score = matched * 2.5

        # Exact phrase bonus
        if query_keywords and " ".join(query_keywords) in content_lower:
            score += 3.0

        # Category match bonus
        if query_category and memory.get("category", "").lower() == query_category.lower():
            score += 2.0

        # Confidence
        score *= memory.get("confidence", 1.0)

        # Recency: updated_at (half-life ~14 days)
        try:
            updated_dt = datetime.fromisoformat(memory["updated_at"])
            days_ago = max(0.0, (datetime.now() - updated_dt).total_seconds() / 86400.0)
            score += math.exp(-0.05 * days_ago) * 1.5
        except Exception:
            pass

        # Access recency bonus
        try:
            if memory.get("last_accessed_at"):
                accessed_dt = datetime.fromisoformat(memory["last_accessed_at"])
                access_days = max(0.0, (datetime.now() - accessed_dt).total_seconds() / 86400.0)
                score += math.exp(-0.1 * access_days) * 0.8
        except Exception:
            pass

        return score

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search_memories(
        self,
        query: str,
        category: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Keyword-based search + composite scoring, capped at top_k.
        """
        top_k = top_k or self.settings.top_k
        keywords = self.extract_keywords(query)
        if not keywords:
            return []

        # Fetch a generous set, then score in Python
        all_mems = self.store.list_memories(category=category, limit=200)

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for mem in all_mems:
            s = self.score_memory(mem, keywords, query_category=category)
            if s >= config.MEMORY_MIN_CONFIDENCE:
                scored.append((s, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:top_k]]

    # ------------------------------------------------------------------
    # Token-budget cap
    # ------------------------------------------------------------------

    def _apply_token_budget(
        self, items: List[str], budget_chars: int
    ) -> List[str]:
        """
        Trims item list until total character count fits within budget_chars.
        """
        result, total = [], 0
        for item in items:
            if total + len(item) > budget_chars:
                break
            result.append(item)
            total += len(item) + 2  # +2 for "\n• "
        return result

    # ------------------------------------------------------------------
    # Context retrieval (called by MemoryManager before LLM)
    # ------------------------------------------------------------------

    def retrieve_context(self, user_query: str) -> Optional[str]:
        """
        High-level retrieval: analyse → search → score → cap → format.
        Returns None when there's nothing relevant or retrieval is skipped.
        Prints a terminal notice whenever memory context is prepared for LLM.
        """
        if not self.should_retrieve_memory(user_query):
            return None

        keywords = self.extract_keywords(user_query)
        context_items: List[str] = []

        # 1. Project continuity + rejected-design + decision provenance
        is_project_q = bool(
            re.search(
                r"\b(?:project|william-1|william|continue|blocker|next task|stack|health|going|how is)\b",
                user_query, re.IGNORECASE,
            )
        )
        is_decision_q = bool(
            re.search(
                r"\b(?:why|chose|chosen|rationale|reason|decision|decided|pick|picked|went with)\b",
                user_query, re.IGNORECASE,
            )
        )

        # Identify active project from query or fall back to William-1
        active_project_name: Optional[str] = None
        for p in self.project_manager.list_projects():
            if p["name"].lower() in user_query.lower():
                active_project_name = p["name"]
                break
        if not active_project_name:
            active_project_name = "William-1"

        if is_project_q:
            briefing = self.project_manager.get_project_continuity_briefing(active_project_name)
            if briefing.get("found"):
                context_items.append(
                    f"PROJECT RECORD [{active_project_name}]: {briefing['message']}"
                )

        if is_decision_q:
            matches = self.project_manager.search_project_decisions(
                active_project_name, user_query, limit=3
            )
            for ev in matches:
                try:
                    date_str = datetime.fromisoformat(ev["created_at"]).strftime("%b %d, %Y")
                except Exception:
                    date_str = "unknown date"
                context_items.append(
                    f"DECISION [{date_str}]: {ev['summary']}"
                )

        # 2. Rejected-design check (proactively flag if query proposes something ruled out)
        is_proposal_q = bool(
            re.search(
                r"\b(?:what if we|should we|can we|let's use|use|try|switch to|add|build with)\b",
                user_query, re.IGNORECASE,
            )
        )
        if is_proposal_q:
            rejected = self.project_manager.find_rejected_designs(
                active_project_name, user_query
            )
            if rejected:
                warning = self.project_manager.format_rejection_warning(rejected)
                context_items.insert(0, f"REJECTED DESIGN WARNING: {warning}")

        # 3. General memories (keyword + optional semantic)
        top_k = self.settings.top_k
        budget_chars = self.settings.max_token_budget * _CHARS_PER_TOKEN

        if self._semantic:
            # Semantic backend: find_similar() returns (score, memory_dict) pairs
            candidates = self.store.list_memories(limit=500)
            sem_results = self._semantic.find_similar(user_query, candidates, top_k=top_k)
            matched_mems = [m for _, m in sem_results]
        else:
            matched_mems = self.search_memories(user_query, top_k=top_k)

        for mem in matched_mems:
            cat = mem.get("category", "personal").capitalize()
            context_items.append(f"{cat}: {mem['content']}")
            self.store.touch_memory_accessed(mem["id"])

        if not context_items:
            return None

        # 4. Token budget cap
        capped = self._apply_token_budget(context_items, budget_chars)

        # 5. Build context block
        context_block = "[RELEVANT MEMORY (v0.3+)]\n" + "\n".join(f"• {item}" for item in capped)

        # 6. Cloud-transparency notice
        local_only = self.settings.local_only
        if local_only:
            print("\033[93m[Memory] local_only=true — memory context suppressed from cloud LLM.\033[0m")
            return None

        count = len(capped)
        print(f"\033[96m[Memory] Recalled {count} memor{'y' if count == 1 else 'ies'} -> sending to LLM context.\033[0m")
        return context_block
