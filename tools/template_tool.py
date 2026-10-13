"""
Template Tool Implementation and Extensibility Guide for William-1 (v0.2).
===========================================================================

This module serves as the canonical reference implementation and developer guide
for extending William-1 with new capabilities while strictly preserving the Phase 2
security boundary: zero arbitrary execution, explicit typed registries, tiered
permissions, root-confined sandboxes, and observable audit trails.

ARCHITECTURAL LIFECYCLE OF A TOOL CALL:
---------------------------------------
1. AI Intent: The LLM emits a typed tool call (e.g., {"tool": "get_system_uptime", "arguments": {}}).
2. Registry Lookup: ToolManager verifies the tool name exists in its approved registry.
3. OS Compatibility: ToolManager verifies the current host OS is in supported_platforms.
4. Kill-Switch Check: If the tool is Level 3 (Destructive) and DISABLE_L3_TOOLS=True, blocked immediately.
5. Argument Validation: Type checks (int/str), range bounds (_range/_min), and path sandboxing (_is_path).
6. Security Confirmation:
   - Level 1 (Safe): Executes immediately without user interruption.
   - Level 2 (Sensitive): Requires explicit affirmative confirmation ("Do you want me to proceed?").
   - Level 3 (Destructive): Strong confirmation naming consequences ("This permanent action cannot be undone...").
7. Sandboxed Execution: The Python function runs cleanly without arbitrary shell execution.
8. Dual Audit Logging: Every call records human audit text and structured JSONL action data.
9. Spoken Narration: Spoken intent announced before acting ("Checking system uptime... done"),
   followed by a single natural conversational response reporting the result.

===========================================================================
DEVELOPER GUIDE: HOW TO ADD A NEW TOOL IN 4 STEPS
===========================================================================

Step 1: Write the tool function
-------------------------------
Create your safe Python function in a module under `tools/` (e.g., `tools/template_tool.py`).
Rules:
- Never invoke arbitrary shell execution (`os.system` is prohibited).
- Always validate arguments and enforce bounds.
- Always return a structured dictionary conforming to:
  {
      "success": bool,
      "message": str,                # Natural spoken phrase
      "data": dict,                  # Machine-readable payload
      "alternative": Optional[dict], # Nearest safe alternative if action failed
      "error": Optional[str]         # Error diagnostic if failed
  }

Step 2: Assign a Permission Level
---------------------------------
In `security/permissions.py`, add your tool to `TOOL_PERMISSIONS`:
```python
TOOL_PERMISSIONS["get_system_uptime"] = PermissionLevel.LEVEL_1_SAFE
```
If Level 2 or Level 3, also register a consequence prompt in `CONSEQUENCE_DESCRIPTIONS`:
```python
CONSEQUENCE_DESCRIPTIONS["clear_temporary_cache"] = "Clearing the cache will remove cached session data."
```

Step 3: Register in ToolManager
-------------------------------
In `tools/tool_manager.py`, import the function and register its schema:
```python
self.register_tool(
    name="get_system_uptime",
    func=get_system_uptime,
    description="Gets how long the computer has been powered on and running.",
    parameters={
        "detailed": {
            "type": "boolean",
            "description": "Whether to return detailed hours, minutes, and boot timestamp."
        }
    },
    required_params=[],
    type_specs={"detailed": bool},
    supported_platforms=["Windows", "Linux", "Darwin"],
)
```

Step 4: Verify in Safety and Demo Suites
----------------------------------------
Run `python main.py --demo` and `python main.py --safety-test` to ensure
the registry, schemas, and security boundaries validate cleanly.

===========================================================================
REFERENCE IMPLEMENTATION: SYSTEM UPTIME TOOL
===========================================================================
"""

import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

try:
    import psutil
except ImportError:
    psutil = None


def get_system_uptime(detailed: bool = False) -> Dict[str, Any]:
    """
    Retrieves system uptime in natural human prose.
    Level 1 (Safe) - Read-only telemetry.

    Args:
        detailed (bool): If True, returns full boot timestamp and breakdown.

    Returns:
        Dict[str, Any]: Structured tool result.
    """
    if psutil is None:
        return {
            "success": False,
            "message": "System telemetry utilities are unavailable on this machine.",
            "error": "psutil library is not installed.",
            "alternative": {
                "tool": "get_datetime",
                "arguments": {},
                "suggestion": "Check current date and time instead"
            }
        }

    try:
        boot_timestamp = psutil.boot_time()
        uptime_seconds = time.time() - boot_timestamp
        uptime_delta = timedelta(seconds=int(uptime_seconds))

        days = uptime_delta.days
        hours, remainder = divmod(uptime_delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        # Build natural human phrasing
        time_parts = []
        if days > 0:
            time_parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            time_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0 or not time_parts:
            time_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

        uptime_str = ", ".join(time_parts)
        boot_dt = datetime.fromtimestamp(boot_timestamp).strftime("%A, %B %d at %I:%M %p")

        if detailed:
            msg = f"Your computer has been running for {uptime_str}, since {boot_dt}."
        else:
            msg = f"Your computer has been running for {uptime_str}."

        return {
            "success": True,
            "message": msg,
            "data": {
                "uptime_seconds": int(uptime_seconds),
                "uptime_formatted": uptime_str,
                "boot_time": boot_dt,
                "days": days,
                "hours": hours,
                "minutes": minutes,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Could not determine system uptime.",
            "error": str(e),
            "alternative": {
                "tool": "get_system_health",
                "arguments": {},
                "suggestion": "Check overall system health instead"
            }
        }


def sample_sensitive_action_template(target_item: str) -> Dict[str, Any]:
    """
    Example template for a sensitive (Level 2) state modification tool.
    Demonstrates argument validation, graceful degradation, and structured returns.
    """
    if not target_item or not target_item.strip():
        return {
            "success": False,
            "message": "Please specify a target item to modify.",
            "error": "Missing required argument 'target_item'.",
            "alternative": {
                "tool": "list_directory",
                "arguments": {"folder": "workspace"},
                "suggestion": "List available files in workspace"
            }
        }

    # Action logic executes safely within sandbox
    # ...
    return {
        "success": True,
        "message": f"Successfully performed action on {target_item}.",
        "data": {"target": target_item, "timestamp": time.time()}
    }


# ===========================================================================
# ROADMAP SCALING NOTES (PHASES 3 TO 5)
# ===========================================================================
# Phase 3 (Personal Memory):
#   - Tools like `remember_preference(key, value)`, `query_memory(topic)`.
#   - Memory graph storage stored in local SQLite / vector index with privacy tiers.
#
# Phase 4 (Vision & Web Automation):
#   - Tools like `inspect_screen(query)`, `click_ui_element(label)`, `scrape_webpage(url)`.
#   - Visual boundary confirmation before clicking sensitive buttons.
#
# Phase 5 (Local AI & Autonomous Agents):
#   - Tools run directly against local quantized LLMs (e.g., Llama 3 / Mistral via llama.cpp).
#   - Multi-step planning with verifiable guardrails and execution timeouts.
