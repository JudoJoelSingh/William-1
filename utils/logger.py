"""
Audit Logger Module for William-1 (v0.2).
Provides dual persistent logging:
1. Human-readable text audit trail (logs/william_audit.log)
2. Machine-readable structured JSONL action log (logs/william_actions.jsonl)
"""

import os
import json
import threading
from datetime import datetime
from typing import Dict, Any, Optional
from config import config


class AuditLogger:
    """Thread-safe persistent audit and structured action logger for all assistant tool interactions."""

    _lock = threading.Lock()

    @classmethod
    def log(
        cls,
        user_request: str,
        tool_name: str,
        arguments: Dict[str, Any],
        permission_level: str,
        status: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
        confirmed: Optional[bool] = None,
        duration_sec: float = 0.0,
    ):
        """
        Appends both human-readable and machine-readable JSONL entries to the audit logs.
        status options: "CONFIRMED", "EXECUTED", "DENIED", "FAILED", "CANCELLED", "BLOCKED"
        """
        if not config.AUDIT_LOG_ENABLED:
            return

        now = datetime.now()
        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        iso_timestamp = now.isoformat()

        # 1. Human-readable format
        args_str = json.dumps(arguments, ensure_ascii=False)
        human_line = (
            f"[{timestamp_str}] | USER: {user_request!r} | TOOL: {tool_name} | "
            f"ARGS: {args_str} | PERM: {permission_level} | STATUS: {status} | "
            f"DURATION: {duration_sec:.3f}s | RESULT: {result or error or 'None'}\n"
        )

        # 2. Machine-readable JSONL action record
        jsonl_record = {
            "timestamp": iso_timestamp,
            "transcript": user_request,
            "tool": tool_name,
            "arguments": arguments,
            "permission_level": permission_level,
            "confirmed": confirmed if confirmed is not None else (status in ("CONFIRMED", "EXECUTED")),
            "status": status,
            "duration_sec": round(duration_sec, 4),
            "result": result,
            "error": error,
        }
        jsonl_line = json.dumps(jsonl_record, ensure_ascii=False) + "\n"

        with cls._lock:
            try:
                # Ensure log directory exists
                log_dir = os.path.dirname(config.AUDIT_LOG_FILE)
                if log_dir:
                    os.makedirs(log_dir, exist_ok=True)

                # Write human-readable text log
                with open(config.AUDIT_LOG_FILE, "a", encoding="utf-8") as f_text:
                    f_text.write(human_line)

                # Write machine-readable JSONL action log
                with open(config.JSONL_LOG_FILE, "a", encoding="utf-8") as f_jsonl:
                    f_jsonl.write(jsonl_line)

                # Feed real-time event to live dashboard if active
                try:
                    from ui import dashboard
                    if dashboard:
                        dashboard.add_log(
                            tool_name=tool_name,
                            perm_level=permission_level,
                            status=status,
                            message=str(result or error or "Done"),
                        )
                except Exception:
                    pass

            except Exception as e:
                if config.DEBUG:
                    print(f"[AuditLogger Error] Failed to write log: {e}")
