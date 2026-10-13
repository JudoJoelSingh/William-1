"""
Permissions Module for William-1 Safe Tool Execution Layer (v0.2).
Classifies tools into three permission tiers and enforces the Level 3 kill-switch:
- Level 1 (Safe): Read-only info, app opening, URLs, media controls. No confirmation needed.
- Level 2 (Sensitive): App closing, file modifications. Explicit affirmative confirmation required.
- Level 3 (Destructive): Deletion, shutdown, restart, sleep, lock. Strong confirmation required & kill-switch aware.
"""

from enum import IntEnum
from typing import Dict, Optional, Tuple
from config import config



class PermissionLevel(IntEnum):
    LEVEL_1_SAFE = 1
    LEVEL_2_SENSITIVE = 2
    LEVEL_3_DESTRUCTIVE = 3


# Explicit mapping of tool names to their required permission level
TOOL_PERMISSIONS: Dict[str, PermissionLevel] = {
    # --- Level 1: Safe (Read-only / Non-destructive) ---
    "open_application": PermissionLevel.LEVEL_1_SAFE,
    "open_url": PermissionLevel.LEVEL_1_SAFE,
    "search_web": PermissionLevel.LEVEL_1_SAFE,
    "list_directory": PermissionLevel.LEVEL_1_SAFE,
    "search_files": PermissionLevel.LEVEL_1_SAFE,
    "get_file_info": PermissionLevel.LEVEL_1_SAFE,
    "open_folder": PermissionLevel.LEVEL_1_SAFE,
    "get_battery_status": PermissionLevel.LEVEL_1_SAFE,
    "get_cpu_usage": PermissionLevel.LEVEL_1_SAFE,
    "get_ram_usage": PermissionLevel.LEVEL_1_SAFE,
    "get_disk_usage": PermissionLevel.LEVEL_1_SAFE,
    "get_os_info": PermissionLevel.LEVEL_1_SAFE,
    "get_datetime": PermissionLevel.LEVEL_1_SAFE,
    "play_pause": PermissionLevel.LEVEL_1_SAFE,
    "next_track": PermissionLevel.LEVEL_1_SAFE,
    "previous_track": PermissionLevel.LEVEL_1_SAFE,
    "volume_up": PermissionLevel.LEVEL_1_SAFE,
    "volume_down": PermissionLevel.LEVEL_1_SAFE,
    "set_volume": PermissionLevel.LEVEL_1_SAFE,
    "mute": PermissionLevel.LEVEL_1_SAFE,
    "unmute": PermissionLevel.LEVEL_1_SAFE,
    "get_system_health": PermissionLevel.LEVEL_1_SAFE,
    "get_recent_actions": PermissionLevel.LEVEL_1_SAFE,
    "explain_last_action": PermissionLevel.LEVEL_1_SAFE,
    "get_system_uptime": PermissionLevel.LEVEL_1_SAFE,
    "save_memory": PermissionLevel.LEVEL_1_SAFE,
    "query_memory": PermissionLevel.LEVEL_1_SAFE,
    "list_memories": PermissionLevel.LEVEL_1_SAFE,
    "show_all_memories": PermissionLevel.LEVEL_1_SAFE,
    "show_project": PermissionLevel.LEVEL_1_SAFE,
    "get_memory_settings": PermissionLevel.LEVEL_1_SAFE,
    "export_memories": PermissionLevel.LEVEL_1_SAFE,
    "set_memory_mode": PermissionLevel.LEVEL_1_SAFE,
    "continue_project": PermissionLevel.LEVEL_1_SAFE,
    "why_decision": PermissionLevel.LEVEL_1_SAFE,
    "project_health": PermissionLevel.LEVEL_1_SAFE,
    "generate_session_summary": PermissionLevel.LEVEL_1_SAFE,

    # --- Level 2: Sensitive (State Modification / Termination) ---
    "close_application": PermissionLevel.LEVEL_2_SENSITIVE,
    "open_file": PermissionLevel.LEVEL_2_SENSITIVE,
    "update_project_status": PermissionLevel.LEVEL_2_SENSITIVE,
    "record_project_event": PermissionLevel.LEVEL_2_SENSITIVE,
    "configure_memory": PermissionLevel.LEVEL_2_SENSITIVE,
    "import_memories": PermissionLevel.LEVEL_2_SENSITIVE,

    # --- Level 3: Destructive (Power States / Deletions / Workstation Lock) ---
    "delete_file": PermissionLevel.LEVEL_3_DESTRUCTIVE,
    "shutdown_system": PermissionLevel.LEVEL_3_DESTRUCTIVE,
    "restart_system": PermissionLevel.LEVEL_3_DESTRUCTIVE,
    "sleep_system": PermissionLevel.LEVEL_3_DESTRUCTIVE,
    "lock_computer": PermissionLevel.LEVEL_3_DESTRUCTIVE,
    "forget_memory": PermissionLevel.LEVEL_3_DESTRUCTIVE,
    "forget_memory_by_id": PermissionLevel.LEVEL_3_DESTRUCTIVE,
    "delete_project_memories": PermissionLevel.LEVEL_3_DESTRUCTIVE,
}


