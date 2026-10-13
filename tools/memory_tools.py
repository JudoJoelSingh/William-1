"""
Memory Tools Module for William-1 Safe Tool Execution Layer (v0.3+).
Exposes persistent memory operations to the Tool Manager.

Permission levels:
  LEVEL_1_SAFE        – save, query, list, settings, export
  LEVEL_2_SENSITIVE   – update_project_status, import, configure_memory
  LEVEL_3_DESTRUCTIVE – forget_memory, forget_memory_by_id, delete_project_memories

Every operation is logged to the audit trail by the MemoryManager.
"""

from typing import Dict, Any, Optional
from memory.memory_manager import memory_manager


# ---------------------------------------------------------------------------
# Level 1 – Safe reads and writes
# ---------------------------------------------------------------------------

def save_memory(content: str, category: str = "personal", confirmed: bool = False) -> Dict[str, Any]:
    """
    Saves a persistent fact, preference, or note.
    If the content looks like a credential, William explains why he won't store it.
    If confirmed=True, bypasses the confirm_before_save gate (used after user confirms).
    """
    return memory_manager.save_memory(
        content=content,
        category=category or "personal",
        source="user",
        confirmed=confirmed,
    )


def query_memory(query: str, category: str = "") -> Dict[str, Any]:
    """Queries saved memories by keyword and optional category."""
    cat = category.strip() or None
    return memory_manager.query_memory(query=query, category=cat)


def list_memories(category: str = "") -> Dict[str, Any]:
    """Lists saved user memories, optionally filtered by category."""
    cat = category.strip() or None
    return memory_manager.list_memories(category=cat)


def show_all_memories() -> Dict[str, Any]:
    """Displays all active memories grouped by category in the terminal."""
    return memory_manager.show_all_memories_by_category()


def get_memory_settings() -> Dict[str, Any]:
    """Returns current memory settings."""
    return memory_manager.get_memory_settings()


def set_memory_mode(enabled: bool) -> Dict[str, Any]:
    """Enables or disables persistent memory storage."""
    return memory_manager.set_memory_mode(enabled=enabled)


def export_memories(output_path: str = "") -> Dict[str, Any]:
    """
    Exports non-sensitive memories to a JSON backup file.
    Sensitive/credential memories are excluded automatically.
    """
    path = output_path.strip() or None
    return memory_manager.export_memories(output_path=path)


# ---------------------------------------------------------------------------
# Level 2 – Sensitive (require confirmation)
# ---------------------------------------------------------------------------

def update_project_status(
    project_name: str,
    status: str = "",
    current_blocker: str = "",
    next_task: str = "",
) -> Dict[str, Any]:
    """
    Updates the status, blocker, or next task of a tracked project.
    Returns an ambiguity clarification if project_name is vague.
    Level 2: requires explicit confirmation.
    """
    return memory_manager.update_project_status(
        project_name=project_name,
        status=status.strip() or None,
        current_blocker=current_blocker.strip() or None,
        next_task=next_task.strip() or None,
    )


def show_project(project_name: str) -> Dict[str, Any]:
    """Shows a project's full record and event timeline in the terminal."""
    return memory_manager.show_project_full(project_name)


def configure_memory(settings_json: str = "") -> Dict[str, Any]:
    """
    Bulk-updates memory settings from a JSON string.
    Example: configure_memory('{"top_k": 5, "local_only": true}')
    Level 2: requires explicit confirmation.
    """
    import json
    try:
        updates = json.loads(settings_json) if settings_json.strip() else {}
    except Exception:
        return {"success": False, "message": "Invalid JSON for settings update."}
    return memory_manager.configure_memory(updates)


def import_memories(input_path: str, confirmed: bool = False) -> Dict[str, Any]:
    """
    Imports memories from a JSON export file.
    Requires confirmed=True to proceed (Level 2).
    """
    return memory_manager.import_memories(input_path=input_path, confirmed=confirmed)


# ---------------------------------------------------------------------------
# Level 3 – Destructive (require strong confirmation naming target)
# ---------------------------------------------------------------------------

def forget_memory(target: str) -> Dict[str, Any]:
    """
    Soft-deletes memory records matching a keyword or phrase.
    Returns ambiguity clarification if multiple distinct memories match.
    Level 3: requires explicit confirmation naming the target.
    """
    return memory_manager.forget_memory(target=target)


def forget_memory_by_id(memory_id: int) -> Dict[str, Any]:
    """
    Precisely soft-deletes a single memory by numeric ID.
    Level 3: requires explicit confirmation.
    """
    return memory_manager.forget_memory_by_id(memory_id=memory_id)


def delete_project_memories(project_name: str) -> Dict[str, Any]:
    """
    Deletes an entire project, its event timeline, and all associated memory records.
    Returns ambiguity clarification if project_name is vague.
    Level 3: requires explicit confirmation naming the project.
    """
    return memory_manager.delete_project_memories(project_name=project_name)


# ---------------------------------------------------------------------------
# Companion Tools (Phase 3 Elevation)
# ---------------------------------------------------------------------------

def continue_project(project_name: str = "William-1") -> Dict[str, Any]:
    """
    Returns a crisp spoken briefing on project status, last milestone, current blocker,
    recorded decisions, and next task — strictly from saved records with provenance.
    Level 1: Safe.
    """
    return memory_manager.continue_project(project_name=project_name)


def why_decision(topic_or_query: str, project_name: str = "William-1") -> Dict[str, Any]:
    """
    Retrieves decision records with date, context, and provenance.
    Level 1: Safe.
    """
    return memory_manager.why_decision(query=topic_or_query, project_name=project_name)


def project_health(project_name: str = "William-1") -> Dict[str, Any]:
    """
    Synthesizes project status, completed milestones, blockers, and staleness into
    one natural briefing plus suggested next step.
    Level 1: Safe.
    """
    return memory_manager.project_health(project_name=project_name)


def record_project_event(
    project_name: str,
    event_type: str,
    summary: str,
    details: str = "",
    rejected_reason: str = "",
) -> Dict[str, Any]:
    """
    Records a milestone, decision, or rejected design with rationale in the project event log.
    Level 2: Sensitive.
    """
    return memory_manager.record_project_event(
        project_name=project_name,
        event_type=event_type,
        summary=summary,
        details=details,
        rejected_reason=rejected_reason,
    )


def generate_session_summary(project_name: str = "William-1", approved: bool = True) -> Dict[str, Any]:
    """
    Generates a concise episodic summary of the session and saves it with retention.
    Level 1: Safe.
    """
    return memory_manager.generate_session_summary(project_name=project_name, approved=approved)

