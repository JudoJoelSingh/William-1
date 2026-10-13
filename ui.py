"""
UI and Terminal UX Module for William-1 (v0.2).
Provides rich terminal styling, animated presence indicators,
color-coded tool calls, results, security confirmation cards,
and startup diagnostic reports.
"""

import sys
import time
import json
import threading
from typing import Optional, Dict, List, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.table import Table
    from rich.theme import Theme
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.layout import Layout
    from rich.align import Align

    custom_theme = Theme({
        "info": "cyan",
        "warning": "yellow",
        "danger": "bold red",
        "success": "bold green",
        "user": "bold cyan",
        "assistant": "bold bright_blue",
        "status": "bold magenta",
        "telemetry": "dim yellow",
        "presence": "bold white on dark_blue",
        "tool_name": "bold yellow",
        "tool_arg": "bright_cyan",
        "tool_result": "bright_green",
        "tool_error": "bold red",
        "confirm_box": "bold magenta",
    })
    console = Console(theme=custom_theme)
except ImportError:
    console = None
    Live = None

# Audio cue support
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False



class DashboardLive:
    """
    Manages a live terminal dashboard for observability.
    Displays real-time battery, CPU, RAM, disk telemetry and a live feed
    of recent actions with their permission tier and status.
    """

    def __init__(self):
        self.live = None
        self.layout = None
        self.action_logs: List[Tuple[str, str, str, str, str]] = []
        self._lock = threading.Lock()
        self._preload_recent_logs()

    def _preload_recent_logs(self):
        """Loads existing actions from the JSONL log file upon initialization."""
        import os
        from config import config
        log_file = config.JSONL_LOG_FILE
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = [ln.strip() for ln in f if ln.strip()]
                    for ln in lines[-12:]:
                        try:
                            d = json.loads(ln)
                            t_str = d.get("timestamp", "")
                            time_part = t_str.split("T")[1][:8] if "T" in t_str else time.strftime("%H:%M:%S")
                            tool = d.get("tool", d.get("tool_name", "unknown"))
                            perm = d.get("permission_level", "L1 Safe")
                            clean_perm = "L1 (Safe)" if "Level 1" in perm or "L1" in perm else "L2 (Sensitive)" if "Level 2" in perm or "L2" in perm else "L3 (Destructive)"
                            stat = d.get("status", "EXECUTED")
                            res = d.get("result", "") or d.get("error", "") or "Done"
                            self.action_logs.append((time_part, tool, clean_perm, stat, str(res)))
                        except Exception:
                            pass
            except Exception:
                pass

    def add_log(self, tool_name: str, perm_level: str, status: str, message: str):
        with self._lock:
            clean_perm = "L1 (Safe)" if "Level 1" in perm_level or "L1" in perm_level else "L2 (Sensitive)" if "Level 2" in perm_level or "L2" in perm_level else "L3 (Destructive)"
            self.action_logs.append((time.strftime("%H:%M:%S"), tool_name, clean_perm, status, message))
            if len(self.action_logs) > 15:
                self.action_logs.pop(0)

    def generate_layout(self):
        if not console:
            return None

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="telemetry", ratio=2),
            Layout(name="actions", ratio=5)
        )

        # Header
        icon, label, style = presence.STATES.get(presence.current_state, ("[*]", presence.current_state.capitalize(), "white"))
        header_text = Text.assemble(
            ("William-1 System Observability Dashboard  |  State: ", "bold cyan"),
            (f"{icon} {label.upper()}", style),
            ("  |  Every Action Is Observable", "dim white")
        )
        layout["header"].update(Panel(Align.center(header_text, vertical="middle"), style="bright_blue"))

        # Telemetry panel
        cpu_text = "N/A"
        ram_text = "N/A"
        bat_text = "AC Power"
        disk_text = "N/A"

        try:
            import psutil
            cpu_val = psutil.cpu_percent()
            cores = psutil.cpu_count(logical=True)
            cpu_text = f"{cpu_val}% ({cores} cores)"

            vm = psutil.virtual_memory()
            ram_used_gb = vm.used / (1024 ** 3)
            ram_total_gb = vm.total / (1024 ** 3)
            ram_text = f"{vm.percent}% ({ram_used_gb:.1f} / {ram_total_gb:.1f} GB)"

            try:
                bat = psutil.sensors_battery()
                if bat:
                    status_sub = "Charging" if bat.power_plugged else "Discharging"
                    bat_text = f"{bat.percent}% ({status_sub})"
                else:
                    bat_text = "AC Line Power"
            except Exception:
                bat_text = "AC Power"

            try:
                du = psutil.disk_usage("C:\\" if sys.platform == "win32" else "/")
                free_gb = du.free / (1024 ** 3)
                total_gb = du.total / (1024 ** 3)
                disk_text = f"{du.percent}% ({free_gb:.1f} GB free of {total_gb:.1f} GB)"
            except Exception:
                disk_text = "N/A"
        except Exception:
            pass

        tel_table = Table.grid(padding=(1, 2))
        tel_table.add_column(style="bold white", width=14)
        tel_table.add_column(style="yellow")
        tel_table.add_row("⚡ Battery:", bat_text)
        tel_table.add_row("🧠 Memory:", ram_text)
        tel_table.add_row("⚙️ CPU Load:", cpu_text)
        tel_table.add_row("💾 Primary Disk:", disk_text)
        layout["telemetry"].update(Panel(tel_table, title="[bold cyan]📊 Real-Time Telemetry[/bold cyan]", border_style="cyan"))

        # Live Actions Feed table
        act_table = Table(show_header=True, header_style="bold magenta", expand=True)
        act_table.add_column("Time", width=9, style="dim white")
        act_table.add_column("Tool", width=18, style="bold yellow")
        act_table.add_column("Tier", width=16)
        act_table.add_column("Status", width=12)
        act_table.add_column("Result / Message", style="green")

        with self._lock:
            for t, tool, perm, stat, msg in self.action_logs[-10:]:
                # Color-code permission tier
                if "L1" in perm:
                    perm_style = "[bold green]L1 (Safe)[/bold green]"
                elif "L2" in perm:
                    perm_style = "[bold yellow]L2 (Sensitive)[/bold yellow]"
                else:
                    perm_style = "[bold red]L3 (Destructive)[/bold red]"

                # Color-code status
                if stat in ("SUCCESS", "EXECUTED", "CONFIRMED"):
                    stat_style = "[bold green]PASS[/bold green]"
                elif stat in ("FAILED", "DENIED"):
                    stat_style = "[bold red]FAIL[/bold red]"
                elif stat == "CANCELLED":
                    stat_style = "[bold yellow]CANCELLED[/bold yellow]"
                elif stat == "BLOCKED":
                    stat_style = "[bold magenta]BLOCKED[/bold magenta]"
                else:
                    stat_style = f"[white]{stat}[/white]"

                act_table.add_row(t, tool, perm_style, stat_style, msg[:60] + ("..." if len(msg) > 60 else ""))

        layout["actions"].update(Panel(act_table, title="[bold magenta]🛡️ Live Action Feed (Observable Security Layer)[/bold magenta]", border_style="magenta"))

        # Footer
        footer_text = Text("William-1 v0.2 Safe Tool Execution Layer  |  Press Ctrl+C or say 'Stop listening' to exit", style="dim")
        layout["footer"].update(Panel(Align.center(footer_text), style="dim"))

        return layout

    def start(self):
        if console and Live:
            self.live = Live(self.generate_layout(), console=console, refresh_per_second=2, screen=True)
            self.live.start()

    def update(self):
        if self.live:
            self.live.update(self.generate_layout())

    def stop(self):
        if self.live:
            self.live.stop()
            self.live = None

    def run_standalone(self, assistant=None):
        """
        Runs the dashboard in a dedicated live observation loop.
        If an assistant is provided and mic is active, runs the voice loop in a background thread.
        """
        if not console or not Live:
            print("[Dashboard Notice] Rich library is required for live terminal dashboard mode.")
            return

        stop_event = threading.Event()

        # If assistant provided and mic active, run voice listener concurrently!
        voice_thread = None
        if assistant and getattr(assistant, "stt", None) and assistant.stt.microphone is not None:
            def bg_voice():
                try:
                    assistant.run_voice_loop()
                except Exception:
                    pass
                finally:
                    stop_event.set()
            voice_thread = threading.Thread(target=bg_voice, daemon=True)
            voice_thread.start()

        with Live(self.generate_layout(), console=console, refresh_per_second=3, screen=True) as live:
            try:
                while not stop_event.is_set():
                    time.sleep(0.33)
                    live.update(self.generate_layout())
            except KeyboardInterrupt:
                pass
            finally:
                if assistant:
                    assistant.is_running = False