# Clear, natural spoken consequence descriptions for Level 2 and Level 3 actions
CONSEQUENCE_DESCRIPTIONS: Dict[str, str] = {
    "close_application": "Closing {application_name} will terminate the process and may cause unsaved work to be lost.",
    "shutdown_system": "Shutting down the computer will terminate all running applications and power off your system.",
    "restart_system": "Restarting the computer will close all open applications and reboot Windows.",
    "sleep_system": "Putting the computer to sleep will suspend your session.",
    "lock_computer": "Locking the computer will secure your workstation and require your password or PIN to unlock.",
    "delete_file": "Deleting {target} is a permanent action and cannot be undone.",
    "open_file": "Opening {target} will launch the associated desktop application.",
    "update_project_status": "Updating project '{project_name}' will modify the saved project status, blocker, or next task.",
    "record_project_event": "Recording an event for '{project_name}' will append to its persistent project log.",
    "configure_memory": "Changing memory settings will update how William stores and retrieves your personal memories.",
    "import_memories": "Importing memories from '{target}' will add records to your persistent memory store.",
    "forget_memory": "Forgetting '{target}' is permanent and will delete matching records from your memory.",
    "forget_memory_by_id": "Deleting memory ID {target} is permanent and will delete the record from your memory.",
    "delete_project_memories": "Deleting project '{project_name}' will permanently erase the project record, events, and related memories.",
}



def get_tool_permission_level(tool_name: str) -> PermissionLevel:
    """Returns the permission level for a given tool name. Defaults to Sensitive if unregistered."""
    return TOOL_PERMISSIONS.get(tool_name, PermissionLevel.LEVEL_2_SENSITIVE)


def requires_confirmation(tool_name: str) -> bool:
    """Returns True if the tool requires explicit affirmative user confirmation (Level 2 or Level 3)."""
    return get_tool_permission_level(tool_name) >= PermissionLevel.LEVEL_2_SENSITIVE


def is_tool_blocked_by_killswitch(tool_name: str) -> Tuple[bool, str]:
    """
    Checks whether the tool is blocked by configuration kill-switches.
    Returns: (is_blocked, reason)
    """
    perm = get_tool_permission_level(tool_name)
    if perm == PermissionLevel.LEVEL_3_DESTRUCTIVE and config.DISABLE_L3_TOOLS:
        return True, "Destructive system tools (Level 3) are currently disabled by the safety kill-switch."
    return False, ""


def get_consequence_prompt(tool_name: str, arguments: dict) -> str:
    """Generates a concise, explicit consequence prompt restating the exact action."""
    template = CONSEQUENCE_DESCRIPTIONS.get(tool_name, "This action will modify system state.")
    app_name = arguments.get("application", arguments.get("app_name", "the application"))
    target = arguments.get("target", arguments.get("path", arguments.get("file_path", arguments.get("file_name", "the selected target"))))
    project_name = arguments.get("project_name", "the project")

    try:
        formatted = template.format(
            application_name=app_name,
            application=app_name,
            target=target,
            file_path=target,
            file_name=target,
            project_name=project_name,
        )
    except Exception:
        formatted = template

    return f"{formatted} Do you want me to proceed?"
