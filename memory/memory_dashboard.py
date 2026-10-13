"""
Memory Dashboard Module for William-1 v0.3.
Provides an interactive terminal dashboard displaying:
1. Personal memories panel
2. Projects panel (status, blocker, next task)
3. Recent events timeline (milestones, decisions, rejected designs)
4. Storage and retention statistics
5. Interactive commands to edit, delete, or manage records under user control.
"""

import os
import sys
import time
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.layout import Layout
    from rich.prompt import Prompt
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

from memory.memory_manager import memory_manager
memory_store = memory_manager.store


class MemoryDashboard:
    """Terminal UI for inspecting and editing long-term memories under user control."""

    def __init__(self):
        self.console = Console() if HAVE_RICH else None

    def render(self):
        """Renders the 4 panels and statistics."""
        if not HAVE_RICH:
            self._render_plain()
            return

        self.console.clear()

        # Header Title
        title_text = Text(
            "[MEMORY] William-1 v0.3 — Personal Memory Dashboard (User Control Panel)",
            style="bold cyan",
        )
        self.console.print(Panel(title_text, border_style="cyan"))

        # Panel 1: Personal Memories
        memories = memory_store.list_memories(limit=15)
        mem_table = Table(title="Personal Memories & Facts", expand=True, border_style="blue")
        mem_table.add_column("ID", style="bold yellow", width=5)
        mem_table.add_column("Category", style="magenta", width=12)
        mem_table.add_column("Content", style="white")
        mem_table.add_column("Updated", style="dim", width=14)

        if memories:
            for m in memories:
                updated = (m.get("updated_at") or "")[:10]
                mem_table.add_row(str(m["id"]), m.get("category", "fact"), m.get("content", ""), updated)
        else:
            mem_table.add_row("-", "empty", "[dim]No active memories saved yet[/dim]", "-")

        # Panel 2: Tracked Projects
        projects = memory_store.list_projects()
        proj_table = Table(title="Tracked Projects", expand=True, border_style="green")
        proj_table.add_column("Project", style="bold green", width=14)
        proj_table.add_column("Status", style="yellow", width=10)
        proj_table.add_column("Current Blocker", style="red")
        proj_table.add_column("Next Recommended Task", style="cyan")

        if projects:
            for p in projects:
                status = p.get("status") or "active"
                blocker = p.get("current_blocker") or "[dim]None[/dim]"
                next_t = p.get("next_task") or "[dim]None[/dim]"
                proj_table.add_row(p.get("name", "Unknown"), status, blocker, next_t)
        else:
            proj_table.add_row("-", "none", "[dim]No projects registered yet[/dim]", "-")

        # Panel 3: Recent Events Timeline
        events_table = Table(title="Recent Events Timeline (Milestones, Decisions, Rejections)", expand=True, border_style="magenta")
        events_table.add_column("Date", style="dim", width=12)
        events_table.add_column("Project", style="cyan", width=12)
        events_table.add_column("Type", style="bold", width=12)
        events_table.add_column("Summary & Details", style="white")

        has_events = False
        for p in (projects or []):
            evs = memory_store.get_project_events(p["id"], limit=6)
            for ev in evs:
                has_events = True
                date_str = (ev.get("created_at") or "")[:10]
                ev_type = ev.get("event_type", "note").lower()
                style_map = {"milestone": "bold green", "decision": "bold yellow", "rejected": "bold red"}
                t_style = style_map.get(ev_type, "white")
                summary = ev.get("summary", "")
                if ev.get("details"):
                    summary += f" ({ev['details']})"
                events_table.add_row(date_str, p.get("name", ""), f"[{t_style}]{ev_type.upper()}[/{t_style}]", summary)

        if not has_events:
            events_table.add_row("-", "-", "none", "[dim]No project events logged yet[/dim]")

        # Panel 4: Storage & Retention Stats
        settings = memory_manager.get_memory_settings()
        enabled = settings.get("enabled", True)
        local_only = settings.get("local_only", False)
        retention = settings.get("retention_days", 90)
        top_k = settings.get("top_k", 5)

        db_path = memory_store.db_path
        db_size_kb = 0
        if os.path.exists(db_path):
            try:
                db_size_kb = os.path.getsize(db_path) / 1024
            except Exception:
                pass

        stats_table = Table(title="Storage & Retention Health", expand=True, border_style="cyan")
        stats_table.add_column("Metric", style="bold white")
        stats_table.add_column("Value", style="bold green")
        stats_table.add_column("Policy Guarantee", style="dim")

        stats_table.add_row("Memory Status", "[bold green]ENABLED[/bold green]" if enabled else "[bold red]DISABLED[/bold red]", "User master kill-switch")
        stats_table.add_row("Local-Only Isolation", "[bold green]ACTIVE[/bold green]" if local_only else "[yellow]ALLOW CLOUD CONTEXT[/yellow]", "Zero cloud exfiltration when True")
        stats_table.add_row("Retention Policy", f"{retention} days", "Automatic pruning of stale memories")
        stats_table.add_row("Max Retrieval Top-K", f"{top_k} items", "Token budget cap per prompt")
        stats_table.add_row("Database File", f"{os.path.basename(db_path)} ({db_size_kb:.1f} KB)", "Local SQLite3 database (user-owned)")

        # Print all 4 panels
        self.console.print(mem_table)
        self.console.print(proj_table)
        self.console.print(events_table)
        self.console.print(stats_table)

    def _render_plain(self):
        """Plain terminal fallback if rich is not installed."""
        print("=" * 70)
        print("  William-1 v0.3 — Personal Memory Dashboard")
        print("=" * 70)
        print("\n--- [Personal Memories] ---")
        for m in memory_store.list_memories(limit=10):
            print(f"[{m['id']}] ({m.get('category')}): {m.get('content')}")
        print("\n--- [Tracked Projects] ---")
        for p in memory_store.list_projects():
            print(f"- {p['name']}: {p.get('status')} | Blocker: {p.get('current_blocker')} | Next: {p.get('next_task')}")
        print("=" * 70)

    def run_interactive(self):
        """Interactive loop for inspecting and editing memories."""
        while True:
            self.render()
            print("\n[Commands]:")
            print("  [d]elete <id>        - Soft-delete a memory record by ID")
            print("  [e]dit <id> <text>   - Update memory record text")
            print("  [f]orget <keyword>   - Delete memories matching keyword")
            print("  [p]roject <name> [status=X] [blocker=Y] [next=Z] - Update project")
            print("  [t]oggle             - Toggle memory storage ENABLED/DISABLED")
            print("  [r]efresh            - Refresh display")
            print("  [q]uit               - Exit dashboard")

            try:
                cmd_line = input("\nMemory Dashboard > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nExiting dashboard.")
                break

            if not cmd_line or cmd_line.lower() in ("r", "refresh"):
                continue

            if cmd_line.lower() in ("q", "quit", "exit"):
                print("Exiting dashboard.")
                break

            parts = cmd_line.split(maxsplit=2)
            action = parts[0].lower()

            if action in ("d", "delete") and len(parts) >= 2:
                try:
                    mid = int(parts[1])
                    res = memory_manager.forget_memory_by_id(mid)
                    print(f"\nResult: {res.get('message')}")
                    time.sleep(1.2)
                except ValueError:
                    print("Invalid memory ID. Must be integer.")
                    time.sleep(1.0)

            elif action in ("e", "edit") and len(parts) >= 3:
                try:
                    mid = int(parts[1])
                    new_text = parts[2].strip()
                    res = memory_store.update_memory(mid, content=new_text)
                    print(f"\nResult: Memory {mid} updated.")
                    time.sleep(1.2)
                except Exception as ex:
                    print(f"Error updating memory: {ex}")
                    time.sleep(1.2)

            elif action in ("f", "forget") and len(parts) >= 2:
                tgt = " ".join(parts[1:])
                res = memory_manager.forget_memory(tgt)
                print(f"\nResult: {res.get('message')}")
                time.sleep(1.2)

            elif action in ("t", "toggle"):
                cur = memory_manager.is_memory_enabled()
                res = memory_manager.set_memory_mode(not cur)
                print(f"\nResult: {res.get('message')}")
                time.sleep(1.2)

            elif action in ("p", "project") and len(parts) >= 2:
                proj_name = parts[1]
                extra = parts[2] if len(parts) > 2 else ""
                status, blocker, next_t = None, None, None
                for token in extra.split():
                    if token.startswith("status="):
                        status = token.split("=", 1)[1]
                    elif token.startswith("blocker="):
                        blocker = token.split("=", 1)[1]
                    elif token.startswith("next="):
                        next_t = token.split("=", 1)[1]
                res = memory_manager.update_project_status(
                    project_name=proj_name,
                    status=status,
                    current_blocker=blocker,
                    next_task=next_t,
                )
                print(f"\nResult: {res.get('message')}")
                time.sleep(1.5)
            else:
                print(f"Unknown command: '{cmd_line}'")
                time.sleep(1.0)


def run_memory_dashboard():
    """Entry point for python main.py --memory."""
    dashboard = MemoryDashboard()
    dashboard.run_interactive()
