"""
Tool Manager Module for William-1 Safe Tool Execution Layer (v0.2).
The centralized security boundary for all system interactions:
1. Tool validation against explicit typed registry.
2. Cross-platform OS support verification (fail-fast on unsupported platforms).
3. Level 3 Kill-switch safety check.
4. Strict argument type, range, and normalized path verification.
5. Permission level evaluation & explicit user confirmation.
6. Sandboxed execution without arbitrary shell execution.
7. Structured dual logging (human audit log + JSONL action log).
"""

import os
import time
import platform
from typing import Dict, Any, Callable, List, Optional, Tuple
from security.permissions import (
    get_tool_permission_level,
    requires_confirmation,
    is_tool_blocked_by_killswitch,
    PermissionLevel,
)
from security.confirmation import ConfirmationHandler
from utils.logger import AuditLogger
from config import config

# Import tool implementations
from tools.applications import open_application, close_application
from tools.browser import open_url, search_web
from tools.files import open_folder, open_file, list_directory, search_files, get_file_info, delete_file, _is_path_allowed
from tools.system import (
    get_battery_status,
    get_cpu_usage,
    get_ram_usage,
    get_disk_usage,
    get_os_info,
    get_datetime,
    set_volume,
    mute,
    unmute,
    lock_computer,
    sleep_system,
    restart_system,
    shutdown_system,
    get_system_health,
    get_recent_actions,
    explain_last_action,
)
from tools.template_tool import get_system_uptime
from tools.media import play_pause, next_track, previous_track, volume_up, volume_down
from tools.memory_tools import (
    save_memory,
    query_memory,
    list_memories,
    show_all_memories,
    show_project,
    update_project_status,
    forget_memory,
    forget_memory_by_id,
    delete_project_memories,
    set_memory_mode,
    configure_memory,
    get_memory_settings,
    export_memories,
    import_memories,
    continue_project,
    why_decision,
    project_health,
    record_project_event,
    generate_session_summary,
)



