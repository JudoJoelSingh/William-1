"""
Configuration module for William-1 Personal AI Voice Assistant (v0.2).
Centralizes all assistant settings, security parameters, tool allowlists,
fuzzy aliases, named shortcuts, and startup diagnostics.
"""

import os
import shutil
import platform
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any
from dotenv import load_dotenv

# Load variables from .env file if present
load_dotenv()


@dataclass
class Config:
    # --- Assistant Identity & Companion Persona ---
    ASSISTANT_NAME: str = os.getenv("ASSISTANT_NAME", "William")

    # Fixed system personality with crisp intent routing & tool calling rules
    SYSTEM_PROMPT: str = os.getenv(
        "SYSTEM_PROMPT",
        (
            "You are William, an intelligent, calm, concise, and helpful personal voice companion and desktop assistant. "
            "Your responses are converted directly to spoken audio in real time, so follow these core rules strictly:\n"
            "1. CONVERSATION VS ACTIONS: If the user asks a factual, conversational, or explanation question (e.g. 'What is a transistor?'), "
            "provide a direct, informative answer immediately without calling any tools. Never invoke a tool for pure knowledge questions.\n"
            "2. MULTI-TOOL COMPOSITION: When the user asks for multiple actions in a single request (e.g., 'Open VS Code and my William-1 project', "
            "'Mute the computer and open YouTube', or 'Check battery and memory'), emit ALL corresponding tool calls in an ordered sequence within the same response. "
            "Never drop secondary actions.\n"
            "3. SYSTEM HEALTH & TRANSPARENCY: When asked 'How is my computer doing?' or about computer performance, call 'get_system_health'. "
            "When asked 'What did you just do?' or to explain your last action, call 'explain_last_action'.\n"
            "4. AMBIGUITY: If a request is genuinely ambiguous or lacks a required target, ask a single brief clarifying question.\n"
            "5. SPOKEN PROSE: Speak in natural, human prose with short, clean sentences (usually 1 to 2 sentences). "
            "Do NOT use markdown symbols, asterisks, bullet points, numbered lists, hashtags, emojis, or code fences.\n"
            "6. GRACEFUL DEGRADATION: If an action fails, state clearly what failed and why, and proactively offer the nearest safe alternative.\n"
            "7. HONESTY: Clearly distinguish what you announced from what actions were actually executed on the system.\n"
            "8. USER MEMORY & PROJECT CONTINUITY: You have access to persistent memory tools. When asked to remember something, call 'save_memory'. "
            "When asked what you remember or for saved preferences, call 'query_memory' or 'list_memories'. "
            "Call 'show_all_memories' to list everything grouped by category. "
            "Call 'show_project' to show a project's full record and event timeline. "
            "Call 'configure_memory' to change memory settings like top_k, local_only, confirm_before_save. "
            "Call 'get_memory_settings' to show current memory configuration. "
            "Call 'export_memories' to back up memories to a file, 'import_memories' to restore. "
            "When asked to update project status, call 'update_project_status'. "
            "When asked to forget or delete memory, call 'forget_memory' (by keyword) or 'forget_memory_by_id' (by ID) or 'delete_project_memories'. "
            "If a forget/update command is ambiguous, present the candidates and ask one clarifying question — never guess on destructive operations. "
            "If relevant memories or project records are injected into your context, use them faithfully. "
            "CRITICAL: Never invent or hallucinate memories, decisions, or project status. If no records exist, say so honestly. "
            "CRITICAL: Never store passwords, API keys, tokens, private keys, or credentials — refuse politely and explain why."
        ),
    )

    # Trigger phrases that command William to stop listening and gracefully shut down
    STOP_PHRASES: List[str] = field(
        default_factory=lambda: [
            "stop listening",
            "goodbye william",
            "shut down",
            "turn off",
            "stop assistant",
            "exit",
            "quit",
            "bye william",
            "sleep now",
        ]
    )

    # --- Activation Modes ---
    # Options: "always_on" (continuous), "wake_word" (listens for wake word), "push_to_talk" (press Enter)
    ACTIVATION_MODE: str = os.getenv("ACTIVATION_MODE", "always_on").lower()
    WAKE_WORD: str = os.getenv("WAKE_WORD", "william").lower()

    # Audio & Visual Cues
    AUDIO_CUES_ENABLED: bool = os.getenv("AUDIO_CUES_ENABLED", "True").lower() == "true"
    BARGE_IN_ENABLED: bool = os.getenv("BARGE_IN_ENABLED", "True").lower() == "true"
    LATENCY_TRACKING: bool = os.getenv("LATENCY_TRACKING", "True").lower() == "true"
    STREAM_RESPONSES: bool = os.getenv("STREAM_RESPONSES", "True").lower() == "true"

    # --- LLM / Brain Settings ---
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai").lower()  # openai, groq, openrouter, generic
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "") or os.getenv("OPENAI_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.6"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "250"))
    MAX_HISTORY_TURNS: int = int(os.getenv("MAX_HISTORY_TURNS", "10"))  # Context history window

    # --- Speech-to-Text (STT) Settings ---
    # Options: "faster-whisper" (local), "openai-whisper" (local), "openai-api" (cloud), "groq-api" (cloud)
    STT_ENGINE: str = os.getenv("STT_ENGINE", "faster-whisper").lower()
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")  # tiny, base, small, medium, large-v3
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")  # cpu or cuda
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")  # int8, float16, float32

    # Microphone capture parameters & smart VAD
    MIC_ENERGY_THRESHOLD: int = int(os.getenv("MIC_ENERGY_THRESHOLD", "300"))
    MIC_DYNAMIC_ENERGY_THRESHOLD: bool = os.getenv("MIC_DYNAMIC_ENERGY_THRESHOLD", "True").lower() == "true"
    MIC_PAUSE_THRESHOLD: float = float(os.getenv("MIC_PAUSE_THRESHOLD", "0.7"))  # Dynamic turn-taking
    MIC_PHRASE_TIME_LIMIT: float = float(os.getenv("MIC_PHRASE_TIME_LIMIT", "15.0"))
    MIC_CALIBRATION_DURATION: float = float(os.getenv("MIC_CALIBRATION_DURATION", "0.8"))

    # --- Text-to-Speech (TTS) Settings ---
    # Options: "pyttsx3" (offline, default), "openai-api"
    TTS_ENGINE: str = os.getenv("TTS_ENGINE", "pyttsx3").lower()
    VOICE_RATE: int = int(os.getenv("VOICE_RATE", "168"))  # Tuned conversational rate
    VOICE_VOLUME: float = float(os.getenv("VOICE_VOLUME", "1.0"))  # 0.0 to 1.0
    VOICE_ID: str = os.getenv("VOICE_ID", "")  # System voice ID or index (optional)
    TTS_OPENAI_VOICE: str = os.getenv("TTS_OPENAI_VOICE", "alloy")  # alloy, echo, fable, onyx, nova, shimmer

    # --- Debugging & Audit Logging ---
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    AUDIT_LOG_ENABLED: bool = os.getenv("AUDIT_LOG_ENABLED", "True").lower() == "true"
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    AUDIT_LOG_FILE: str = os.getenv("AUDIT_LOG_FILE", "logs/william_audit.log")
    JSONL_LOG_FILE: str = os.getenv("JSONL_LOG_FILE", "logs/william_actions.jsonl")

    # --- Phase 2: Safe Tool Layer & Security Controls ---
    ENABLE_TOOLS: bool = os.getenv("ENABLE_TOOLS", "True").lower() == "true"
    DISABLE_L3_TOOLS: bool = os.getenv("DISABLE_L3_TOOLS", "False").lower() == "true"  # Kill-switch for destructive actions
    CONFIRMATION_TIMEOUT_SECONDS: float = float(os.getenv("CONFIRMATION_TIMEOUT_SECONDS", "10.0"))

    # --- Phase 3: Persistent User-Controlled Memory (v0.3+) ---
    ENABLE_MEMORY: bool = os.getenv("ENABLE_MEMORY", "True").lower() == "true"
    DATA_DIR: str = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
    MEMORY_DB_FILE: str = os.getenv("MEMORY_DB_FILE", "william_memory.db")
    MEMORY_RETRIEVAL_TOP_K: int = int(os.getenv("MEMORY_RETRIEVAL_TOP_K", "5"))  # default top-K cap
    MEMORY_MIN_CONFIDENCE: float = float(os.getenv("MEMORY_MIN_CONFIDENCE", "0.5"))
    MEMORY_EPISODIC_RETENTION_DAYS: int = int(os.getenv("MEMORY_EPISODIC_RETENTION_DAYS", "30"))
    # New v0.3+ toggles — also persisted in DB via MemorySettings
    MEMORY_AUTO_CAPTURE: bool = os.getenv("MEMORY_AUTO_CAPTURE", "True").lower() == "true"
    MEMORY_CONFIRM_BEFORE_SAVE: bool = os.getenv("MEMORY_CONFIRM_BEFORE_SAVE", "False").lower() == "true"
    MEMORY_LOCAL_ONLY: bool = os.getenv("MEMORY_LOCAL_ONLY", "False").lower() == "true"
    MEMORY_MAX_TOKEN_BUDGET: int = int(os.getenv("MEMORY_MAX_TOKEN_BUDGET", "500"))  # ~tokens for context

    @property
    def MEMORY_DB_PATH(self) -> str:
        return os.path.abspath(os.path.join(self.DATA_DIR, self.MEMORY_DB_FILE))


    # Application Allowlists (Friendly canonical name -> OS-specific executable paths/commands)
    APP_ALLOWLIST: dict = field(
        default_factory=lambda: {
            "vscode": {
                "windows": ["code", "code.cmd", r"C:\Program Files\Microsoft VS Code\Code.exe", r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"],
                "process_names": ["Code.exe", "code"],
                "display_name": "Visual Studio Code"
            },
            "chrome": {
                "windows": ["chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
                "process_names": ["chrome.exe", "chrome"],
                "display_name": "Google Chrome"
            },
            "explorer": {
                "windows": ["explorer.exe"],
                "process_names": ["explorer.exe"],
                "display_name": "File Explorer"
            },
            "notepad": {
                "windows": ["notepad.exe"],
                "process_names": ["notepad.exe", "Notepad.exe"],
                "display_name": "Notepad"
            },
            "calculator": {
                "windows": ["calc.exe"],
                "process_names": ["CalculatorApp.exe", "Calculator.exe", "calc.exe"],
                "display_name": "Calculator"
            },
            "terminal": {
                "windows": ["wt.exe", "powershell.exe", "cmd.exe"],
                "process_names": ["WindowsTerminal.exe", "powershell.exe", "cmd.exe"],
                "display_name": "Terminal"
            },
            "spotify": {
                "windows": ["spotify", r"%APPDATA%\Spotify\Spotify.exe"],
                "process_names": ["Spotify.exe", "spotify"],
                "display_name": "Spotify"
            },
            "discord": {
                "windows": ["discord", r"%LOCALAPPDATA%\Discord\Update.exe --processStart Discord.exe"],
                "process_names": ["Discord.exe", "discord"],
                "display_name": "Discord"
            },
            "brave": {
                "windows": [
                    "brave",
                    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
                    r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"
                ],
                "process_names": ["brave.exe", "brave"],
                "display_name": "Brave Browser"
            }
        }
    )

    # Configurable Fuzzy App Aliases (Natural phrasing -> Canonical allowlist key)
    APP_ALIASES: dict = field(
        default_factory=lambda: {
            "vscode": "vscode",
            "vs code": "vscode",
            "code": "vscode",
            "visual studio code": "vscode",
            "my coding environment": "vscode",
            "coding environment": "vscode",
            "code editor": "vscode",
            "my editor": "vscode",
            "dev environment": "vscode",
            "chrome": "chrome",
            "google chrome": "chrome",
            "the browser": "chrome",
            "my browser": "chrome",
            "web browser": "chrome",
            "internet": "chrome",
            "web": "chrome",
            "explorer": "explorer",
            "file explorer": "explorer",
            "my files": "explorer",
            "files": "explorer",
            "file manager": "explorer",
            "folder manager": "explorer",
            "notepad": "notepad",
            "text editor": "notepad",
            "notes": "notepad",
            "calculator": "calculator",
            "calc": "calculator",
            "the calculator": "calculator",
            "terminal": "terminal",
            "my terminal": "terminal",
            "command prompt": "terminal",
            "cmd": "terminal",
            "powershell": "terminal",
            "console": "terminal",
            "shell": "terminal",
            "spotify": "spotify",
            "my music": "spotify",
            "music": "spotify",
            "music player": "spotify",
            "songs": "spotify",
            "playlist": "spotify",
            "discord": "discord",
            "chat app": "discord",
            "brave": "brave",
            "brave browser": "brave",
            "the brave browser": "brave",
        }
    )

    # Known Websites Allowlist (Canonical name / alias -> Verified URL)
    KNOWN_WEBSITES: dict = field(
        default_factory=lambda: {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "github": "https://www.github.com",
            "reddit": "https://www.reddit.com",
            "wikipedia": "https://www.wikipedia.org",
            "spotify": "https://open.spotify.com",
            "netflix": "https://www.netflix.com",
            "twitter": "https://twitter.com",
            "x": "https://x.com",
            "gmail": "https://mail.google.com",
            "chatgpt": "https://chatgpt.com",
            "amazon": "https://www.amazon.com",
            "weather": "https://weather.com",
            "news": "https://news.google.com",
            "stackoverflow": "https://stackoverflow.com",
            "linkedin": "https://www.linkedin.com",
        }
    )

    # Fuzzy Website Aliases (Natural phrasing -> Canonical website key)
    SITE_ALIASES: dict = field(
        default_factory=lambda: {
            "google": "google",
            "search": "google",
            "youtube": "youtube",
            "videos": "youtube",
            "video": "youtube",
            "github": "github",
            "repo": "github",
            "git": "github",
            "reddit": "reddit",
            "wikipedia": "wikipedia",
            "wiki": "wikipedia",
            "spotify": "spotify",
            "music web": "spotify",
            "netflix": "netflix",
            "movies": "netflix",
            "twitter": "twitter",
            "x": "x",
            "gmail": "gmail",
            "email": "gmail",
            "my mail": "gmail",
            "chatgpt": "chatgpt",
            "openai": "chatgpt",
            "amazon": "amazon",
            "shopping": "amazon",
            "weather": "weather",
            "the weather": "weather",
            "news": "news",
            "the news": "news",
            "stackoverflow": "stackoverflow",
            "stack overflow": "stackoverflow",
            "linkedin": "linkedin",
        }
    )

    # Allowed File Root Directories (File operations are restricted strictly to these roots)
    ALLOWED_ROOT_NAMES: list = field(
        default_factory=lambda: [
            "documents",
            "downloads",
            "desktop",
            "pictures",
            "music",
            "videos",
            "workspace",
            "home",
        ]
    )

    # Configurable Named Shortcuts (Friendly shortcut phrase -> absolute filesystem path)
    def get_named_shortcuts(self) -> Dict[str, str]:
        """Returns user-defined named shortcuts mapping friendly names to absolute paths."""
        workspace_dir = os.path.abspath(os.path.dirname(__file__))
        home = os.path.expanduser("~")
        return {
            "william-1 project": workspace_dir,
            "william project": workspace_dir,
            "my project": workspace_dir,
            "current project": workspace_dir,
            "assistant project": workspace_dir,
            "workspace": workspace_dir,
            "my documents": os.path.abspath(os.path.join(home, "Documents")),
            "my downloads": os.path.abspath(os.path.join(home, "Downloads")),
            "my desktop": os.path.abspath(os.path.join(home, "Desktop")),
        }

    def get_allowed_root_paths(self) -> dict:
        """Resolves friendly folder root names to normalized absolute paths on the local system."""
        home = os.path.expanduser("~")
        current_dir = os.path.abspath(os.path.dirname(__file__))
        roots = {
            "home": os.path.abspath(home),
            "documents": os.path.abspath(os.path.join(home, "Documents")),
            "downloads": os.path.abspath(os.path.join(home, "Downloads")),
            "desktop": os.path.abspath(os.path.join(home, "Desktop")),
            "pictures": os.path.abspath(os.path.join(home, "Pictures")),
            "music": os.path.abspath(os.path.join(home, "Music")),
            "videos": os.path.abspath(os.path.join(home, "Videos")),
            "workspace": current_dir,
        }
        return roots

    def get_daily_greeting(self) -> str:
        """Returns a natural, time-of-day aware companion opener."""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            time_greeting = "Good morning"
        elif 12 <= hour < 17:
            time_greeting = "Good afternoon"
        elif 17 <= hour < 22:
            time_greeting = "Good evening"
        else:
            time_greeting = "Hello"

        return f"{time_greeting}! I am {self.ASSISTANT_NAME}. How may I help you?"

    def run_startup_self_check(self) -> Dict[str, Any]:
        """
        Performs a comprehensive diagnostic self-check of applications, folders, and libraries.
        Returns detailed status dictionary.
        """
        current_os = platform.system()
        report = {
            "os": current_os,
            "apps_detected": [],
            "apps_missing": [],
            "roots_valid": [],
            "roots_missing": [],
            "libraries_ok": [],
            "libraries_missing": [],
            "is_healthy": True,
        }

        # 1. Check Allowlisted Applications
        for app_key, app_info in self.APP_ALLOWLIST.items():
            candidates = app_info.get("windows" if current_os == "Windows" else "linux", [])
            found = False
            for cand in candidates:
                expanded = os.path.expandvars(cand)
                if os.path.isfile(expanded) or shutil.which(cand):
                    found = True
                    break
            if app_key in ("calculator", "explorer", "terminal") and current_os == "Windows":
                found = True

            disp = app_info.get("display_name", app_key)
            if found:
                report["apps_detected"].append(disp)
            else:
                report["apps_missing"].append(disp)

        # 2. Check Allowed Root Folders
        roots = self.get_allowed_root_paths()
        for root_name, root_path in roots.items():
            if os.path.exists(root_path):
                report["roots_valid"].append(f"{root_name} ({root_path})")
            else:
                report["roots_missing"].append(f"{root_name} ({root_path})")

        # 3. Check Required Python Libraries
        libs = ["psutil", "pyttsx3", "speech_recognition", "openai", "dotenv"]
        for lib in libs:
            try:
                __import__(lib)
                report["libraries_ok"].append(lib)
            except ImportError:
                report["libraries_missing"].append(lib)
                report["is_healthy"] = False

        return report

    def validate(self) -> Tuple[bool, List[str], List[str]]:
        """
        Validates startup configuration.
        Returns: (is_valid, list_of_errors, list_of_warnings)
        """
        errors = []
        warnings = []

        if not self.LLM_API_KEY:
            warnings.append(
                "LLM_API_KEY is not set in .env. Live LLM reasoning will fall back to diagnostic responses until set."
            )

        valid_modes = ["always_on", "wake_word", "push_to_talk"]
        if self.ACTIVATION_MODE not in valid_modes:
            warnings.append(
                f"Invalid ACTIVATION_MODE '{self.ACTIVATION_MODE}'. Falling back to 'always_on'. Valid: {valid_modes}"
            )
            self.ACTIVATION_MODE = "always_on"

        valid_stt = ["faster-whisper", "openai-whisper", "openai-api", "groq-api"]
        if self.STT_ENGINE not in valid_stt:
            warnings.append(f"Unknown STT_ENGINE '{self.STT_ENGINE}'. Defaulting to 'faster-whisper'.")
            self.STT_ENGINE = "faster-whisper"

        if self.LLM_TEMPERATURE < 0.0 or self.LLM_TEMPERATURE > 2.0:
            self.LLM_TEMPERATURE = 0.6

        if self.MAX_HISTORY_TURNS <= 0:
            self.MAX_HISTORY_TURNS = 10

        # Ensure logs directory exists
        try:
            os.makedirs(self.LOG_DIR, exist_ok=True)
        except Exception as e:
            warnings.append(f"Could not create log directory '{self.LOG_DIR}': {e}")

        is_valid = len(errors) == 0
        return is_valid, errors, warnings


# Global configuration instance
config = Config()
