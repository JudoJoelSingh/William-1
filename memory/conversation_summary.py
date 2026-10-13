"""
Conversation Summary Module for William-1 Persistent Memory Layer (v0.3+).

End-of-session summary pipeline:
  1. Collect session events (decisions recorded, tasks done, topics discussed).
  2. Build a concise episodic summary (rule-based; LLM hook available).
  3. Show summary to user for approval before saving.
  4. Save with a retention date derived from memory_settings.retention_days.
  5. At next startup, optionally offer a "Last time we..." recap.

Raw transcripts are NEVER stored — only the approved summary.
"""

import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from memory.memory_store import MemoryStore
from config import config


class ConversationSummaryManager:
    """
    Manages episodic conversation summaries with time-bounded retention.
    Provides "last time we..." recap for session continuity.
    """

    def __init__(self, store: MemoryStore):
        self.store = store
        self._session_id: str = str(uuid.uuid4())
        self._session_events: List[str] = []   # ephemeral, never persisted

    # ------------------------------------------------------------------
    # Session event accumulation (in-memory only, never saved raw)
    # ------------------------------------------------------------------

    def note_session_event(self, description: str) -> None:
        """
        Records an in-session event description for later summarisation.
        These are ephemeral — only the final approved summary is persisted.
        """
        if description and len(self._session_events) < 50:
            self._session_events.append(description.strip())

    def clear_session_events(self) -> None:
        """Clears in-session event notes (e.g., after session ends)."""
        self._session_events.clear()

    # ------------------------------------------------------------------
    # Summary generation (rule-based; LLM hook described below)
    # ------------------------------------------------------------------

    def generate_session_summary(
        self,
        project_name: Optional[str] = None,
        extra_context: Optional[str] = None,
    ) -> str:
        """
        Builds a concise episodic summary from this session's noted events.

        Implementation note — semantic enrichment hook:
            If you later integrate a local LLM (Phase 5), call it here:
            ```
            if config.ENABLE_LOCAL_LLM:
                return local_llm.summarize(self._session_events, project_name)
            ```
            For now we use deterministic rule-based assembly, which is
            accurate and always traceable.

        Returns a 2–4 sentence summary string ready for user approval.
        Raw event notes are NEVER saved — only this approved string is.
        """
        now = datetime.now()
        date_str = now.strftime("%B %d, %Y")
        events = self._session_events

        if not events:
            base = f"Session on {date_str}."
            if project_name:
                base += f" Project worked on: {project_name}."
            if extra_context:
                base += f" {extra_context}"
            return base

        # Deduplicate while preserving order
        seen = set()
        unique_events = []
        for ev in events:
            ev_lower = ev.lower()
            if ev_lower not in seen:
                seen.add(ev_lower)
                unique_events.append(ev)

        # Classify events
        decisions = [e for e in unique_events if any(w in e.lower() for w in
                     ("decided", "chose", "choice", "selected", "rationale", "because", "architecture"))]
        tasks_done = [e for e in unique_events if any(w in e.lower() for w in
                      ("completed", "finished", "implemented", "fixed", "shipped", "done", "wrote", "built"))]
        blockers = [e for e in unique_events if any(w in e.lower() for w in
                    ("blocker", "blocked", "issue", "problem", "error", "fail", "stuck"))]

        parts = [f"Session on {date_str}."]

        if project_name:
            parts.append(f"Worked on: {project_name}.")

        if tasks_done:
            tasks_summary = "; ".join(t[:80] for t in tasks_done[:3])
            parts.append(f"Completed: {tasks_summary}.")

        if decisions:
            dec_summary = "; ".join(d[:80] for d in decisions[:2])
            parts.append(f"Decisions: {dec_summary}.")

        if blockers:
            bl_summary = blockers[0][:80]
            parts.append(f"Open: {bl_summary}.")

        # What's next (last non-classified event as a proxy)
        non_classified = [e for e in unique_events if e not in tasks_done + decisions + blockers]
        if non_classified:
            parts.append(f"Next focus: {non_classified[-1][:80]}.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Approval + persistence
    # ------------------------------------------------------------------

    def save_session_summary(
        self,
        summary: str,
        session_id: Optional[str] = None,
        retention_days: Optional[int] = None,
    ) -> int:
        """
        Saves a concise session summary with a retention expiration date.
        Only call after the user has approved the summary.
        Raw transcripts are NEVER saved here.
        """
        sid = session_id or self._session_id
        days = retention_days if retention_days is not None else config.MEMORY_EPISODIC_RETENTION_DAYS
        retention_until = (
            (datetime.now() + timedelta(days=days)).isoformat() if days > 0 else None
        )
        return self.store.insert_conversation_summary(
            session_id=sid,
            summary=summary.strip(),
            retention_until=retention_until,
        )

    def save_approved_summary(
        self,
        project_name: Optional[str] = None,
        extra_context: Optional[str] = None,
        retention_days: Optional[int] = None,
    ) -> Tuple[str, int]:
        """
        Full end-of-session pipeline:
        generate → display (for user approval — caller is responsible for prompting)
        → save.  Returns (summary_text, record_id).
        """
        summary = self.generate_session_summary(
            project_name=project_name, extra_context=extra_context
        )
        record_id = self.save_session_summary(
            summary=summary, retention_days=retention_days
        )
        self.clear_session_events()
        return summary, record_id

    # ------------------------------------------------------------------
    # Retrieval — "last time we..." recap
    # ------------------------------------------------------------------

    def get_recent_summaries(self, limit: int = 3) -> List[Dict[str, Any]]:
        """Retrieves recent conversation summaries."""
        return self.store.list_recent_summaries(limit=limit)

    def get_last_session_recap(self) -> Optional[str]:
        """
        Returns a short spoken recap for the "last time we..." startup message.
        Returns None if no previous summaries exist.
        """
        summaries = self.store.list_recent_summaries(limit=1)
        if not summaries:
            return None

        last = summaries[0]
        summary_text = last["summary"]
        created_at = last.get("created_at", "")

        try:
            ts = datetime.fromisoformat(created_at)
            # How long ago?
            delta = datetime.now() - ts
            if delta.days == 0:
                time_str = "earlier today"
            elif delta.days == 1:
                time_str = "yesterday"
            elif delta.days < 7:
                time_str = f"{delta.days} days ago"
            else:
                time_str = ts.strftime("%B %d")
        except Exception:
            time_str = "last session"

        # Keep the recap brief (first 2 sentences)
        sentences = summary_text.split(". ")
        brief = ". ".join(sentences[:2])
        if not brief.endswith("."):
            brief += "."

        return f"Last time ({time_str}): {brief}"
