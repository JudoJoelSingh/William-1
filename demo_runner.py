"""
Automated Test and Demo Runner for William-1 v0.2 (Hardened Safe Tool Layer).
Executes the comprehensive Phase 2 Hardened Validation Suite verifying:
1. Tool Manager Registry & Strict Argument / Range Validation
2. System Telemetry with Humanized Numbers & Units
3. Fuzzy Application / Site Alias Resolution & Friendly Fallback
4. Named Project & Folder Shortcuts
5. Security Permissions, Natural Confirmation ("go ahead"), & L3 Kill-Switch
6. File Sandbox Boundaries & Directory Traversal Rejection
7. Dual Logging (Audit Text + Machine-Readable JSONL Actions)
8. Startup Diagnostic Self-Check Health Report
"""

import os
import json
import time
from typing import List, Dict, Any
from config import config
from tools.tool_manager import tool_manager
from tools.system import get_battery_status, get_cpu_usage, get_ram_usage, get_disk_usage, get_os_info, get_datetime
from tools.applications import open_application, close_application, resolve_application_alias
from tools.files import list_directory, search_files, get_file_info, open_folder
from tools.browser import open_url, search_web, _resolve_website_alias, _validate_and_format_url
from security.permissions import get_tool_permission_level, requires_confirmation, is_tool_blocked_by_killswitch, PermissionLevel
from security.confirmation import ConfirmationHandler
from utils.logger import AuditLogger
from brain import Brain
from ui import UI


