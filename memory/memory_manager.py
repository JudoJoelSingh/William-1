"""
Memory Manager for William-1 Persistent Memory Layer (v0.3+).

Public orchestrator for all memory operations:
  - Working memory (ephemeral in-session context)
  - Personal memory (SQLite: facts, preferences)
  - Project memory (SQLite: project records + event timelines)
  - Episodic memory (SQLite: session summaries)
  - Settings: on/off, auto-capture, confirm-before-save, retention, local_only, etc.
  - Lifecycle: capture → policy → deduplicate/update → store
  - Retrieval: score → cap → inject into prompt
  - Inspection/control: list-all, show-project, export/import JSON
  - Startup cleanup: expires_at, retention_until
  - Ambiguity guard on destructive commands
  - Audit logging for every memory change
  - Terminal UX indicators: 💾 Saved  ✏️ Updated  🔍 Recalled  🗑️ Forgotten
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from config import config
from memory.memory_store import MemoryStore
from memory.memory_settings import MemorySettings
from memory.memory_policy import (
    is_valid_memory_candidate,
    normalize_memory_content,
    contains_secrets,
    calculate_jaccard_similarity,
    is_preference_update,
)
from memory.project_memory import ProjectMemoryManager
from memory.conversation_summary import ConversationSummaryManager
from memory.memory_retrieval import MemoryRetrievalEngine
from utils.logger import AuditLogger


# ---------------------------------------------------------------------------
# Terminal colour helpers (ANSI — degrades gracefully on no-colour terminals)
# ---------------------------------------------------------------------------

def _mem_print(indicator: str, message: str) -> None:
    """Print a colour-coded memory event indicator to the terminal."""
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"

    colour = {
        "💾": GREEN,
        "✏️": YELLOW,
        "🔍": CYAN,
        "🗑️": RED,
        "⚠️": YELLOW,
        "🔒": RED,
    }.get(indicator, "")
    try:
        print(f"{colour}{indicator} {message}{RESET}")
    except UnicodeEncodeError:
        tag = {
            "💾": "[SAVED]",
            "✏️": "[UPDATED]",
            "🔍": "[RECALLED]",
            "🗑️": "[FORGOTTEN]",
            "⚠️": "[WARNING]",
            "🔒": "[BLOCKED]",
        }.get(indicator, "[MEMORY]")
        print(f"{tag} {message}")


# ---------------------------------------------------------------------------
# Working Memory
# ---------------------------------------------------------------------------

class WorkingMemory:
    """Ephemeral in-session context: active task, project, recent topics."""

    def __init__(self):
        self.active_task: Optional[str] = None
        self.active_project: Optional[str] = "William-1"
        self.recent_topics: List[str] = []

    def set_active_task(self, task: str):
        self.active_task = task

    def set_active_project(self, project: str):
        self.active_project = project

    def add_topic(self, topic: str):
        if topic not in self.recent_topics:
            self.recent_topics.append(topic)
            if len(self.recent_topics) > 5:
                self.recent_topics.pop(0)

    def clear(self):
        self.active_task = None
        self.active_project = None
        self.recent_topics.clear()


# ---------------------------------------------------------------------------
# Memory Manager
# ---------------------------------------------------------------------------

class MemoryManager:
    """
    Public API for all William-1 memory operations.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.store = MemoryStore(db_path=db_path)
        self.settings = MemorySettings(self.store)
        self.project_memory = ProjectMemoryManager(self.store)
        self.conversation_summary = ConversationSummaryManager(self.store)
        self.retrieval = MemoryRetrievalEngine(self.store, self.project_memory, self.settings)
        self.working_memory = WorkingMemory()
        # Startup cleanup
        self._run_startup_cleanup()

    # ------------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------------

    def _run_startup_cleanup(self) -> None:
        """Purge expired memories and outdated episodic summaries at startup."""
        expired_mems = self.store.purge_expired_memories()
        expired_sums = self.store.purge_expired_summaries()
        if expired_mems or expired_sums:
            _mem_print(
                "🗑️",
                f"Startup cleanup: expired {expired_mems} memory record(s), {expired_sums} summary(ies).",
            )
            AuditLogger.log(
                user_request="startup",
                tool_name="memory_cleanup",
                arguments={"expired_memories": expired_mems, "expired_summaries": expired_sums},
                result="Startup expiry cleanup complete",
                status="EXECUTED",
                permission_level="LEVEL_1_SAFE",
            )

    # ------------------------------------------------------------------
    # Guard: is memory on?
    # ------------------------------------------------------------------

    def is_memory_enabled(self) -> bool:
        if not config.ENABLE_MEMORY:
            return False
        return self.settings.memory_enabled

    # ------------------------------------------------------------------
    # Settings management
    # ------------------------------------------------------------------

    def set_memory_mode(self, enabled: bool) -> Dict[str, Any]:
        """Enable or disable persistent memory entirely."""
        self.settings.memory_enabled = enabled
        label = "enabled" if enabled else "disabled"
        _mem_print("💾", f"Memory {label}.")
        AuditLogger.log(
            user_request="user",
            tool_name="set_memory_mode",
            arguments={"enabled": enabled},
            result=f"Memory {label}",
            status="EXECUTED",
            permission_level="LEVEL_1_SAFE",
        )
        return {"success": True, "message": f"Persistent memory has been {label}.", "enabled": enabled}

    def configure_memory(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Bulk-update memory settings.
        e.g. configure_memory({"top_k": 5, "local_only": True})
        """
        applied = self.settings.apply_dict(updates)
        msg = f"Updated memory settings: {', '.join(applied)}." if applied else "No recognised settings to update."
        _mem_print("💾", msg)
        AuditLogger.log(
            user_request="user",
            tool_name="configure_memory",
            arguments=updates,
            result=msg,
            status="EXECUTED",
            permission_level="LEVEL_1_SAFE",
        )
        return {"success": bool(applied), "message": msg, "applied": applied, "current": self.settings.as_dict()}

    def get_memory_settings(self) -> Dict[str, Any]:
        """Return current memory settings."""
        return {"success": True, "settings": self.settings.as_dict()}

    # ------------------------------------------------------------------
    # Save / capture
    # ------------------------------------------------------------------

    def save_memory(
        self,
        content: str,
        category: str = "personal",
        source: str = "user",
        confirmed: bool = False,
    ) -> Dict[str, Any]:
        """
        Full lifecycle: evaluate → policy → deduplicate/update → store.

        confirmed=True must be passed when the user has explicitly approved
        storage of sensitive personal information.
        """
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is currently disabled."}

        # 1. Policy evaluation
        valid, reason, requires_confirm = is_valid_memory_candidate(content, category, confirmed=confirmed)
        if not valid:
            if requires_confirm:
                # Signal upward that confirmation is needed
                return {
                    "success": False,
                    "requires_confirmation": True,
                    "message": reason,
                }
            # Hard block (credential or policy rejection)
            _mem_print("🔒", reason)
            AuditLogger.log(
                user_request="user",
                tool_name="save_memory",
                arguments={"category": category, "content_len": len(content)},
                result=reason,
                status="DENIED",
                permission_level="LEVEL_1_SAFE",
            )
            return {"success": False, "requires_confirmation": False, "message": reason}

        # 2. Confirm-before-save setting (soft confirmation gate)
        if self.settings.confirm_before_save and not confirmed:
            return {
                "success": False,
                "requires_confirmation": True,
                "message": f"confirm_before_save is on. Shall I remember: \"{content}\"?",
            }

        # 3. Normalise
        normalized = normalize_memory_content(content)

        # 4. Deduplication & contradiction detection
        existing_memories = self.store.find_candidates_by_category(category, limit=100)
        is_update_signal = is_preference_update(normalized)

        for ex in existing_memories:
            sim = calculate_jaccard_similarity(normalized, ex["content"])

            if sim >= 0.85:
                # Near-identical — skip (already stored)
                _mem_print("💾", f"Already remembered ({ex['category']}): {ex['content']}")
                return {
                    "success": True,
                    "message": f"I already have that in my {category} memory.",
                    "memory_id": ex["id"],
                    "action": "duplicate_skipped",
                }

            if sim >= 0.30 and is_update_signal:
                # Likely a contradiction / update — replace the old record
                old_content = ex["content"]
                self.store.update_memory(ex["id"], normalized, category)
                msg = f"Updated memory: was \"{old_content}\" → now \"{normalized}\""
                _mem_print("✏️", msg)
                AuditLogger.log(
                    user_request="user",
                    tool_name="save_memory",
                    arguments={"memory_id": ex["id"], "old": old_content, "new": normalized},
                    result="Memory updated (contradiction detected)",
                    status="EXECUTED",
                    permission_level="LEVEL_1_SAFE",
                )
                return {
                    "success": True,
                    "message": f"I've updated your {category} memory. It was \"{old_content}\" — now it's \"{normalized}\".",
                    "memory_id": ex["id"],
                    "action": "updated",
                }

        # 5. Fresh insert
        memory_id = self.store.insert_memory(
            category=category,
            content=normalized,
            source=source,
            confidence=1.0,
        )
        _mem_print("💾", f"Saved ({category}): {normalized}")
        AuditLogger.log(
            user_request="user",
            tool_name="save_memory",
            arguments={"category": category, "content": normalized, "memory_id": memory_id},
            result="New memory saved",
            status="EXECUTED",
            permission_level="LEVEL_1_SAFE",
        )
        return {
            "success": True,
            "message": f"Got it — I've saved that to your {category} memory.",
            "memory_id": memory_id,
            "action": "created",
        }

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_memory(self, query: str, category: Optional[str] = None) -> Dict[str, Any]:
        """Query saved memories and return formatted results."""
        if not self.is_memory_enabled():
            return {"success": True, "message": "Memory is currently disabled.", "memories": []}

        # Check project context first
        keywords = self.retrieval.extract_keywords(query)
        for kw in keywords:
            if kw in {"project", "william-1", "william", "status", "milestone", "decision", "blocker"}:
                briefing = self.project_memory.get_project_continuity_briefing("William-1")
                if briefing.get("found"):
                    return {
                        "success": True,
                        "message": briefing["message"],
                        "memories": [briefing["data"]["project"]],
                    }

        top_k = self.settings.top_k
        results = self.retrieval.search_memories(query, category=category, top_k=top_k)
        if not results:
            return {
                "success": True,
                "message": f"I don't have any saved memories matching '{query}'.",
                "memories": [],
            }

        _mem_print("🔍", f"Recalled {len(results)} memor{'y' if len(results) == 1 else 'ies'}.")
        formatted = "; ".join(m["content"] for m in results)
        return {
            "success": True,
            "message": f"Here is what I remember: {formatted}",
            "memories": results,
        }

    # ------------------------------------------------------------------
    # Inspection & control
    # ------------------------------------------------------------------

    def list_memories(self, category: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
        """Lists saved memories grouped by category."""
        if not self.is_memory_enabled():
            return {"success": True, "message": "Memory is currently disabled.", "memories": []}

        results = self.store.list_memories(category=category, limit=limit)
        if not results:
            cat_label = f" in '{category}'" if category else ""
            return {"success": True, "message": f"No saved memories found{cat_label}.", "memories": []}

        # Group by category for spoken summary
        by_cat: Dict[str, List[str]] = {}
        for m in results:
            cat = m.get("category", "personal")
            by_cat.setdefault(cat, []).append(m["content"])

        lines = []
        for cat, items in by_cat.items():
            lines.append(f"{cat.capitalize()} ({len(items)}): " + "; ".join(items))

        _mem_print("🔍", f"Showing {len(results)} memories.")
        return {
            "success": True,
            "message": f"I have {len(results)} saved memor{'y' if len(results) == 1 else 'ies'}. " + " | ".join(lines),
            "memories": results,
            "grouped": by_cat,
        }

    def show_all_memories_by_category(self) -> Dict[str, Any]:
        """Shows all active memories grouped by category (terminal-friendly)."""
        all_mems = self.store.list_memories(limit=1000)
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for m in all_mems:
            grouped.setdefault(m["category"], []).append(m)

        parts = []
        for cat, mems in grouped.items():
            parts.append(f"  {cat.upper()} ({len(mems)}):")
            for m in mems:
                ts = m.get("updated_at", "")[:10]
                parts.append(f"    [{m['id']}] {m['content']} (updated {ts})")

        summary = "\n".join(parts) if parts else "No memories stored."
        print(summary)
        return {
            "success": True,
            "message": f"Found {len(all_mems)} memor{'y' if len(all_mems) == 1 else 'ies'} across {len(grouped)} categories.",
            "grouped": grouped,
            "total": len(all_mems),
        }

    # ------------------------------------------------------------------
    # Forget (with ambiguity guard)
    # ------------------------------------------------------------------

    def forget_memory(self, target: str) -> Dict[str, Any]:
        """
        Soft-deletes memories matching the target keyword.
        If multiple distinct memories match and the target is vague, asks for
        clarification instead of guessing on a destructive operation.
        """
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}

        target_clean = target.strip()
        # Find candidates first
        all_mems = self.store.list_memories(limit=1000)
        matches = [m for m in all_mems if target_clean.lower() in m["content"].lower()]

        if not matches:
            return {
                "success": True,
                "message": f"No memories found matching '{target}' to forget.",
                "deleted_count": 0,
            }

        # Ambiguity check: if there are multiple distinct-category matches and
        # the target word is short/vague, ask for clarification.
        categories_hit = {m["category"] for m in matches}
        if len(matches) > 1 and len(target_clean.split()) <= 2 and len(categories_hit) > 1:
            candidates = [f"[{m['id']}] ({m['category']}) {m['content'][:60]}" for m in matches[:5]]
            listing = "; ".join(candidates)
            msg = (
                f"Which memory did you want to forget? I found {len(matches)}: {listing}. "
                f"Please say 'forget memory ID <number>' to be precise."
            )
            return {
                "success": False,
                "ambiguous": True,
                "message": msg,
                "candidates": matches[:5],
            }

        # Proceed with soft-delete
        count, deleted = self.store.soft_delete_memories_matching(target_clean)
        _mem_print("🗑️", f"Forgotten {count} memory record(s) matching '{target}'.")
        AuditLogger.log(
            user_request="user",
            tool_name="forget_memory",
            arguments={"target": target, "count": count},
            result=f"Soft-deleted {count} records",
            status="EXECUTED",
            permission_level="LEVEL_3_DESTRUCTIVE",
        )
        return {
            "success": True,
            "message": f"Done — I've forgotten {count} memory record(s) matching '{target}'.",
            "deleted_count": count,
        }

    def forget_memory_by_id(self, memory_id: int) -> Dict[str, Any]:
        """Precise soft-delete of a single memory by ID."""
        mem = self.store.get_memory(memory_id)
        if not mem:
            return {"success": False, "message": f"No active memory found with ID {memory_id}."}
        self.store.soft_delete_memory(memory_id)
        _mem_print("🗑️", f"Forgotten memory [{memory_id}]: {mem['content'][:60]}")
        AuditLogger.log(
            user_request="user",
            tool_name="forget_memory_by_id",
            arguments={"memory_id": memory_id, "content": mem["content"]},
            result="Memory soft-deleted",
            status="EXECUTED",
            permission_level="LEVEL_3_DESTRUCTIVE",
        )
        return {
            "success": True,
            "message": f"Forgotten: \"{mem['content']}\".",
            "memory_id": memory_id,
        }

    # ------------------------------------------------------------------
    # Project operations (with ambiguity guard)
    # ------------------------------------------------------------------

    def update_project_status(
        self,
        project_name: str,
        status: Optional[str] = None,
        current_blocker: Optional[str] = None,
        next_task: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates project status fields."""
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}

        # Ambiguity guard: if project_name is very generic, list candidates
        all_projects = self.project_memory.list_projects()
        if project_name.lower() in {"the project", "my project", "project", "it"}:
            if len(all_projects) > 1:
                names = ", ".join(f"'{p['name']}'" for p in all_projects)
                return {
                    "success": False,
                    "ambiguous": True,
                    "message": f"Which project? I'm tracking: {names}. Please name it specifically.",
                }
            elif len(all_projects) == 1:
                project_name = all_projects[0]["name"]

        p = self.project_memory.update_project(
            name=project_name, status=status, current_blocker=current_blocker, next_task=next_task
        )
        parts = [f"Updated project '{project_name}'."]
        if status:
            parts.append(f"Status: {status}.")
        if current_blocker:
            parts.append(f"Blocker: {current_blocker}.")
        if next_task:
            parts.append(f"Next task: {next_task}.")

        msg = " ".join(parts)
        _mem_print("✏️", msg)
        AuditLogger.log(
            user_request="user",
            tool_name="update_project_status",
            arguments={"project": project_name, "status": status, "blocker": current_blocker, "next": next_task},
            result=msg,
            status="EXECUTED",
            permission_level="LEVEL_2_SENSITIVE",
        )
        return {"success": True, "message": msg, "project": p}

    def get_project_continuity(self, project_name: str) -> Dict[str, Any]:
        """Project continuity briefing."""
        return self.project_memory.get_project_continuity_briefing(project_name)

    def show_project_full(self, project_name: str) -> Dict[str, Any]:
        """Full project record + event timeline (terminal output)."""
        project = self.project_memory.get_project(project_name)
        if not project:
            return {"success": False, "message": f"No project found named '{project_name}'."}

        events = self.store.get_project_events(project["id"], limit=50)
        print(f"\n  PROJECT: {project['name']} [{project['status']}]")
        print(f"  Stack: {project.get('technology_stack') or 'N/A'}")
        print(f"  Blocker: {project.get('current_blocker') or 'None'}")
        print(f"  Next: {project.get('next_task') or 'None'}")
        print(f"  Updated: {project.get('updated_at', '')[:16]}")
        if events:
            print(f"\n  EVENT TIMELINE ({len(events)}):")
            for ev in reversed(events):
                ts = ev.get("created_at", "")[:16]
                print(f"    [{ts}] {ev['event_type'].upper()}: {ev['summary']}")

        return {
            "success": True,
            "message": f"Project '{project_name}': {project.get('description') or 'no description'}. Status: {project['status']}.",
            "project": project,
            "events": events,
        }

    def delete_project_memories(self, project_name: str) -> Dict[str, Any]:
        """Deletes entire project + timeline. Ambiguity-guarded."""
        all_projects = self.project_memory.list_projects()
        if project_name.lower() in {"the project", "my project", "project", "it"}:
            if len(all_projects) > 1:
                names = ", ".join(f"'{p['name']}'" for p in all_projects)
                return {
                    "success": False,
                    "ambiguous": True,
                    "message": f"Which project to delete? I'm tracking: {names}. Name it exactly.",
                }
        result = self.project_memory.delete_project_and_memories(project_name)
        if result.get("success"):
            _mem_print("🗑️", f"Deleted project '{project_name}' and its memories.")
            AuditLogger.log(
                user_request="user",
                tool_name="delete_project_memories",
                arguments={"project": project_name},
                result=result.get("message", ""),
                status="EXECUTED",
                permission_level="LEVEL_3_DESTRUCTIVE",
            )
        return result

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export_memories(self, output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Exports all non-sensitive memories to a JSON file.
        Sensitive memories (those containing credential-like content) are excluded.
        """
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}

        safe_memories = self.store.export_non_sensitive_memories()
        projects = self.project_memory.list_projects()
        summaries = self.conversation_summary.get_recent_summaries(limit=50)

        payload = {
            "exported_at": datetime.now().isoformat(),
            "version": "v0.3+",
            "memories": safe_memories,
            "projects": projects,
            "conversation_summaries": summaries,
        }

        if output_path is None:
            data_dir = config.DATA_DIR
            os.makedirs(data_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(data_dir, f"william_memory_export_{ts}.json")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        msg = f"Exported {len(safe_memories)} memories and {len(projects)} project(s) to {output_path}."
        _mem_print("💾", msg)
        AuditLogger.log(
            user_request="user",
            tool_name="export_memories",
            arguments={"output_path": output_path},
            result=msg,
            status="EXECUTED",
            permission_level="LEVEL_1_SAFE",
        )
        return {"success": True, "message": msg, "path": output_path, "count": len(safe_memories)}

    def import_memories(self, input_path: str, confirmed: bool = False) -> Dict[str, Any]:
        """
        Imports memories from a JSON file exported by export_memories().
        Skips any records that fail the secret filter. Requires confirmed=True.
        """
        if not confirmed:
            return {
                "success": False,
                "requires_confirmation": True,
                "message": f"Import will add records from '{input_path}'. Confirm to proceed.",
            }

        if not os.path.isfile(input_path):
            return {"success": False, "message": f"Import file not found: '{input_path}'."}

        with open(input_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        imported, skipped = 0, 0
        for m in payload.get("memories", []):
            content = m.get("content", "")
            category = m.get("category", "personal")
            has_secret, _ = contains_secrets(content)
            if has_secret:
                skipped += 1
                continue
            # Use save_memory to run full dedup logic
            result = self.save_memory(content, category=category, source="import", confirmed=True)
            if result.get("success"):
                imported += 1
            else:
                skipped += 1

        msg = f"Import complete: {imported} memories imported, {skipped} skipped (secrets or duplicates)."
        _mem_print("💾", msg)
        AuditLogger.log(
            user_request="user",
            tool_name="import_memories",
            arguments={"input_path": input_path},
            result=msg,
            status="EXECUTED",
            permission_level="LEVEL_2_SENSITIVE",
        )
        return {"success": True, "message": msg, "imported": imported, "skipped": skipped}

    # ------------------------------------------------------------------
    # Context retrieval (called from Brain before LLM)
    # ------------------------------------------------------------------

    def retrieve_context_for_prompt(self, user_text: str) -> Optional[str]:
        """
        Called by Brain before each LLM generation.
        Returns a compact memory context block or None.
        When memory is disabled, returns None with zero reads.
        """
        if not self.is_memory_enabled():
            return None
        return self.retrieval.retrieve_context(user_text)



    # ------------------------------------------------------------------
    # Session event tracking (in-memory, never persisted raw)
    # ------------------------------------------------------------------

    def note_session_event(self, description: str) -> None:
        """Adds an event description to the current session's accumulator."""
        self.conversation_summary.note_session_event(description)

    # ------------------------------------------------------------------
    # Companion: project continuity
    # ------------------------------------------------------------------

    def continue_project(self, project_name: str = "William-1") -> dict:
        """Crisp briefing: phase, milestone, blocker, decisions, next task. Fully sourced."""
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        briefing = self.project_memory.get_project_continuity_briefing(project_name)
        if briefing.get("found"):
            _mem_print("🔍", f"Project briefing for '{project_name}'.")
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
        """Retrieves decision records with date + context. Honest if nothing saved."""
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
        _mem_print("🔍", f"Found {len(matches)} decision record(s).")
        return {"success": True, "message": " | ".join(parts), "events": matches}

    # ------------------------------------------------------------------
    # Companion: project health
    # ------------------------------------------------------------------

    def project_health(self, project_name: str = "William-1") -> dict:
        """Synthesizes status, milestones, blockers, staleness. Honest if nothing saved."""
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        result = self.project_memory.get_project_health(project_name)
        if result.get("found"):
            _mem_print("🔍", f"Project health for '{project_name}'.")
        return {"success": result.get("found", False), "message": result["message"], "data": result.get("data")}

    # ------------------------------------------------------------------
    # Companion: record project event
    # ------------------------------------------------------------------

    def record_project_event(
        self,
        project_name: str,
        event_type: str,
        summary: str,
        details: str = "",
        rejected_reason: str = "",
    ) -> dict:
        """Records a timestamped project event (milestone, decision, rejected, fix)."""
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        from utils.logger import AuditLogger as _AL
        event_type_clean = event_type.lower().strip()
        full_summary = summary
        if details:
            full_summary += f" - {details}"
        if rejected_reason:
            full_summary += f" (Reason: {rejected_reason})"
        result = self.project_memory.record_event(project_name, event_type_clean, full_summary)
        indicator = "💾" if event_type_clean in {"milestone", "completed"} else "✏️"
        _mem_print(indicator, f"[{project_name}] {event_type_clean}: {full_summary[:60]}")
        _AL.log(
            user_request="user", tool_name="record_project_event",
            arguments={"project": project_name, "type": event_type_clean, "summary": full_summary},
            result=f"Event {result['event_id']} recorded", status="EXECUTED", permission_level="LEVEL_1_SAFE",
        )
        return {"success": True, "message": f"Recorded {event_type_clean} for '{project_name}': {full_summary}", "event_id": result["event_id"]}

    # ------------------------------------------------------------------
    # Companion: session summary
    # ------------------------------------------------------------------

    def generate_session_summary(self, project_name=None, approved: bool = False, extra_context=None) -> dict:
        """End-of-session summary. approved=False for draft, True to persist. No raw transcripts saved."""
        summary = self.conversation_summary.generate_session_summary(project_name=project_name, extra_context=extra_context)
        if not approved:
            return {"success": True, "message": f"Session summary draft:\n{summary}", "summary": summary, "saved": False}
        record_id = self.conversation_summary.save_session_summary(
            summary=summary, retention_days=self.settings.retention_days
        )
        self.conversation_summary.clear_session_events()
        _mem_print("💾", f"Session summary saved (record {record_id}).")
        from utils.logger import AuditLogger as _AL
        _AL.log(
            user_request="user", tool_name="generate_session_summary",
            arguments={"project_name": project_name, "approved": True},
            result=f"Session summary saved as record {record_id}", status="EXECUTED", permission_level="LEVEL_1_SAFE",
        )
        return {"success": True, "message": f"Saved. {summary}", "summary": summary, "record_id": record_id, "saved": True}

    def get_last_session_recap(self):
        """Short 'Last time we...' recap. None if no previous sessions."""
        return self.conversation_summary.get_last_session_recap()

    # ------------------------------------------------------------------
    # Companion: memory-powered tool intelligence
    # ------------------------------------------------------------------

    def resolve_open_project_from_memory(self, project_name: str) -> dict:
        """Resolves folder path from saved project data for open_folder tool calls."""
        if not self.is_memory_enabled():
            return {"success": False, "message": "Memory is disabled."}
        path = self.project_memory.resolve_project_path(project_name)
        if path:
            _mem_print("🔍", f"Resolved '{project_name}' -> {path}")
            return {"success": True, "message": f"Found saved path: {path}", "path": path}
        import re as _re
        results = self.retrieval.search_memories(f"{project_name} folder path directory", top_k=3)
        for mem in results:
            m = _re.search(r'(?:[A-Za-z]:\\[^\s\'"]+|/[^\s\'"]{3,}|~[^\s\'\"]+)', mem["content"])
            if m:
                _mem_print("🔍", f"Path found in memory: {m.group(0)}")
                return {"success": True, "message": f"Found path in memory: {m.group(0)}", "path": m.group(0)}
        return {
            "success": False,
            "message": f"I don't have a saved path for '{project_name}'. "
                       f"Try: 'Remember that my {project_name} folder is at C:\\Users\\...'.",
        }

    def resolve_recent_project_from_episodic(self):
        """Identifies most-recently worked-on project from episodic summaries."""
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


# ---------------------------------------------------------------------------
# Application-wide singleton
# ---------------------------------------------------------------------------
memory_manager = MemoryManager()