dashboard = DashboardLive()

class LivePresence:

    """Manages an animated live status presence in the terminal."""

    STATES = {
        "idle": ("[-]", "William is Idle", "dim white"),
        "listening": ("[o]", "Listening... (speak now)", "bold green"),
        "transcribing": ("(~)", "Transcribing speech...", "bold yellow"),
        "thinking": ("[*]", "Reasoning & executing tools...", "bold magenta"),
        "speaking": ("[>]", "Speaking response...", "bold bright_blue"),
        "interrupted": ("[x]", "Interrupted by user", "bold red"),
    }

    def __init__(self):
        self.current_state = "idle"

    def set_state(self, state: str):
        self.current_state = state
        icon, label, style = self.STATES.get(state, ("[*]", state.capitalize(), "white"))
        try:
            if console:
                console.print(f"  [{style}]{icon} [{state.upper()}] {label}[/{style}]", end="\r")
            else:
                print(f"{icon} [{state.upper()}]: {label}")
        except Exception:
            pass


presence = LivePresence()


class UI:
    """Static helper for all terminal displays, banners, and audio cues."""

    @staticmethod
    def print_banner(name: str, mode: str, model: str, stt: str, tts: str, barge_in: bool, greeting: str, tools_enabled: bool = True, tool_count: int = 27):
        """Displays a clean, styled startup companion card."""
        if console:
            info_table = Table.grid(padding=(0, 2))
            info_table.add_column(style="bold white")
            info_table.add_column(style="green")
            info_table.add_row("Assistant:", f"[bold cyan]{name} v0.2 (Safe Tool Layer Edition)[/bold cyan]")
            info_table.add_row("Status:", f"[bold green]● Online[/bold green] — [italic]\"{greeting}\"[/italic]")
            info_table.add_row("Activation Mode:", f"[bold yellow]{mode.upper()}[/bold yellow]")
            info_table.add_row("LLM Reasoning:", f"[bold blue]{model}[/bold blue] (Tool Calling active)")
            info_table.add_row("Safe Tool Layer:", f"[bold green]Active[/bold green] ({tool_count} sandboxed tools, Level 1-3 permissions)" if tools_enabled else "[dim]Disabled[/dim]")
            info_table.add_row("Speech Stack:", f"STT: [cyan]{stt}[/cyan] | TTS: [cyan]{tts}[/cyan]")
            info_table.add_row("Barge-In Interruption:", "[green]Active[/green]" if barge_in else "[dim]Disabled[/dim]")

            panel = Panel(
                info_table,
                title=f"[bold cyan]🤖 {name.upper()}-1 AI VOICE ASSISTANT (v0.2)[/bold cyan]",
                subtitle="[dim]Say 'stop listening' or press Ctrl+C anytime to exit[/dim]",
                border_style="bright_blue",
                padding=(1, 2)
            )
            console.print()
            console.print(panel)
            console.print()
        else:
            print("=" * 60)
            print(f"       {name.upper()}-1 VOICE ASSISTANT v0.2")
            print(f" Status: Online | {greeting}")
            print(f" Mode: {mode} | Model: {model} | Tools: {'Active' if tools_enabled else 'Off'} | STT: {stt} | TTS: {tts}")
            print("=" * 60)

    @staticmethod
    def print_startup_diagnostics(report: Dict[str, Any]):
        """Renders startup diagnostic self-check summary table."""
        if console:
            diag_table = Table(title="🔍 Startup Self-Check & Environment Diagnostics", border_style="cyan")
            diag_table.add_column("Diagnostic Category", style="bold white", width=26)
            diag_table.add_column("Status / Detected Assets", style="cyan", width=46)
            diag_table.add_column("Health", justify="center", width=10)

            # OS
            diag_table.add_row("Operating System", report.get("os", "Unknown"), "[bold green]OK[/bold green]")

            # Apps
            apps_det = ", ".join(report.get("apps_detected", []))
            diag_table.add_row("Allowlisted Apps", f"Detected: {apps_det}", "[bold green]OK[/bold green]")

            # Roots
            valid_roots = len(report.get("roots_valid", []))
            diag_table.add_row("Permitted Roots", f"{valid_roots} allowed folders verified", "[bold green]OK[/bold green]")

            # Libraries
            libs_ok = ", ".join(report.get("libraries_ok", []))
            diag_table.add_row("Core Libraries", libs_ok, "[bold green]OK[/bold green]")

            console.print(diag_table)
            console.print()
        else:
            print(f"[Diagnostics] OS: {report.get('os')} | Apps: {len(report.get('apps_detected', []))} detected | Roots: {len(report.get('roots_valid', []))} verified")

    @staticmethod
    def print_tool_call(tool_name: str, arguments: Dict[str, Any]):
        """Displays color-coded tool call dispatched by the brain."""
        args_json = json.dumps(arguments, ensure_ascii=False)
        if console:
            console.print(f"  [bold cyan]🔧 TOOL CALL:[/bold cyan] [tool_name]{tool_name}[/tool_name] [dim]arguments:[/dim] [tool_arg]{args_json}[/tool_arg]")
        else:
            print(f"  [TOOL CALL] {tool_name} {args_json}")

    @staticmethod
    def print_tool_result(tool_name: str, message: str, success: bool = True):
        """Displays color-coded result returned by tool execution."""
        status_tag = "[bold green]✓ RESULT[/bold green]" if success else "[bold red]✗ RESULT[/bold red]"
        style = "tool_result" if success else "tool_error"
        if console:
            console.print(f"  {status_tag} [[bold white]{tool_name}[/bold white]]: [{style}]{message}[/{style}]")
        else:
            status_txt = "[SUCCESS]" if success else "[FAILED]"
            print(f"  {status_txt} {tool_name}: {message}")

    @staticmethod
    def print_confirmation_prompt(consequence_question: str):
        """Displays highlighted security confirmation prompt."""
        if console:
            panel = Panel(
                f"[bold yellow]⚠️ Permission Required:[/bold yellow] [white]{consequence_question}[/white]",
                border_style="magenta",
                title="[bold magenta]SECURITY CONFIRMATION[/bold magenta]",
                padding=(0, 1)
            )
            console.print()
            console.print(panel)
        else:
            print(f"\n[SECURITY CONFIRMATION] {consequence_question}")

    @staticmethod
    def play_audio_cue(cue_type: str):
        """Plays frequency audio feedback tones."""
        if not HAS_WINSOUND:
            return

        try:
            if cue_type == "listen_start":
                winsound.Beep(900, 80)
            elif cue_type == "listen_stop":
                winsound.Beep(600, 80)
            elif cue_type == "interrupted":
                winsound.Beep(750, 50)
                winsound.Beep(500, 50)
            elif cue_type == "error":
                winsound.Beep(400, 150)
        except Exception:
            pass

    @staticmethod
    def print_user_speech(text: str):
        """Prints transcribed user utterance."""
        if console:
            console.print(f"\n[user]You:[/user] [white]{text}[/white]")
        else:
            print(f"\nYou said: {text}")

    @staticmethod
    def print_assistant_start(name: str):
        """Prepares the assistant's speech dialogue line."""
        if console:
            console.print(f"[assistant]{name}:[/assistant] ", end="")
        else:
            print(f"{name}: ", end="", flush=True)

    @staticmethod
    def print_assistant_chunk(chunk: str):
        """Appends spoken streamed text to the screen."""
        if console:
            console.print(f"[bright_white]{chunk}[/bright_white] ", end="")
        else:
            print(f"{chunk} ", end="", flush=True)

    @staticmethod
    def print_assistant_end():
        """Concludes the assistant dialogue line."""
        if console:
            console.print()
        else:
            print()

    @staticmethod
    def print_assistant_speech(name: str, text: str):
        """Prints full assistant speech line."""
        if console:
            console.print(f"[assistant]{name}:[/assistant] [bright_white]{text}[/bright_white]")
        else:
            print(f"{name}: {text}")

    @staticmethod
    def print_interrupted():
        if console:
            console.print("  [bold red]■ Interrupted[/bold red] [dim](listening...)[/dim]")
        else:
            print("[William interrupted by user]")

    @staticmethod
    def print_telemetry(metrics: Dict[str, float]):
        """Prints latency metrics."""
        if not metrics:
            return

        stt_t = metrics.get("stt_sec", 0.0)
        llm_t = metrics.get("first_token_sec", metrics.get("llm_sec", 0.0))
        tts_t = metrics.get("tts_sec", 0.0)
        total_t = metrics.get("total_sec", 0.0)

        badge_text = f"⏱ Turnaround: STT: {stt_t:.2f}s | TTFT: {llm_t:.2f}s | TTS: {tts_t:.2f}s | Total: {total_t:.2f}s"
        if console:
            console.print(f"  [telemetry]{badge_text}[/telemetry]\n")
        else:
            print(f"  [{badge_text}]\n")

    # --- Error Handlers ---

    @staticmethod
    def error_no_microphone(detail: str = ""):
        msg = "No working microphone detected. Please check Windows privacy permissions or connect a mic."
        if detail:
            msg += f"\nDetails: {detail}"
        if console:
            console.print(Panel(f"[bold yellow]⚠️ Microphone Notice[/bold yellow]\n{msg}", border_style="yellow"))
        else:
            print(f"[Microphone Error] {msg}")

    @staticmethod
    def error_unintelligible():
        if console:
            console.print("  [dim yellow]○ (Silence / unintelligible audio)[/dim yellow]")
        else:
            print("[Silence or unintelligible noise]")

    @staticmethod
    def error_network(detail: str = ""):
        msg = "Network connection failed. Please verify your internet connection."
        if detail:
            msg += f"\nDetails: {detail}"
        if console:
            console.print(Panel(f"[bold red]🌐 Network Notice[/bold red]\n{msg}", border_style="red"))
        else:
            print(f"[Network Error] {msg}")

    @staticmethod
    def error_api(provider: str, detail: str = ""):
        msg = f"API communication issue with {provider}. Verify API key and account status in .env."
        if detail:
            msg += f"\nDetails: {detail}"
        if console:
            console.print(Panel(f"[bold red]🔑 API Notice[/bold red]\n{msg}", border_style="red"))
        else:
            print(f"[API Error] {msg}")

    @staticmethod
    def error_tts(detail: str = ""):
        msg = "TTS playback error. Falling back to console display."
        if detail:
            msg += f"\nDetails: {detail}"
        if console:
            console.print(Panel(f"[bold magenta]🔊 Audio Driver Notice[/bold magenta]\n{msg}", border_style="magenta"))
        else:
            print(f"[TTS Error] {msg}")

    @staticmethod
    def print_setup_error(missing_items: list):
        items_str = "\n".join([f" • {item}" for item in missing_items])
        msg = f"[bold red]Configuration Validation Failed:[/bold red]\n{items_str}\n\nPlease update your [bold cyan].env[/bold cyan] file."
        if console:
            console.print(Panel(msg, title="[bold red]Setup Error[/bold red]", border_style="red"))
        else:
            print("=" * 60)
            print("SETUP CONFIGURATION ERROR:\n" + items_str)
            print("=" * 60)

    # --- Test Suite / Demo Reporting ---

    @staticmethod
    def print_demo_results(results: List[Dict[str, any]], overall_passed: bool):
        """Renders an evaluation table for --demo mode."""
        if console:
            try:
                table = Table(title="[bold cyan]William-1 Phase 2 Validation Suite (Safe Tool Layer)[/bold cyan]", border_style="bright_blue")
                table.add_column("Scenario / Test Case", style="bold white", width=34)
                table.add_column("Input Query / Event", style="cyan", width=30)
                table.add_column("Status", justify="center", width=12)
                table.add_column("Latency / Metric", style="yellow", width=16)

                for r in results:
                    status_str = "[bold green]PASS[/bold green]" if r["passed"] else "[bold red]FAIL[/bold red]"
                    table.add_row(r["name"], r.get("query", "-"), status_str, r.get("metric", "-"))

                console.print()
                console.print(table)
                console.print()

                summary_text = "[bold green][PASS] ALL PHASE 2 TEST SCENARIOS PASSED — Safe Tool Layer Verified![/bold green]" if overall_passed else "[bold red][FAIL] SOME TESTS FAILED[/bold red]"

                console.print(Panel(summary_text, border_style="green" if overall_passed else "red"))
                console.print()
                return
            except Exception:
                pass

        print("\n" + "=" * 60)
        print("WILLIAM-1 DEMO TEST RESULTS")
        print("=" * 60)
        for r in results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"[{status}] {r['name']}: {r.get('metric', '')}")
        print("=" * 60 + "\n")
