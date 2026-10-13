"""Helper script to inject companion methods into memory_manager.py."""
import os

NEW_CODE = """
    # ------------------------------------------------------------------
    # Session event tracking (in-memory, never persisted raw)
    # ------------------------------------------------------------------

    def note_session_event(self, description: str) -> None:
        \"\"\"Adds an event description to the current session's accumulator.\"\"\"
        self.conversation_summary.note_session_event(description)

    # ------------------------------------------------------------------
    # Companion: project continuity
    # ------------------------------------------------------------------

    def continue_project(self, project_name: str = "William-1") -> dict:
        \"\"\"Crisp briefing: phase, milestone, blocker, decisions, next task. Fully sourced.\"\"\"
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        briefing = self.project_memory.get_project_continuity_briefing(project_name)
        if briefing.get("found"):
            _mem_print("\U0001f50d", f"Project briefing for '{project_name}'.")
        return {
            "success": briefing.get("found", False),
            "message": briefing["message"],
            "sources": briefing.get("sources", {}),
            "data": briefing.get("data"),
        }

    # ------------------------------------------------------------------
    # Companion: decision provenance
    # ------------------------------------------------------------------

    def why_decision(self, query: str, project_name: str = "William-1") -> dict:
        \"\"\"Retrieves decision records with date + context. Honest if nothing saved.\"\"\"
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        from datetime import datetime as _dt
        matches = self.project_memory.search_project_decisions(project_name, query, limit=3)
        if not matches:
            return {
                "success": True,
                "message": f"I don't have any saved decisions about that for '{project_name}'.",
                "events": [],
            }
        parts = []
        for ev in matches:
            try:
                date_str = _dt.fromisoformat(ev["created_at"]).strftime("%B %d, %Y")
            except Exception:
                date_str = "an earlier session"
            parts.append(f"On {date_str}: {ev['summary']}")
        _mem_print("\U0001f50d", f"Found {len(matches)} decision record(s).")
        return {"success": True, "message": " | ".join(parts), "events": matches}

    # ------------------------------------------------------------------
    # Companion: project health
    # ------------------------------------------------------------------

    def project_health(self, project_name: str = "William-1") -> dict:
        \"\"\"Synthesizes status, milestones, blockers, staleness. Honest if nothing saved.\"\"\"
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        result = self.project_memory.get_project_health(project_name)
        if result.get("found"):
            _mem_print("\U0001f50d", f"Project health for '{project_name}'.")
        return {"success": result.get("found", False), "message": result["message"], "data": result.get("data")}

    # ------------------------------------------------------------------
    # Companion: record project event
    # ------------------------------------------------------------------

    def record_project_event(self, project_name: str, event_type: str, summary: str) -> dict:
        \"\"\"Records a timestamped project event (milestone, decision, rejected, fix).\"\"\"
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        from utils.logger import AuditLogger as _AL
        event_type_clean = event_type.lower().strip()
        result = self.project_memory.record_event(project_name, event_type_clean, summary)
        indicator = "\U0001f4be" if event_type_clean in {"milestone", "completed"} else "\u270f\ufe0f"
        _mem_print(indicator, f"[{project_name}] {event_type_clean}: {summary[:60]}")
        _AL.log(
            user_request="user", tool_name="record_project_event",
            arguments={"project": project_name, "type": event_type_clean, "summary": summary},
            result=f"Event {result['event_id']} recorded", status="EXECUTED", permission_level="LEVEL_1_SAFE",
        )
        return {"success": True, "message": f"Recorded {event_type_clean} for '{project_name}': {summary}", "event_id": result["event_id"]}

    # ------------------------------------------------------------------
    # Companion: session summary
    # ------------------------------------------------------------------

    def generate_session_summary(self, project_name=None, approved: bool = False, extra_context=None) -> dict:
        \"\"\"End-of-session summary. approved=False for draft, True to persist. No raw transcripts saved.\"\"\"
        summary = self.conversation_summary.generate_session_summary(project_name=project_name, extra_context=extra_context)
        if not approved:
            return {"success": True, "message": f"Session summary draft:\\n{summary}", "summary": summary, "saved": False}
        record_id = self.conversation_summary.save_session_summary(
            summary=summary, retention_days=self.settings.retention_days
        )
        self.conversation_summary.clear_session_events()
        _mem_print("\U0001f4be", f"Session summary saved (record {record_id}).")
        from utils.logger import AuditLogger as _AL
        _AL.log(
            user_request="user", tool_name="generate_session_summary",
            arguments={"project_name": project_name, "approved": True},
            result=f"Session summary saved as record {record_id}", status="EXECUTED", permission_level="LEVEL_1_SAFE",
        )
        return {"success": True, "message": f"Saved. {summary}", "summary": summary, "record_id": record_id, "saved": True}

    def get_last_session_recap(self):
        \"\"\"Short 'Last time we...' recap. None if no previous sessions.\"\"\"
        return self.conversation_summary.get_last_session_recap()

    # ------------------------------------------------------------------
    # Companion: memory-powered tool intelligence
    # ------------------------------------------------------------------

    def resolve_open_project_from_memory(self, project_name: str) -> dict:
        \"\"\"Resolves folder path from saved project data for open_folder tool calls.\"\"\"
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        path = self.project_memory.resolve_project_path(project_name)
        if path:
            _mem_print("\U0001f50d", f"Resolved '{project_name}' -> {path}")
            return {"success": True, "message": f"Found saved path: {path}", "path": path}
        import re as _re
        results = self.retrieval.search_memories(f"{project_name} folder path directory", top_k=3)
        for mem in results:
            m = _re.search(r'(?:[A-Za-z]:\\\\[^\\s\\'\"]+|/[^\\s\\'\"]{3,}|~[^\\s\\'\\"]+)', mem["content"])
            if m:
                _mem_print("\U0001f50d", f"Path found in memory: {m.group(0)}")
                return {"success": True, "message": f"Found path in memory: {m.group(0)}", "path": m.group(0)}
        return {
            "success": False,
            "message": f"I don't have a saved path for '{project_name}'. "
                       f"Try: 'Remember that my {project_name} folder is at C:\\\\Users\\\\...'.",
        }

    def resolve_recent_project_from_episodic(self):
        \"\"\"Identifies most-recently worked-on project from episodic summaries.\"\"\"
        recent = self.conversation_summary.get_recent_summaries(limit=3)
        if not recent:
            return None
        projects = self.project_memory.list_projects()
        for s in recent:
            text = s.get("summary", "").lower()
            for p in projects:
                if p["name"].lower() in text:
                    return p["name"]
        return None

"""

path = r"c:\Users\judoj\OneDrive\Documents\William-1\memory\memory_manager.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

marker = "# ---------------------------------------------------------------------------\n# Application-wide singleton"
if marker in content:
    content = content.replace(marker, NEW_CODE + "\n" + marker)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("OK: companion methods injected")
else:
    # Try CRLF variant
    marker_crlf = "# ---------------------------------------------------------------------------\r\n# Application-wide singleton"
    if marker_crlf in content:
        content = content.replace(marker_crlf, NEW_CODE.replace("\n", "\r\n") + "\r\n" + marker_crlf)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("OK: companion methods injected (CRLF)")
    else:
        print("MARKER NOT FOUND")
        # Show what's near the end
        print(repr(content[-300:]))
