"""
Project Memory Module for William-1 Persistent Memory Layer (v0.3+).

Manages structured project tracking (status, stack, blockers, next tasks)
and chronological milestone / decision events for cross-session continuity.

v0.3+ enhancements:
  - Rich continuity briefing with staleness detection and traceable sources
  - Decision provenance: "Why did we choose SQLite?" → event record + date
  - Rejected-design awareness: flags when user re-proposes a ruled-out idea
  - Project health summary with open blockers + completion progress
  - Milestone counting and phase tracking
"""

import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from memory.memory_store import MemoryStore


# ---------------------------------------------------------------------------
# Event type classifications
# ---------------------------------------------------------------------------
DECISION_EVENT_TYPES = {"decision", "choice", "rationale", "architecture"}
REJECTED_EVENT_TYPES = {"rejected", "ruled_out", "discarded", "won't_do", "wont_do", "rejection"}
MILESTONE_EVENT_TYPES = {"milestone", "completed", "shipped", "done", "released"}


class ProjectMemoryManager:
    """
    Manages structured project states and milestone events.
    Guarantees strict truthfulness: if no records exist, reports so cleanly.
    Never invents or infers data that wasn't explicitly saved.
    """

    def __init__(self, store: MemoryStore):
        self.store = store

    # ------------------------------------------------------------------
    # Basic CRUD
    # ------------------------------------------------------------------

    def get_project(self, project_name: str) -> Optional[Dict[str, Any]]:
        """Retrieves a project record by name."""
        return self.store.get_project(project_name)

    def list_projects(self) -> List[Dict[str, Any]]:
        """Lists all recorded projects."""
        return self.store.list_projects()

    def update_project(
        self,
        name: str,
        description: Optional[str] = None,
        status: Optional[str] = None,
        technology_stack: Optional[str] = None,
        current_blocker: Optional[str] = None,
        next_task: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates or updates a project record."""
        return self.store.upsert_project(
            name=name,
            description=description,
            status=status,
            technology_stack=technology_stack,
            current_blocker=current_blocker,
            next_task=next_task,
        )

    def record_event(self, project_name: str, event_type: str, summary: str) -> Dict[str, Any]:
        """
        Records a project event (e.g., 'milestone', 'decision', 'rejected', 'fix').
        Creates the project if it doesn't already exist.
        """
        project = self.store.get_project(project_name)
        if not project:
            project = self.store.upsert_project(name=project_name)

        event_id = self.store.add_project_event(
            project_id=project["id"],
            event_type=event_type,
            summary=summary,
        )
        return {
            "event_id": event_id,
            "project_name": project_name,
            "event_type": event_type,
            "summary": summary,
        }

    def delete_project_and_memories(self, project_name: str) -> Dict[str, Any]:
        """Deletes a project record, its events, and any associated keyword memories."""
        project = self.store.get_project(project_name)
        if not project:
            return {"success": False, "message": f"No project found named '{project_name}'."}

        deleted_project = self.store.delete_project(project_name)
        deleted_memories = self.store.delete_memories_matching(project_name)

        return {
            "success": deleted_project,
            "message": f"Deleted project '{project_name}', its event timeline, and {deleted_memories} related memory records.",
            "deleted_memories_count": deleted_memories,
        }

    # ------------------------------------------------------------------
    # Decision provenance
    # ------------------------------------------------------------------

    def search_project_decisions(
        self, project_name: str, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Searches recorded project events for decision rationale.
        Returns matching events with their dates so William can cite provenance.

        Use for: "Why did we choose SQLite?", "What was the rationale for X?"
        """
        project = self.store.get_project(project_name)
        if not project:
            return []

        all_events = self.store.get_project_events(project["id"], limit=200)
        query_words = set(re.findall(r"\b[a-z]{2,}\b", query.lower()))
        query_words -= {"why", "did", "we", "choose", "the", "use", "used", "what", "how",
                       "when", "where", "which", "reason", "rationale", "decision", "our"}

        scored: List[Tuple[float, Dict[str, Any]]] = []
        for ev in all_events:
            ev_words = set(re.findall(r"\b[a-z]{2,}\b", ev["summary"].lower()))
            overlap = len(query_words & ev_words)
            if overlap == 0:
                continue
            # Boost decision/rationale event types
            type_boost = 1.5 if ev["event_type"].lower() in DECISION_EVENT_TYPES else 1.0
            scored.append((overlap * type_boost, ev))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ev for _, ev in scored[:limit]]

    # ------------------------------------------------------------------
    # Rejected-design awareness
    # ------------------------------------------------------------------

    def find_rejected_designs(
        self, project_name: str, proposal: str
    ) -> Optional[Dict[str, Any]]:
        """
        Checks if a proposal matches a previously rejected design.
        Returns the rejection event if found, or None.

        Use for: flagging "We ruled this out on <date> because <reason>"
        """
        project = self.store.get_project(project_name)
        if not project:
            return None

        all_events = self.store.get_project_events(project["id"], limit=200)
        proposal_words = set(re.findall(r"\b[a-z]{2,}\b", proposal.lower()))
        proposal_words -= {"a", "an", "the", "we", "i", "to", "of", "in", "for",
                          "use", "using", "with", "should", "could", "would", "want"}

        best_score, best_ev = 0.0, None
        for ev in all_events:
            if ev["event_type"].lower() not in REJECTED_EVENT_TYPES:
                continue
            ev_words = set(re.findall(r"\b[a-z]{2,}\b", ev["summary"].lower()))
            overlap = len(proposal_words & ev_words)
            density = overlap / max(len(proposal_words), 1)
            if density > 0.35 and overlap > best_score:
                best_score = overlap
                best_ev = ev

        return best_ev

    def format_rejection_warning(self, rejected_event: Dict[str, Any]) -> str:
        """
        Returns a spoken warning about a previously rejected idea, with date.
        Format: "We ruled this out on <date> because <summary> — want to reconsider?"
        """
        try:
            ts = datetime.fromisoformat(rejected_event["created_at"])
            date_str = ts.strftime("%B %d, %Y")
        except Exception:
            date_str = "a previous session"

        summary = rejected_event["summary"]
        return (
            f"Heads up — we ruled this out on {date_str}: {summary}. "
            f"Want to reconsider it now?"
        )

    # ------------------------------------------------------------------
    # Project continuity briefing (richly sourced)
    # ------------------------------------------------------------------

    def get_project_continuity_briefing(self, project_name: str) -> Dict[str, Any]:
        """
        Builds a synthesized project continuity briefing for "Continue William-1".

        Every item is traceable to its source record.
        If data is missing, explicitly says "I don't have that saved" for that field.
        Never invents or infers data.
        """
        project = self.store.get_project(project_name)
        if not project:
            return {
                "found": False,
                "message": (
                    f"I don't have any saved project records for '{project_name}' yet. "
                    f"Would you like me to start tracking it?"
                ),
                "data": None,
            }

        all_events = self.store.get_project_events(project["id"], limit=100)
        milestones = [e for e in all_events if e["event_type"].lower() in MILESTONE_EVENT_TYPES]
        decisions = [e for e in all_events if e["event_type"].lower() in DECISION_EVENT_TYPES]
        rejections = [e for e in all_events if e["event_type"].lower() in REJECTED_EVENT_TYPES]

        parts = []
        sources = {}  # field → source record reference

        # Project name & status
        p_name = project["name"]
        p_status = project.get("status") or "active"
        parts.append(f"Project: {p_name}. Status: {p_status}.")
        sources["status"] = f"projects.{project['id']}.status (updated {project.get('updated_at','')[:10]})"

        # Technology stack
        if project.get("technology_stack") and project["technology_stack"].strip():
            parts.append(f"Stack: {project['technology_stack']}.")
            sources["stack"] = f"projects.{project['id']}.technology_stack"
        else:
            parts.append("Stack: I don't have that saved.")

        # Last milestone
        if milestones:
            last_ms = milestones[0]
            try:
                ms_date = datetime.fromisoformat(last_ms["created_at"]).strftime("%b %d")
            except Exception:
                ms_date = "unknown date"
            parts.append(f"Last milestone ({ms_date}): {last_ms['summary']}.")
            sources["last_milestone"] = f"project_events.{last_ms['id']}"
        else:
            parts.append("Last milestone: I don't have that saved.")

        # Current blocker
        if project.get("current_blocker") and project["current_blocker"].strip():
            parts.append(f"Current blocker: {project['current_blocker']}.")
            sources["blocker"] = f"projects.{project['id']}.current_blocker"
        else:
            parts.append("Current blocker: none recorded.")

        # Key decisions (up to 2)
        if decisions:
            dec_summaries = [f"\"{d['summary'][:60]}\"" for d in decisions[:2]]
            parts.append(f"Key decisions: {'; '.join(dec_summaries)}.")
            sources["decisions"] = [f"project_events.{d['id']}" for d in decisions[:2]]
        else:
            parts.append("Key decisions: I don't have any saved.")

        # Next task
        if project.get("next_task") and project["next_task"].strip():
            parts.append(f"Recommended next: {project['next_task']}.")
            sources["next_task"] = f"projects.{project['id']}.next_task"
        else:
            parts.append("Next task: I don't have that saved.")

        # Staleness
        try:
            updated_dt = datetime.fromisoformat(project["updated_at"])
            days_stale = (datetime.now() - updated_dt).days
            if days_stale > 7:
                parts.append(f"Note: no updates in {days_stale} days.")
        except Exception:
            pass

        return {
            "found": True,
            "message": " ".join(parts),
            "sources": sources,
            "data": {
                "project": project,
                "events": all_events[:10],
                "milestones": milestones[:5],
                "decisions": decisions[:5],
                "rejections": rejections[:5],
            },
        }

    # ------------------------------------------------------------------
    # Project health summary
    # ------------------------------------------------------------------

    def get_project_health(self, project_name: str) -> Dict[str, Any]:
        """
        "How's my project going?" — synthesizes status, milestones,
        open blockers, staleness into one natural paragraph + suggested next step.
        Never invents information. All items sourced from saved records.
        """
        project = self.store.get_project(project_name)
        if not project:
            return {
                "found": False,
                "message": f"I don't have any saved records for '{project_name}'.",
            }

        all_events = self.store.get_project_events(project["id"], limit=100)
        milestones = [e for e in all_events if e["event_type"].lower() in MILESTONE_EVENT_TYPES]
        open_blockers = []
        if project.get("current_blocker") and project["current_blocker"].strip():
            open_blockers.append(project["current_blocker"])

        # Staleness
        try:
            updated_dt = datetime.fromisoformat(project["updated_at"])
            days_stale = max(0, (datetime.now() - updated_dt).days)
        except Exception:
            days_stale = 0

        # Build paragraph
        parts = []
        status = project.get("status") or "active"
        parts.append(f"{project['name']} is {status}.")

        if milestones:
            parts.append(f"You've completed {len(milestones)} recorded milestone(s).")
            parts.append(f"Most recent: {milestones[0]['summary'][:80]}.")
        else:
            parts.append("No milestones recorded yet.")

        if open_blockers:
            parts.append(f"Open blocker: {open_blockers[0]}.")
        else:
            parts.append("No current blocker recorded.")

        if days_stale > 7:
            parts.append(f"The record hasn't been updated in {days_stale} days — you may want to refresh the status.")
        elif days_stale <= 1:
            parts.append("The record is up to date.")

        next_task = project.get("next_task", "").strip()
        if next_task:
            parts.append(f"Suggested next step: {next_task}.")
        else:
            parts.append("No next step recorded.")

        return {
            "found": True,
            "message": " ".join(parts),
            "data": {
                "project": project,
                "milestone_count": len(milestones),
                "open_blockers": open_blockers,
                "days_since_update": days_stale,
            },
        }

    # ------------------------------------------------------------------
    # Memory-powered path resolution
    # ------------------------------------------------------------------

    def resolve_project_path(self, project_name: str) -> Optional[str]:
        """
        Returns the saved folder path for a project if one is recorded
        in the project description or stack fields (looks for path-like strings).
        Used by "Open my William-1 project" to resolve the folder without guessing.
        """
        project = self.store.get_project(project_name)
        if not project:
            return None

        # Look for Windows or POSIX paths in description or stack fields
        for field in ("description", "technology_stack", "next_task"):
            val = project.get(field) or ""
            # Match C:\..., /home/..., ~/...
            path_match = re.search(
                r'(?:[A-Za-z]:\\[^\s"\']+|/[^\s"\']{3,}|~[^\s"\']+)', val
            )
            if path_match:
                return path_match.group(0)

        # Also check memory records tagged with this project
        return None