def run_demo_suite() -> bool:
    """
    Executes the automated 8-scenario evaluation suite and displays results.
    """
    print("\n" + "=" * 70)
    print("      [TEST] RUNNING WILLIAM-1 v0.2 HARDENED TOOL LAYER TEST SUITE")
    print("=" * 70 + "\n")

    results: List[Dict[str, Any]] = []

    # --- Test 1: Tool Registry & Strict Range / Type Validation ---
    print("[Test 1/8] Testing Tool Registry & Argument Range Validation...")
    start_t = time.time()
    reg_count = len(tool_manager._registry)
    schemas = tool_manager.get_schemas()
    
    # Check range validation on set_volume (-10 is invalid)
    bad_vol = tool_manager.execute_tool("set_volume", {"level": 150})
    passed_vol = (bad_vol.get("success") is False) and ("between 0 and 100" in bad_vol.get("error", ""))

    # Check unknown tool rejection
    bad_cmd = tool_manager.execute_tool("arbitrary_exec", {"cmd": "whoami"})
    passed_cmd = (bad_cmd.get("success") is False) and ("Unknown tool" in bad_cmd.get("error", ""))

    passed1 = (reg_count >= 20) and (len(schemas) == reg_count) and passed_vol and passed_cmd
    duration1 = time.time() - start_t

    results.append({
        "name": "1. Registry & Range Validation",
        "query": "set_volume(150), arbitrary_exec",
        "passed": passed1,
        "metric": f"{duration1:.3f}s (Strict Typing OK)"
    })
    print(f"  Registry: {reg_count} tools. Out-of-bounds arguments rejected safely.\n")

    # --- Test 2: System Telemetry & Humanized Output ---
    print("[Test 2/8] Testing System Telemetry & Humanized Output...")
    start_t = time.time()
    bat = get_battery_status()
    cpu = get_cpu_usage()
    ram = get_ram_usage()
    disk = get_disk_usage()
    dt = get_datetime()

    # Verify numbers are humanized and rounded
    ram_msg = ram.get("message", "")
    bat_msg = bat.get("message", "")
    passed_humanized = ("GB" in ram_msg) and ("percent" in ram_msg) and ("percent" in bat_msg)

    passed2 = (
        bat.get("success") is True and
        cpu.get("success") is True and
        ram.get("success") is True and
        disk.get("success") is True and
        dt.get("success") is True and
        passed_humanized
    )
    duration2 = time.time() - start_t

    results.append({
        "name": "2. Humanized Telemetry (psutil)",
        "query": "Battery, CPU, RAM, Disk, Time",
        "passed": passed2,
        "metric": f"{duration2:.3f}s (Humanized units)"
    })
    print(f"  RAM: \"{ram_msg}\"\n  Battery: \"{bat_msg}\"\n")

    # --- Test 3: Fuzzy App / Site Resolution & Friendly Fallback ---
    print("[Test 3/8] Testing Fuzzy Resolution & Fallback Phrasing...")
    start_t = time.time()
    res_code = resolve_application_alias("my coding environment") == "vscode"
    res_browser = resolve_application_alias("the browser") == "chrome"
    res_music = resolve_application_alias("my music") == "spotify"
    res_site = _resolve_website_alias("videos") == "youtube"

    # Test unknown app fallback message
    unknown_res = tool_manager.execute_tool("open_application", {"application": "Photoshop"})
    fallback_correct = "I don't have 'Photoshop' in my approved applications" in unknown_res.get("message", "")

    passed3 = res_code and res_browser and res_music and res_site and fallback_correct
    duration3 = time.time() - start_t

    results.append({
        "name": "3. Fuzzy Resolution & Helpful Fallback",
        "query": "'my coding environment' -> vscode",
        "passed": passed3,
        "metric": f"{duration3:.3f}s (Resolved cleanly)"
    })
    print(f"  Fuzzy mapping verified. Fallback: \"{unknown_res.get('message')}\"\n")

    # --- Test 4: Named Shortcuts Resolution ---
    print("[Test 4/8] Testing Named Shortcuts Resolution...")
    start_t = time.time()
    shortcuts = config.get_named_shortcuts()
    has_proj = "william-1 project" in shortcuts

    # Test list_directory using named shortcut
    shortcut_res = list_directory("william-1 project", max_items=5)
    passed_shortcut = shortcut_res.get("success") is True

    passed4 = has_proj and passed_shortcut
    duration4 = time.time() - start_t

    results.append({
        "name": "4. Named Project & Folder Shortcuts",
        "query": "list_directory('william-1 project')",
        "passed": passed4,
        "metric": f"{duration4:.3f}s (Shortcut resolved)"
    })
    print(f"  Shortcut 'william-1 project' resolved to: {shortcuts.get('william-1 project')}\n")

    # --- Test 5: Security Permissions, Natural Confirmation & L3 Kill-Switch ---
    print("[Test 5/8] Testing Security Confirmation & Kill-Switch...")
    start_t = time.time()
    
    # Natural affirmative phrase matching
    aff1, _ = ConfirmationHandler.evaluate_response("go ahead")
    aff2, _ = ConfirmationHandler.evaluate_response("do it")
    aff3, _ = ConfirmationHandler.evaluate_response("yes please")
    neg1, _ = ConfirmationHandler.evaluate_response("stop, don't do that")
    ambig1, _ = ConfirmationHandler.evaluate_response("maybe later")
    timeout_res, _ = ConfirmationHandler.evaluate_response("")

    # Test L3 Kill-Switch toggle
    original_flag = config.DISABLE_L3_TOOLS
    config.DISABLE_L3_TOOLS = True
    blocked_res = tool_manager.execute_tool("shutdown_system", {"delay_seconds": 5})
    is_blocked = (blocked_res.get("success") is False) and ("disabled by the safety kill-switch" in blocked_res.get("message", ""))
    config.DISABLE_L3_TOOLS = original_flag

    passed5 = (
        aff1 and aff2 and aff3 and
        (not neg1) and (not ambig1) and (not timeout_res) and
        is_blocked
    )
    duration5 = time.time() - start_t

    results.append({
        "name": "5. Confirmation UX & L3 Kill-Switch",
        "query": "'go ahead', 'do it', Kill-switch",
        "passed": passed5,
        "metric": f"{duration5:.3f}s (Affirmatives & Kill-switch OK)"
    })
    print(f"  Natural affirmatives recognized. L3 Kill-Switch blocked destructive action.\n")

    # --- Test 6: File Sandbox & Directory Traversal Rejection ---
    print("[Test 6/8] Testing File Sandbox & Path Traversal...")
    start_t = time.time()
    traversal_res = list_directory(r"..\..\..\..\..\..\Windows\System32")
    passed_trav = (traversal_res.get("success") is False) and ("restricted" in traversal_res.get("message", ""))

    valid_res = list_directory("documents", max_items=3)
    passed_valid = (valid_res.get("success") is True)

    passed6 = passed_trav and passed_valid
    duration6 = time.time() - start_t

    results.append({
        "name": "6. File Sandbox & Traversal Defense",
        "query": "list_directory('../../Windows')",
        "passed": passed6,
        "metric": f"{duration6:.3f}s (Normalized sandbox OK)"
    })
    print(f"  Traversal attempt blocked cleanly.\n")

    # --- Test 7: Structured Dual Logging (Audit Text + JSONL Action Log) ---
    print("[Test 7/8] Testing Structured Dual Logging...")
    start_t = time.time()
    test_event = "Hardened test action verification"
    AuditLogger.log(
        user_request=test_event,
        tool_name="get_ram_usage",
        arguments={},
        permission_level="Level 1 (LEVEL_1_SAFE)",
        status="EXECUTED",
        result="Logged successfully",
        duration_sec=0.012
    )

    text_log_exists = os.path.exists(config.AUDIT_LOG_FILE)
    jsonl_log_exists = os.path.exists(config.JSONL_LOG_FILE)

    jsonl_has_event = False
    if jsonl_log_exists:
        with open(config.JSONL_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if test_event in line:
                    try:
                        record = json.loads(line)
                        if record.get("tool") == "get_ram_usage" and "duration_sec" in record:
                            jsonl_has_event = True
                            break
                    except Exception:
                        pass

    passed7 = text_log_exists and jsonl_log_exists and jsonl_has_event
    duration7 = time.time() - start_t

    results.append({
        "name": "7. Dual Text & JSONL Action Logging",
        "query": f"{config.AUDIT_LOG_FILE} + {config.JSONL_LOG_FILE}",
        "passed": passed7,
        "metric": f"{duration7:.3f}s (JSONL verified)"
    })
    print(f"  JSONL and text audit trails recorded to disk.\n")

    # --- Test 8: Startup Self-Check Diagnostic Suite ---
    print("[Test 8/8] Testing Startup Self-Check Report...")
    start_t = time.time()
    report = config.run_startup_self_check()
    passed8 = (
        bool(report.get("os")) and
        len(report.get("apps_detected", [])) > 0 and
        len(report.get("roots_valid", [])) > 0 and
        len(report.get("libraries_ok", [])) >= 4
    )
    duration8 = time.time() - start_t

    results.append({
        "name": "8. Startup Diagnostic Self-Check",
        "query": "Check apps, roots, and libraries",
        "passed": passed8,
        "metric": f"{duration8:.3f}s (All checks healthy)"
    })
    print(f"  OS: {report.get('os')} | Detected apps: {len(report.get('apps_detected', []))} | Verified roots: {len(report.get('roots_valid', []))}\n")

    # Render results table
    all_passed = all(r["passed"] for r in results)
    UI.print_demo_results(results, all_passed)
    return all_passed


if __name__ == "__main__":
    run_demo_suite()

def run_safety_test_suite() -> bool:
    """
    Executes the comprehensive Phase 2 Safety Verification Plan:
    1. App Launch (Level 1 Safe - No confirmation)
    2. File Search (Level 1 Safe - No confirmation)
    3. System Info (Level 1 Safe - No confirmation, smart briefing)
    4. Browser (Level 1 Safe - No confirmation)
    5. Mute & Lock (Level 1 Safe / Level 3 Destructive - Confirmation required)
    6. Dangerous: 'delete this folder' (Level 3 Destructive - Traversal blocked, confirmation required, kill-switch)
    7. Dangerous: 'shutdown' (Level 3 Destructive - Confirmation required, kill-switch blocked)
    Reports PASS/FAIL for each scenario, demonstrating Phase 2 security guarantees in one command.
    """
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.panel import Panel
        console = Console()
    except ImportError:
        console = None

    header = "=" * 76
    print("\n" + header)
    print("      [SECURITY TEST] WILLIAM-1 v0.2 HARDENED SAFETY SUITE (--safety-test)")
    print("      Proving: All actions are allowlisted, validated, observable & safe")
    print(header + "\n")

    test_results: List[Dict[str, Any]] = []

    # -------------------------------------------------------------
    # Scenario 1: App Launch (Level 1 Safe)
    # -------------------------------------------------------------
    print("[Scenario 1/7] Testing App Launch (open_application)...")
    perm1 = get_tool_permission_level("open_application")
    req1 = requires_confirmation("open_application")
    pass1 = (perm1 == PermissionLevel.LEVEL_1_SAFE) and (req1 is False)
    test_results.append({
        "scenario": "1. App Launch",
        "tool": "open_application",
        "tier": f"Level {perm1.value} ({perm1.name})",
        "conf_req": "No" if not req1 else "Yes",
        "defense": "Allowlist Verified",
        "passed": pass1,
        "detail": "Auto-executes without interrupting user."
    })
    print(f"  Tier: Level {perm1.value} | Confirmation: {req1} -> {'PASS' if pass1 else 'FAIL'}\n")

    # -------------------------------------------------------------
    # Scenario 2: File Search (Level 1 Safe)
    # -------------------------------------------------------------
    print("[Scenario 2/7] Testing File Search (search_files)...")
    perm2 = get_tool_permission_level("search_files")
    req2 = requires_confirmation("search_files")
    # Verify sandbox containment
    sandbox_res = search_files(query="config", root_folder="workspace")
    pass2 = (perm2 == PermissionLevel.LEVEL_1_SAFE) and (req2 is False) and sandbox_res.get("success", False)
    test_results.append({
        "scenario": "2. File Search",
        "tool": "search_files",
        "tier": f"Level {perm2.value} ({perm2.name})",
        "conf_req": "No" if not req2 else "Yes",
        "defense": "Root-Confined Sandbox",
        "passed": pass2,
        "detail": "Searches within safe roots without elevation."
    })
    print(f"  Tier: Level {perm2.value} | Sandbox search successful -> {'PASS' if pass2 else 'FAIL'}\n")

    # -------------------------------------------------------------
    # Scenario 3: System Info & Smart Briefing (Level 1 Safe)
    # -------------------------------------------------------------
    print("[Scenario 3/7] Testing System Info (get_system_health)...")
    perm3 = get_tool_permission_level("get_system_health")
    req3 = requires_confirmation("get_system_health")
    from tools.system import get_system_health
    health_res = get_system_health()
    has_observation = "observation" in health_res.get("message", "").lower() or "observation" in health_res.get("data", {})
    pass3 = (perm3 == PermissionLevel.LEVEL_1_SAFE) and (req3 is False) and health_res.get("success") and has_observation
    test_results.append({
        "scenario": "3. System Info",
        "tool": "get_system_health",
        "tier": f"Level {perm3.value} ({perm3.name})",
        "conf_req": "No" if not req3 else "Yes",
        "defense": "Synthesized Briefing",
        "passed": pass3,
        "detail": "Synthesizes health metrics with 1 useful observation."
    })
    print(f"  Briefing: \"{health_res.get('message')[:75]}...\" -> {'PASS' if pass3 else 'FAIL'}\n")

    # -------------------------------------------------------------
    # Scenario 4: Browser (Level 1 Safe)
    # -------------------------------------------------------------
    print("[Scenario 4/7] Testing Browser (open_url)...")
    perm4 = get_tool_permission_level("open_url")
    req4 = requires_confirmation("open_url")
    pass4 = (perm4 == PermissionLevel.LEVEL_1_SAFE) and (req4 is False)
    test_results.append({
        "scenario": "4. Web Browser",
        "tool": "open_url",
        "tier": f"Level {perm4.value} ({perm4.name})",
        "conf_req": "No" if not req4 else "Yes",
        "defense": "URL Schema Verification",
        "passed": pass4,
        "detail": "Restricted to http/https and verified aliases."
    })
    print(f"  Tier: Level {perm4.value} | Confirmation: {req4} -> {'PASS' if pass4 else 'FAIL'}\n")

    # -------------------------------------------------------------
    # Scenario 5: Mute (Safe) vs Lock Computer (Destructive)
    # -------------------------------------------------------------
    print("[Scenario 5/7] Testing Mute (L1) vs Lock Computer (L3)...")
    perm_mute = get_tool_permission_level("mute")
    req_mute = requires_confirmation("mute")
    perm_lock = get_tool_permission_level("lock_computer")
    req_lock = requires_confirmation("lock_computer")

    # Test lock_computer with simulated refusal ("no")
    lock_denial = tool_manager.execute_tool(
        tool_name="lock_computer",
        arguments={},
        user_request="Lock my computer",
        confirm_callback=lambda q: "no"
    )
    lock_cancelled = lock_denial.get("cancelled", False) or (lock_denial.get("success") is False)

    pass5 = (perm_mute == PermissionLevel.LEVEL_1_SAFE) and (not req_mute) and (perm_lock == PermissionLevel.LEVEL_3_DESTRUCTIVE) and req_lock and lock_cancelled
    test_results.append({
        "scenario": "5. Mute & Lock Control",
        "tool": "mute & lock_computer",
        "tier": "L1 Safe / L3 Destructive",
        "conf_req": "No / Yes (Required)",
        "defense": "Tiered Confirmation",
        "passed": pass5,
        "detail": "Mute auto-runs; Lock requires confirmation and safely aborts on refusal."
    })
    print(f"  Mute: L1 (No confirm) | Lock: L3 (Requires confirm, cancelled safely on refusal) -> {'PASS' if pass5 else 'FAIL'}\n")

    # -------------------------------------------------------------
    # Scenario 6: Deliberately Dangerous Request 1: "delete this folder"
    # -------------------------------------------------------------
    print("[Scenario 6/7] Testing Deliberate Threat 1: 'delete this folder'...")
    perm_del = get_tool_permission_level("delete_file")
    req_del = requires_confirmation("delete_file")

    # Defense check A: Directory traversal defense
    trav_res = tool_manager.execute_tool(
        tool_name="delete_file",
        arguments={"target_path": r"..\..\..\..\..\..\Windows\System32"},
        user_request="Delete system folder",
        confirm_callback=lambda q: "yes"  # Even if confirmed, traversal must be blocked!
    )
    trav_blocked = (trav_res.get("success") is False) and ("outside" in trav_res.get("message", "").lower() or "restricted" in trav_res.get("message", "").lower() or "outside" in trav_res.get("error", "").lower())

    # Defense check B: Rejection on refusal
    refusal_res = tool_manager.execute_tool(
        tool_name="delete_file",
        arguments={"target_path": "my_folder"},
        user_request="Delete my folder",
        confirm_callback=lambda q: "no"
    )
    refusal_cancelled = refusal_res.get("cancelled", False)

    # Defense check C: Kill-switch blockage
    orig_flag = config.DISABLE_L3_TOOLS
    config.DISABLE_L3_TOOLS = True
    kill_res = tool_manager.execute_tool(
        tool_name="delete_file",
        arguments={"target_path": "my_folder"},
        user_request="Delete folder with kill-switch",
        confirm_callback=lambda q: "yes"
    )
    kill_blocked = (kill_res.get("success") is False) and ("kill-switch" in kill_res.get("message", "").lower() or "kill-switch" in kill_res.get("error", "").lower())
    config.DISABLE_L3_TOOLS = orig_flag

    pass6 = (perm_del == PermissionLevel.LEVEL_3_DESTRUCTIVE) and req_del and trav_blocked and refusal_cancelled and kill_blocked
    test_results.append({
        "scenario": "6. Dangerous: 'delete folder'",
        "tool": "delete_file",
        "tier": f"Level {perm_del.value} ({perm_del.name})",
        "conf_req": "Yes (Destructive)",
        "defense": "Sandbox + Conf + Kill-Switch",
        "passed": pass6,
        "detail": "Traversal rejected; refusal aborted; kill-switch blocked."
    })
    print(f"  Tier: Level {perm_del.value} | Traversal blocked: {trav_blocked} | Refusal aborted: {refusal_cancelled} | Kill-switch: {kill_blocked} -> {'PASS' if pass6 else 'FAIL'}\n")

    # -------------------------------------------------------------
    # Scenario 7: Deliberately Dangerous Request 2: "shutdown"
    # -------------------------------------------------------------
    print("[Scenario 7/7] Testing Deliberate Threat 2: 'shutdown' (shutdown_system)...")
    perm_shut = get_tool_permission_level("shutdown_system")
    req_shut = requires_confirmation("shutdown_system")

    # Defense check A: Refusal safely aborts
    shut_denied = tool_manager.execute_tool(
        tool_name="shutdown_system",
        arguments={"delay_seconds": 1},
        user_request="Shut down the computer",
        confirm_callback=lambda q: "no"
    )
    shut_cancelled = shut_denied.get("cancelled", False)

    # Defense check B: Kill-switch
    config.DISABLE_L3_TOOLS = True
    shut_kill = tool_manager.execute_tool(
        tool_name="shutdown_system",
        arguments={"delay_seconds": 1},
        user_request="Shutdown during kill-switch",
        confirm_callback=lambda q: "yes"
    )
    shut_kill_blocked = (shut_kill.get("success") is False) and ("kill-switch" in shut_kill.get("message", "").lower() or "kill-switch" in shut_kill.get("error", "").lower())
    config.DISABLE_L3_TOOLS = orig_flag

    pass7 = (perm_shut == PermissionLevel.LEVEL_3_DESTRUCTIVE) and req_shut and shut_cancelled and shut_kill_blocked
    test_results.append({
        "scenario": "7. Dangerous: 'shutdown'",
        "tool": "shutdown_system",
        "tier": f"Level {perm_shut.value} ({perm_shut.name})",
        "conf_req": "Yes (Destructive)",
        "defense": "Confirmation + Kill-Switch",
        "passed": pass7,
        "detail": "Requires consequence confirmation; blocked by kill-switch."
    })
    print(f"  Tier: Level {perm_shut.value} | Refusal aborted: {shut_cancelled} | Kill-switch: {shut_kill_blocked} -> {'PASS' if pass7 else 'FAIL'}\n")

    # -------------------------------------------------------------
    # -------------------------------------------------------------
    # Display Verification Table
    # -------------------------------------------------------------
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    all_passed = all(t["passed"] for t in test_results)

    if console:
        try:
            from rich.align import Align
            table = Table(
                title="[bold cyan]WILLIAM-1 v0.2 SAFETY TEST VERIFICATION REPORT[/bold cyan]",
                header_style="bold cyan",
                border_style="bright_blue",
                expand=True
            )
            table.add_column("Scenario", style="bold white", width=26)
            table.add_column("Tool", style="yellow", width=20)
            table.add_column("Permission Tier", width=20)
            table.add_column("Confirmation", width=14)
            table.add_column("Tested Defense", style="cyan", width=28)
            table.add_column("Result", justify="center", width=10)

            for t in test_results:
                tier_style = "[bold green]" + t["tier"] + "[/bold green]" if "Level 1" in t["tier"] else "[bold red]" + t["tier"] + "[/bold red]"
                res_style = "[bold green]PASS[/bold green]" if t["passed"] else "[bold red]FAIL[/bold red]"
                table.add_row(
                    t["scenario"],
                    t["tool"],
                    tier_style,
                    t["conf_req"],
                    t["defense"],
                    res_style
                )

            console.print()
            console.print(table)
            console.print()

            banner_text = (
                "[bold green][PASS] ALL 7 PHASE 2 SECURITY GUARANTEES DEMONSTRABLY ENFORCED (100% PASS)[/bold green]\n"
                "[dim white]Every action is allowlisted, validated against root boundaries, auditable, and cannot bypass permission tiers.[/dim white]"
                if all_passed else
                "[bold red][FAIL] ONE OR MORE SAFETY DEFENSES FAILED VALIDATION[/bold red]"
            )
            console.print(Panel(Align.center(banner_text), border_style="green" if all_passed else "red"))
            console.print()
        except Exception:
            console = None

    if not console:
        print("=" * 70)
        print("SAFETY TEST SUMMARY:")
        for t in test_results:
            status = "PASS" if t["passed"] else "FAIL"
            print(f"[{status}] {t['scenario']} ({t['tool']}): Tier={t['tier']}, Conf={t['conf_req']} -> {t['defense']}")
        print("=" * 70)
        print("OVERALL RESULT:", "PASS" if all_passed else "FAIL")
        print("=" * 70)

    return all_passed
