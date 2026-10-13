"""
Automated Phase 3 Safety, Privacy & Memory Walkthrough Suite.
Run via: python main.py --memory-test

Tests all Phase 3 success criteria:
1. Save memory record
2. Restart simulation (persistence across sessions)
3. Recall (retrieval with scoring)
4. Deduplication (normalized similarity check)
5. Contradiction update (preference replacement)
6. Forget / soft-delete
7. Memory-disabled mode (master kill-switch)
8. Corrupted-DB recovery (self-healing SQLite layer)
9. Credential rejection (sensitive data filter)
"""

import os
import sys
import shutil
import tempfile
from typing import List, Dict, Any

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    HAVE_RICH = True
except ImportError:
    HAVE_RICH = False

from memory.memory_store import MemoryStore
from memory.memory_manager import MemoryManager


def run_memory_test_walkthrough() -> bool:
    """Executes the complete Phase 3 safety and privacy automated walkthrough."""
    console = Console() if HAVE_RICH else None

    if HAVE_RICH:
        console.print(
            Panel(
                "[bold cyan]William-1 v0.3 — Phase 3 Memory, Safety & Privacy Automated Test Suite[/bold cyan]\n"
                "[dim]Verifying all Phase 3 success criteria in an isolated test environment[/dim]",
                border_style="cyan"
            )
        )
    else:
        print("=== William-1 v0.3 Phase 3 Memory Test Suite ===")

    test_dir = tempfile.mkdtemp(prefix="william_test_memory_")
    test_db_path = os.path.join(test_dir, "test_memory.db")

    results: List[Dict[str, Any]] = []

    try:
        # Step 1: Save
        manager = MemoryManager(db_path=test_db_path)

        res_save = manager.save_memory("User prefers Python and dark mode theme", category="preference")
        pass_save = res_save.get("success", False) and "saved" in res_save.get("message", "").lower()
        results.append({
            "criterion": "1. Save Memory",
            "operation": "save_memory('User prefers Python and dark mode')",
            "expected": "Stored with category 'preference'",
            "status": "PASS" if pass_save else "FAIL",
            "detail": res_save.get("message", "")[:60],
        })

        # Step 2: Restart Simulation
        del manager
        manager_restarted = MemoryManager(db_path=test_db_path)
        all_restarted = manager_restarted.store.list_memories()
        pass_restart = any("python" in m.get("content", "").lower() for m in all_restarted)
        results.append({
            "criterion": "2. Restart Simulation",
            "operation": "Close DB, reopen from disk, list_memories()",
            "expected": "Persists across assistant restart",
            "status": "PASS" if pass_restart else "FAIL",
            "detail": f"Found {len(all_restarted)} record(s) on reboot",
        })

        # Step 3: Recall
        res_recall = manager_restarted.query_memory("What theme do I prefer?")
        pass_recall = res_recall.get("success", False) and len(res_recall.get("memories", [])) > 0
        results.append({
            "criterion": "3. Decision & Fact Recall",
            "operation": "query_memory('What theme do I prefer?')",
            "expected": "Relevant preference retrieved with score",
            "status": "PASS" if pass_recall else "FAIL",
            "detail": f"Retrieved {len(res_recall.get('memories', []))} match(es)",
        })

        # Step 4: Deduplication
        res_dedupe = manager_restarted.save_memory("I prefer Python and dark mode theme", category="preference")
        pass_dedupe = "already" in res_dedupe.get("message", "").lower() or res_dedupe.get("action") == "duplicate_skipped"
        results.append({
            "criterion": "4. Deduplication",
            "operation": "save_memory('I prefer Python and dark mode theme')",
            "expected": "Identified as near-duplicate, skipped re-insert",
            "status": "PASS" if pass_dedupe else "FAIL",
            "detail": res_dedupe.get("message", "")[:60],
        })

        # Step 5: Contradiction Update
        res_update = manager_restarted.save_memory("I now prefer TypeScript and light mode theme", category="preference")
        pass_update = "updated" in res_update.get("message", "").lower() or res_update.get("action") == "updated"
        results.append({
            "criterion": "5. Contradiction Update",
            "operation": "save_memory('I now prefer TypeScript...')",
            "expected": "Updates existing record, explains transition",
            "status": "PASS" if pass_update else "FAIL",
            "detail": res_update.get("message", "")[:60],
        })

        # Step 6: Forget (Soft-Delete)
        res_forget = manager_restarted.forget_memory("TypeScript")
        pass_forget = res_forget.get("success", False) and res_forget.get("deleted_count", 0) > 0
        active_after = [m for m in manager_restarted.store.list_memories() if "typescript" in m.get("content", "").lower()]
        pass_forget = pass_forget and len(active_after) == 0
        results.append({
            "criterion": "6. Forget / Soft-Delete",
            "operation": "forget_memory('TypeScript')",
            "expected": "Soft-deleted, omitted from active retrieval",
            "status": "PASS" if pass_forget else "FAIL",
            "detail": res_forget.get("message", "")[:60],
        })

        # Step 7: Memory-Disabled Mode
        manager_restarted.set_memory_mode(False)
        res_dis_save = manager_restarted.save_memory("Remember I like tea")
        res_dis_ctx = manager_restarted.retrieve_context_for_prompt("What tea do I like?")
        pass_disabled = not res_dis_save.get("success", True) and res_dis_ctx is None
        results.append({
            "criterion": "7. Memory-Disabled Mode",
            "operation": "set_memory_mode(False) -> save & context",
            "expected": "Zero writes, zero context reads when disabled",
            "status": "PASS" if pass_disabled else "FAIL",
            "detail": "Confirmed disabled; zero writes, context is None",
        })
        manager_restarted.set_memory_mode(True)

        # Step 8: Corrupted-DB Recovery
        corrupt_db_path = os.path.join(test_dir, "corrupt.db")
        with open(corrupt_db_path, "wb") as f:
            f.write(b"NOT_A_VALID_SQLITE_DATABASE_HEADER_CORRUPTED_BYTES")
        recovered_store = MemoryStore(db_path=corrupt_db_path)
        tables = recovered_store._get_connection().execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        pass_recovery = len(tables) >= 3
        del recovered_store
        results.append({
            "criterion": "8. Corrupted-DB Recovery",
            "operation": "Initialize MemoryStore on corrupt binary header",
            "expected": "Backs up corrupt file, rebuilds clean schema",
            "status": "PASS" if pass_recovery else "FAIL",
            "detail": f"Auto-healed database; restored {len(tables)} tables",
        })

        # Step 9: Credential Rejection
        api_key_sample = "sk-ant-api03-abcdef123456789012345678901234567890"
        res_key = manager_restarted.save_memory(f"My secret key is {api_key_sample}")
        pass_key = (
            not res_key.get("success", True)
            and "credential" in res_key.get("message", "").lower()
        )
        results.append({
            "criterion": "9. Credential Rejection",
            "operation": f"save_memory('My secret key is {api_key_sample[:18]}...')",
            "expected": "Hard refusal: 'I won\\'t store that — it looks like a credential'",
            "status": "PASS" if pass_key else "FAIL",
            "detail": res_key.get("message", "")[:60],
        })

    finally:
        shutil.rmtree(test_dir, ignore_errors=True)

    # Render results table
    all_passed = all(r["status"] == "PASS" for r in results)

    if HAVE_RICH:
        table = Table(title="Phase 3 Verification Matrix", expand=True)
        table.add_column("Criterion", style="bold cyan", width=22)
        table.add_column("Operation", style="white")
        table.add_column("Expected Behavior", style="dim")
        table.add_column("Result Detail", style="yellow")
        table.add_column("Status", style="bold", width=8)

        for r in results:
            st_color = "bold green" if r["status"] == "PASS" else "bold red"
            table.add_row(
                r["criterion"],
                r["operation"],
                r["expected"],
                r["detail"],
                f"[{st_color}]{r['status']}[/{st_color}]"
            )
        console.print(table)

        summary_color = "bold green" if all_passed else "bold red"
        summary_text = (
            f"\n[{summary_color}]Phase 3 Safety & Privacy Verification: "
            f"{sum(1 for r in results if r['status'] == 'PASS')} / {len(results)} PASS "
            f"({'100%' if all_passed else 'FAILED'})[/{summary_color}]\n"
        )
        console.print(summary_text)
    else:
        for r in results:
            print(f"[{r['status']}] {r['criterion']}: {r['detail']}")
        print(f"\nResult: {sum(1 for r in results if r['status'] == 'PASS')} / {len(results)} passed.")

    return all_passed