class ToolManager:
    """Central registry and security manager for all assistant tools."""

    def __init__(self):
        self._registry: Dict[str, Callable] = {}
        self._schemas: List[Dict[str, Any]] = []
        self._param_specs: Dict[str, Dict[str, Any]] = {}
        self._platforms: Dict[str, List[str]] = {}
        self.current_os = platform.system()
        self._register_all_tools()

    def register_tool(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters: Dict[str, Any],
        required_params: Optional[List[str]] = None,
        type_specs: Optional[Dict[str, Any]] = None,
        supported_platforms: Optional[List[str]] = None,
    ):
        """Registers a tool function with its JSON schema, type specs, and platform constraints."""
        self._registry[name] = func
        self._param_specs[name] = type_specs or {}
        self._platforms[name] = supported_platforms or ["Windows", "Linux", "Darwin"]

        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": parameters,
                    "required": required_params or [],
                },
            },
        }
        self._schemas.append(schema)

    def _register_all_tools(self):
        """Initializes all approved tool registrations."""
        # --- Applications ---
        self.register_tool(
            name="open_application",
            func=open_application,
            description="Opens an allowed desktop application (e.g. 'vscode', 'chrome', 'explorer', 'notepad', 'calculator', 'terminal', 'spotify', 'discord') or fuzzy alias.",
            parameters={
                "application": {
                    "type": "string",
                    "description": "Friendly name or alias (e.g. 'vscode', 'the browser', 'my music', 'notepad', 'calculator', 'terminal').",
                }
            },
            required_params=["application"],
            type_specs={"application": str},
        )

        self.register_tool(
            name="close_application",
            func=close_application,
            description="Closes running instances of an allowlisted application (requires confirmation).",
            parameters={
                "application": {
                    "type": "string",
                    "description": "Friendly name or alias of the application to close.",
                }
            },
            required_params=["application"],
            type_specs={"application": str},
        )

        # --- Browser ---
        self.register_tool(
            name="open_url",
            func=open_url,
            description="Opens a website by name (e.g. 'youtube', 'github', 'reddit') or verified web URL in default browser.",
            parameters={
                "url": {
                    "type": "string",
                    "description": "Website name alias or valid web URL (http/https).",
                }
            },
            required_params=["url"],
            type_specs={"url": str},
        )

        self.register_tool(
            name="search_web",
            func=search_web,
            description="Conducts a web search query in default browser.",
            parameters={
                "query": {
                    "type": "string",
                    "description": "The search query string.",
                }
            },
            required_params=["query"],
            type_specs={"query": str},
        )

        # --- Files ---
        self.register_tool(
            name="open_folder",
            func=open_folder,
            description="Opens a folder in File Explorer within permitted roots ('documents', 'downloads', 'desktop', etc.) or named shortcuts ('william-1 project').",
            parameters={
                "folder": {
                    "type": "string",
                    "description": "Friendly root name, named shortcut (e.g. 'william-1 project', 'my documents'), or allowed folder path.",
                }
            },
            required_params=[],
            type_specs={"folder": str},
        )

        self.register_tool(
            name="open_file",
            func=open_file,
            description="Opens a file with default associated application (requires confirmation).",
            parameters={
                "file_path": {
                    "type": "string",
                    "description": "Path to file inside permitted user directories.",
                }
            },
            required_params=["file_path"],
            type_specs={"file_path": str, "_is_path": True},
        )

        self.register_tool(
            name="list_directory",
            func=list_directory,
            description="Lists files and subdirectories within a permitted folder path or named shortcut.",
            parameters={
                "folder": {
                    "type": "string",
                    "description": "Folder name, shortcut (e.g. 'workspace', 'documents'), or permitted path.",
                },
                "max_items": {
                    "type": "integer",
                    "description": "Maximum items to display (default 15).",
                }
            },
            required_params=[],
            type_specs={"folder": str, "max_items": int},
        )

        self.register_tool(
            name="search_files",
            func=search_files,
            description="Searches for files by name or extension within permitted folders.",
            parameters={
                "query": {
                    "type": "string",
                    "description": "Partial or full filename to search for.",
                },
                "root_folder": {
                    "type": "string",
                    "description": "Folder or shortcut to search in (e.g. 'documents', 'downloads', 'workspace').",
                },
                "extension": {
                    "type": "string",
                    "description": "Optional file extension filter (e.g. 'pdf', 'txt', 'py').",
                }
            },
            required_params=["query"],
            type_specs={"query": str, "root_folder": str, "extension": str},
        )

        self.register_tool(
            name="get_file_info",
            func=get_file_info,
            description="Retrieves metadata (size, last modified date, type) of a file within permitted folders.",
            parameters={
                "file_path": {
                    "type": "string",
                    "description": "Path to file inside permitted directories.",
                }
            },
            required_params=["file_path"],
            type_specs={"file_path": str, "_is_path": True},
        )

        self.register_tool(
            name="delete_file",
            func=delete_file,
            description="Permanently deletes a file or directory within permitted folders (Level 3 destructive - requires confirmation).",
            parameters={
                "target_path": {
                    "type": "string",
                    "description": "Path to file or directory within permitted roots to delete.",
                }
            },
            required_params=["target_path"],
            type_specs={"target_path": str, "_is_path": True},
        )

        # --- System Telemetry ---
        self.register_tool(
            name="get_battery_status",
            func=get_battery_status,
            description="Gets the current laptop battery percentage, charging state, and remaining time.",
            parameters={},
            required_params=[],
        )

        self.register_tool(
            name="get_cpu_usage",
            func=get_cpu_usage,
            description="Gets current CPU load percentage and core count.",
            parameters={},
            required_params=[],
        )

        self.register_tool(
            name="get_ram_usage",
            func=get_ram_usage,
            description="Gets system RAM memory usage and available memory.",
            parameters={},
            required_params=[],
        )

        self.register_tool(
            name="get_disk_usage",
            func=get_disk_usage,
            description="Gets primary storage drive usage, free space, and capacity.",
            parameters={},
            required_params=[],
        )

        self.register_tool(
            name="get_os_info",
            func=get_os_info,
            description="Gets operating system name, version, and hardware architecture.",
            parameters={},
            required_params=[],
        )

        self.register_tool(
            name="get_datetime",
            func=get_datetime,
            description="Gets the current date, time, and day of the week.",
            parameters={},
            required_params=[],
        )

        self.register_tool(
            name="get_system_health",
            func=get_system_health,
            description="Synthesizes an intelligent system health briefing covering battery, memory pressure, disk space, and CPU load with one useful observation.",
            parameters={},
            required_params=[],
        )

        self.register_tool(
            name="get_recent_actions",
            func=get_recent_actions,
            description="Retrieves the most recent actions executed by the assistant.",
            parameters={
                "limit": {
                    "type": "integer",
                    "description": "Number of recent actions to retrieve (default 5).",
                }
            },
            required_params=[],
            type_specs={"limit": int, "_min": 1},
        )

        self.register_tool(
            name="explain_last_action",
            func=explain_last_action,
            description="Explains what William just did, accurately distinguishing what was spoken from what actions and tools were executed on the system.",
            parameters={},
            required_params=[],
        )

        self.register_tool(
            name="get_system_uptime",
            func=get_system_uptime,
            description="Gets how long the computer has been running since last boot.",
            parameters={
                "detailed": {
                    "type": "boolean",
                    "description": "Whether to return detailed hours, minutes, and boot time.",
                }
            },
            required_params=[],
            type_specs={"detailed": bool},
            supported_platforms=["Windows", "Linux", "Darwin"],
        )

        # --- System Controls ---
        self.register_tool(
            name="set_volume",
            func=set_volume,
            description="Sets the master system volume to a percentage level between 0 and 100.",
            parameters={
                "level": {
                    "type": "integer",
                    "description": "Volume percentage from 0 (muted) to 100 (maximum).",
                }
            },
            required_params=["level"],
            type_specs={"level": int, "_range": (0, 100)},
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="mute",
            func=mute,
            description="Mutes system audio sound.",
            parameters={},
            required_params=[],
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="unmute",
            func=unmute,
            description="Unmutes system audio sound.",
            parameters={},
            required_params=[],
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="lock_computer",
            func=lock_computer,
            description="Locks the computer screen (Level 3 destructive - requires confirmation).",
            parameters={},
            required_params=[],
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="sleep_system",
            func=sleep_system,
            description="Puts the computer to sleep (Level 3 destructive - requires confirmation).",
            parameters={},
            required_params=[],
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="restart_system",
            func=restart_system,
            description="Restarts the computer (Level 3 destructive - requires confirmation).",
            parameters={
                "delay_seconds": {
                    "type": "integer",
                    "description": "Delay before restarting in seconds (default 5).",
                }
            },
            required_params=[],
            type_specs={"delay_seconds": int, "_min": 0},
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="shutdown_system",
            func=shutdown_system,
            description="Powers off and shuts down the computer (Level 3 destructive - requires confirmation).",
            parameters={
                "delay_seconds": {
                    "type": "integer",
                    "description": "Delay before shutdown in seconds (default 5).",
                }
            },
            required_params=[],
            type_specs={"delay_seconds": int, "_min": 0},
            supported_platforms=["Windows"],
        )

        # --- Media Controls ---
        self.register_tool(
            name="play_pause",
            func=play_pause,
            description="Toggles play or pause for active media player.",
            parameters={},
            required_params=[],
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="next_track",
            func=next_track,
            description="Skips to next media track.",
            parameters={},
            required_params=[],
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="previous_track",
            func=previous_track,
            description="Returns to previous media track.",
            parameters={},
            required_params=[],
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="volume_up",
            func=volume_up,
            description="Increases volume by small increments.",
            parameters={
                "steps": {
                    "type": "integer",
                    "description": "Steps to increase (1 to 20, default 2).",
                }
            },
            required_params=[],
            type_specs={"steps": int, "_range": (1, 20)},
            supported_platforms=["Windows"],
        )

        self.register_tool(
            name="volume_down",
            func=volume_down,
            description="Decreases volume by small increments.",
            parameters={
                "steps": {
                    "type": "integer",
                    "description": "Steps to decrease (1 to 20, default 2).",
                }
            },
            required_params=[],
            type_specs={"steps": int, "_range": (1, 20)},
            supported_platforms=["Windows"],
        )

        # --- Phase 3: Persistent User-Controlled Memory Tools ---
        self.register_tool(
            name="save_memory",
            func=save_memory,
            description="Saves a persistent fact, preference, or note into user memory.",
            parameters={
                "content": {
                    "type": "string",
                    "description": "The fact, preference, or project detail to remember (never passwords or API keys).",
                },
                "category": {
                    "type": "string",
                    "description": "Category for memory: 'personal', 'preference', 'fact', 'project', or 'decision'.",
                },
            },
            required_params=["content"],
            type_specs={"content": str, "category": str},
        )

        self.register_tool(
            name="query_memory",
            func=query_memory,
            description="Queries saved long-term memories by keyword or category.",
            parameters={
                "query": {
                    "type": "string",
                    "description": "The search query or topic to look up in saved memories.",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category filter (e.g. 'preference', 'project', 'fact').",
                },
            },
            required_params=["query"],
            type_specs={"query": str, "category": str},
        )

        self.register_tool(
            name="list_memories",
            func=list_memories,
            description="Lists saved user preferences and facts.",
            parameters={
                "category": {
                    "type": "string",
                    "description": "Optional category to filter by (e.g. 'preference', 'personal', 'project').",
                }
            },
            required_params=[],
            type_specs={"category": str},
        )

        self.register_tool(
            name="update_project_status",
            func=update_project_status,
            description="Updates the project status, blocker, or next task of a tracked project (requires confirmation).",
            parameters={
                "project_name": {
                    "type": "string",
                    "description": "Name of the project to update (e.g. 'William-1').",
                },
                "status": {
                    "type": "string",
                    "description": "Current status (e.g. 'active', 'paused', 'completed').",
                },
                "current_blocker": {
                    "type": "string",
                    "description": "Current blocker or issue preventing progress.",
                },
                "next_task": {
                    "type": "string",
                    "description": "The next planned task or milestone.",
                },
            },
            required_params=["project_name"],
            type_specs={"project_name": str, "status": str, "current_blocker": str, "next_task": str},
        )

        self.register_tool(
            name="forget_memory",
            func=forget_memory,
            description="Permanently erases memories matching a target phrase or keyword (requires confirmation).",
            parameters={
                "target": {
                    "type": "string",
                    "description": "Keyword or phrase identifying the memory records to delete.",
                }
            },
            required_params=["target"],
            type_specs={"target": str},
        )

        self.register_tool(
            name="delete_project_memories",
            func=delete_project_memories,
            description="Permanently erases an entire project record, its event timeline, and related memories (requires confirmation).",
            parameters={
                "project_name": {
                    "type": "string",
                    "description": "The exact name of the project to delete.",
                }
            },
            required_params=["project_name"],
            type_specs={"project_name": str},
        )

        self.register_tool(
            name="set_memory_mode",
            func=set_memory_mode,
            description="Enables or disables persistent memory storage.",
            parameters={
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable persistent memory, False to disable.",
                }
            },
            required_params=["enabled"],
            type_specs={"enabled": bool},
        )

        self.register_tool(
            name="continue_project",
            func=continue_project,
            description="Returns a crisp spoken briefing on project status, last milestone, current blocker, recorded decisions, and next task from saved records.",
            parameters={
                "project_name": {
                    "type": "string",
                    "description": "Name of the project to resume (defaults to 'William-1').",
                }
            },
            required_params=[],
            type_specs={"project_name": str},
        )

        self.register_tool(
            name="why_decision",
            func=why_decision,
            description="Retrieves recorded decisions with dates and provenance. Explains why a technology, tool, or architectural design was chosen.",
            parameters={
                "topic_or_query": {
                    "type": "string",
                    "description": "The decision topic or technology to look up (e.g. 'SQLite', 'FastAPI').",
                },
                "project_name": {
                    "type": "string",
                    "description": "Project name (defaults to 'William-1').",
                },
            },
            required_params=["topic_or_query"],
            type_specs={"topic_or_query": str, "project_name": str},
        )

        self.register_tool(
            name="project_health",
            func=project_health,
            description="Synthesizes project status, completed milestones, open blockers, and staleness into one natural briefing plus suggested next step.",
            parameters={
                "project_name": {
                    "type": "string",
                    "description": "Project name (defaults to 'William-1').",
                }
            },
            required_params=[],
            type_specs={"project_name": str},
        )

        self.register_tool(
            name="record_project_event",
            func=record_project_event,
            description="Records a project milestone, architectural decision, or rejected design with rationale in the persistent log.",
            parameters={
                "project_name": {
                    "type": "string",
                    "description": "Project name (e.g. 'William-1').",
                },
                "event_type": {
                    "type": "string",
                    "description": "Type of event: 'milestone', 'decision', 'rejected', or 'note'.",
                },
                "summary": {
                    "type": "string",
                    "description": "Short summary of the milestone, decision, or rejected choice.",
                },
                "details": {
                    "type": "string",
                    "description": "Optional context or details.",
                },
                "rejected_reason": {
                    "type": "string",
                    "description": "Reason why the design was rejected (if event_type is 'rejected').",
                },
            },
            required_params=["project_name", "event_type", "summary"],
            type_specs={
                "project_name": str,
                "event_type": str,
                "summary": str,
                "details": str,
                "rejected_reason": str,
            },
        )

        self.register_tool(
            name="generate_session_summary",
            func=generate_session_summary,
            description="Generates an episodic summary of what was worked on, decisions made, and what's next, and persists it.",
            parameters={
                "project_name": {
                    "type": "string",
                    "description": "Optional project name.",
                },
                "approved": {
                    "type": "boolean",
                    "description": "True to save to memory, False for a preview draft.",
                },
            },
            required_params=[],
            type_specs={"project_name": str, "approved": bool},
        )

        self.register_tool(
            name="show_all_memories",
            func=show_all_memories,
            description="Displays all saved user memories grouped by category.",
            parameters={},
            required_params=[],
            type_specs={},
        )

        self.register_tool(
            name="show_project",
            func=show_project,
            description="Displays a project's full record and event timeline.",
            parameters={
                "project_name": {
                    "type": "string",
                    "description": "The name of the project.",
                }
            },
            required_params=["project_name"],
            type_specs={"project_name": str},
        )

        self.register_tool(
            name="configure_memory",
            func=configure_memory,
            description="Configures memory settings via a JSON string.",
            parameters={
                "settings_json": {
                    "type": "string",
                    "description": "JSON object string with settings (e.g. '{\"top_k\": 5}').",
                }
            },
            required_params=["settings_json"],
            type_specs={"settings_json": str},
        )

        self.register_tool(
            name="get_memory_settings",
            func=get_memory_settings,
            description="Returns current memory configuration settings.",
            parameters={},
            required_params=[],
            type_specs={},
        )

        self.register_tool(
            name="export_memories",
            func=export_memories,
            description="Exports non-sensitive memories and projects to a backup JSON file.",
            parameters={
                "output_path": {
                    "type": "string",
                    "description": "Optional file path for the backup JSON.",
                }
            },
            required_params=[],
            type_specs={"output_path": str},
        )

        self.register_tool(
            name="import_memories",
            func=import_memories,
            description="Imports memories from a backup JSON file.",
            parameters={
                "input_path": {
                    "type": "string",
                    "description": "Path to the backup JSON file.",
                },
                "confirmed": {
                    "type": "boolean",
                    "description": "Confirmation flag.",
                },
            },
            required_params=["input_path"],
            type_specs={"input_path": str, "confirmed": bool},
        )

        self.register_tool(
            name="forget_memory_by_id",
            func=forget_memory_by_id,
            description="Permanently deletes a specific memory record by its numeric ID.",
            parameters={
                "memory_id": {
                    "type": "integer",
                    "description": "The numeric ID of the memory record to delete.",
                }
            },
            required_params=["memory_id"],
            type_specs={"memory_id": int},
        )


    def get_schemas(self) -> List[Dict[str, Any]]:
        """Returns the list of OpenAI-compatible tool schemas."""
        return self._schemas

    def is_tool_registered(self, tool_name: str) -> bool:
        """Checks if a tool name exists in the registry."""
        return tool_name in self._registry

    def _validate_arguments(self, tool_name: str, arguments: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validates argument presence, types, numeric ranges, and file path boundaries.
        """
        specs = self._param_specs.get(tool_name, {})

        for param, expected in specs.items():
            if param.startswith("_"):
                continue

            if param in arguments:
                val = arguments[param]
                if expected is int:
                    try:
                        arguments[param] = int(val)
                    except (ValueError, TypeError):
                        return False, f"Argument '{param}' must be an integer."
                elif expected is str and not isinstance(val, str):
                    arguments[param] = str(val)

        # Range validation
        if "_range" in specs:
            min_v, max_v = specs["_range"]
            for param in specs:
                if param.startswith("_"):
                    continue
                if param in arguments:
                    val = arguments[param]
                    if not (min_v <= val <= max_v):
                        return False, f"Argument '{param}' must be between {min_v} and {max_v}."

        if "_min" in specs:
            min_v = specs["_min"]
            for param in specs:
                if param.startswith("_"):
                    continue
                if param in arguments:
                    val = arguments[param]
                    if val < min_v:
                        return False, f"Argument '{param}' must be at least {min_v}."

        # Path normalization and sandbox check
        if specs.get("_is_path", False):
            path_val = arguments.get("file_path", arguments.get("path"))
            if path_val:
                is_allowed, resolved = _is_path_allowed(path_val)
                if not is_allowed:
                    return False, f"Path '{path_val}' is outside permitted root directories."
                arguments["file_path" if "file_path" in arguments else "path"] = resolved

        return True, None

    def execute_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        user_request: str = "",
        confirm_callback: Optional[Callable[[str], str]] = None,
        skip_confirmation: bool = False,
    ) -> Dict[str, Any]:
        """
        Full security verification & execution pipeline:
        1. Registry check
        2. OS Platform compatibility check
        3. Level 3 Kill-switch check
        4. Argument validation & path boundary check
        5. Permission classification & explicit confirmation
        6. Safe execution
        7. Dual audit logging (text + JSONL)
        8. Structured result packaging
        """
        start_time = time.time()
        args = arguments or {}
        perm_level = get_tool_permission_level(tool_name)
        perm_str = f"Level {perm_level.value} ({perm_level.name})"

        # Step 1: Check registry
        if not self.is_tool_registered(tool_name):
            err_msg = f"Unknown tool '{tool_name}'. It is not in my security registry."
            duration = time.time() - start_time
            AuditLogger.log(
                user_request=user_request,
                tool_name=tool_name,
                arguments=args,
                permission_level=perm_str,
                status="DENIED",
                error=err_msg,
                duration_sec=duration,
            )
            return {
                "success": False,
                "tool": tool_name,
                "message": f"I don't know how to perform the requested tool action '{tool_name}'.",
                "error": err_msg,
            }

        # Step 2: OS Platform compatibility check
        supported = self._platforms.get(tool_name, ["Windows", "Linux", "Darwin"])
        if self.current_os not in supported:
            err_msg = f"That action isn't supported on {self.current_os}."
            duration = time.time() - start_time
            AuditLogger.log(
                user_request=user_request,
                tool_name=tool_name,
                arguments=args,
                permission_level=perm_str,
                status="DENIED",
                error=err_msg,
                duration_sec=duration,
            )
            return {
                "success": False,
                "tool": tool_name,
                "message": err_msg,
                "error": f"Tool '{tool_name}' only supports: {supported}",
            }

        # Step 3: Level 3 Kill-Switch check
        is_blocked, block_reason = is_tool_blocked_by_killswitch(tool_name)
        if is_blocked:
            duration = time.time() - start_time
            AuditLogger.log(
                user_request=user_request,
                tool_name=tool_name,
                arguments=args,
                permission_level=perm_str,
                status="BLOCKED",
                error=block_reason,
                duration_sec=duration,
            )
            return {
                "success": False,
                "tool": tool_name,
                "message": block_reason,
                "error": "Blocked by L3 kill-switch.",
            }

        # Step 4: Validate arguments and path boundaries
        valid_args, arg_error = self._validate_arguments(tool_name, args)
        if not valid_args:
            duration = time.time() - start_time
            AuditLogger.log(
                user_request=user_request,
                tool_name=tool_name,
                arguments=args,
                permission_level=perm_str,
                status="DENIED",
                error=arg_error,
                duration_sec=duration,
            )
            return {
                "success": False,
                "tool": tool_name,
                "message": f"Invalid arguments provided for {tool_name}: {arg_error}",
                "error": arg_error,
            }

        # Step 5: Check permission level & confirmation
        confirmed_flag = True
        if not skip_confirmation and requires_confirmation(tool_name):
            confirmed, reason = ConfirmationHandler.request_confirmation(
                tool_name=tool_name,
                arguments=args,
                prompt_callback=confirm_callback,
            )
            confirmed_flag = confirmed
            if not confirmed:
                duration = time.time() - start_time
                AuditLogger.log(
                    user_request=user_request,
                    tool_name=tool_name,
                    arguments=args,
                    permission_level=perm_str,
                    status="CANCELLED",
                    confirmed=False,
                    result=f"Cancelled: {reason}",
                    duration_sec=duration,
                )
                return {
                    "success": False,
                    "tool": tool_name,
                    "cancelled": True,
                    "message": "Action cancelled. I did not proceed without your confirmation.",
                    "data": {"status": "cancelled", "reason": reason},
                }

        # Step 6: Execute approved Python function
        tool_func = self._registry[tool_name]
        try:
            raw_result = tool_func(**args)
            if not isinstance(raw_result, dict):
                raw_result = {"success": True, "message": str(raw_result), "data": raw_result}

            raw_result["tool"] = tool_name
            status = "EXECUTED" if raw_result.get("success", False) else "FAILED"
            duration = time.time() - start_time

            AuditLogger.log(
                user_request=user_request,
                tool_name=tool_name,
                arguments=args,
                permission_level=perm_str,
                status=status,
                confirmed=confirmed_flag,
                result=raw_result.get("message", ""),
                error=raw_result.get("error"),
                duration_sec=duration,
            )
            return raw_result

        except Exception as e:
            duration = time.time() - start_time
            AuditLogger.log(
                user_request=user_request,
                tool_name=tool_name,
                arguments=args,
                permission_level=perm_str,
                status="FAILED",
                confirmed=confirmed_flag,
                error=str(e),
                duration_sec=duration,
            )
            return {
                "success": False,
                "tool": tool_name,
                "message": f"I encountered an error executing {tool_name}.",
                "error": str(e),
            }


# Singleton tool manager instance
tool_manager = ToolManager()
