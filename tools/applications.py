"""
Applications Tool Module for William-1 (v0.2).
Provides fuzzy alias resolution, named shortcuts, and safe process management.
The AI supplies only friendly application names — never arbitrary executable paths.
"""

import os
import shutil
import subprocess
from typing import Dict, Any, Optional
from config import config

try:
    import psutil
except ImportError:
    psutil = None


def resolve_application_alias(app_query: str) -> str:
    """
    Resolves natural, fuzzy application phrasings to canonical allowlist keys using config.APP_ALIASES.
    Example: 'my coding environment' -> 'vscode', 'the browser' -> 'chrome', 'my music' -> 'spotify'.
    """
    if not app_query:
        return ""

    cleaned = app_query.lower().strip()
    aliases = config.APP_ALIASES

    # 1. Exact alias match
    if cleaned in aliases:
        return aliases[cleaned]

    # 2. Check substring in alias keys
    for alias_key, target in aliases.items():
        if alias_key in cleaned or cleaned in alias_key:
            return target

    # 3. Direct allowlist key check
    if cleaned in config.APP_ALLOWLIST:
        return cleaned

    return cleaned


def open_application(application: str) -> Dict[str, Any]:
    """
    Opens an allowlisted application by friendly name or fuzzy alias.
    Falls back gracefully with helpful phrasing if the app is unapproved.
    """
    canonical_key = resolve_application_alias(application)
    allowlist = config.APP_ALLOWLIST

    # Handle unapproved application request
    if canonical_key not in allowlist:
        return {
            "success": False,
            "message": f"I don't have '{application}' in my approved applications -- want me to search for it on the web instead?",
            "error": f"Application '{application}' (resolved: '{canonical_key}') not in allowlist.",
            "alternative": {
                "tool": "search_web",
                "arguments": {"query": application},
                "suggestion": f"Search for {application} on the web"
            }
        }


    app_info = allowlist[canonical_key]
    display_name = app_info.get("display_name", canonical_key)
    candidates = app_info.get("windows", [])

    # Built-in Windows executables / special verbs
    if canonical_key == "calculator":
        try:
            subprocess.Popen(["calc.exe"], shell=False)
            return {
                "success": True,
                "message": f"I've opened {display_name} for you.",
                "data": {"app": canonical_key, "display_name": display_name}
            }
        except Exception:
            pass

    if canonical_key == "explorer":
        try:
            subprocess.Popen(["explorer.exe"], shell=False)
            return {
                "success": True,
                "message": f"I've opened {display_name} for you.",
                "data": {"app": canonical_key, "display_name": display_name}
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"I encountered a problem launching {display_name}.",
                "error": str(e)
            }

    # Locate and launch executable candidates
    for candidate in candidates:
        expanded = os.path.expandvars(candidate)

        target_path = None
        if os.path.isfile(expanded):
            target_path = expanded
        else:
            which_res = shutil.which(candidate)
            if which_res:
                target_path = which_res

        if target_path:
            try:
                subprocess.Popen([target_path], shell=False)
                return {
                    "success": True,
                    "message": f"I've opened {display_name} for you.",
                    "data": {"app": canonical_key, "path": target_path}
                }
            except Exception:
                continue

    # Attempt os.startfile fallback for registered Windows apps
    for candidate in candidates:
        cmd_only = candidate.split()[0]
        try:
            os.startfile(cmd_only)
            return {
                "success": True,
                "message": f"I've opened {display_name} for you.",
                "data": {"app": canonical_key}
            }
        except Exception:
            pass

    # Specific nearest safe alternatives for known desktop apps
    if canonical_key == "spotify":
        return {
            "success": False,
            "message": "I couldn't launch Spotify -- want me to open it in the browser instead?",
            "error": "Spotify desktop executable not found.",
            "alternative": {
                "tool": "open_url",
                "arguments": {"url": "spotify"},
                "suggestion": "Open Spotify in web browser"
            }
        }
    elif canonical_key == "discord":
        return {
            "success": False,
            "message": "I couldn't launch Discord -- want me to open Discord on the web instead?",
            "error": "Discord desktop executable not found.",
            "alternative": {
                "tool": "open_url",
                "arguments": {"url": "discord"},
                "suggestion": "Open Discord in web browser"
            }
        }
    elif canonical_key == "vscode":
        return {
            "success": False,
            "message": "I couldn't launch Visual Studio Code -- want me to open your project folder in File Explorer instead?",
            "error": "Visual Studio Code executable not found.",
            "alternative": {
                "tool": "open_folder",
                "arguments": {"folder": "william-1 project"},
                "suggestion": "Open project folder in File Explorer"
            }
        }

    return {
        "success": False,
        "message": f"I couldn't find {display_name} installed on this computer.",
        "error": f"Executable paths for '{canonical_key}' were not found.",
        "alternative": {
            "tool": "search_web",
            "arguments": {"query": display_name},
            "suggestion": f"Search for {display_name} on the web"
        }
    }


def close_application(application: str) -> Dict[str, Any]:
    """
    Closes running instances of an allowlisted application.
    """
    canonical_key = resolve_application_alias(application)
    allowlist = config.APP_ALLOWLIST

    if canonical_key not in allowlist:
        return {
            "success": False,
            "message": f"I don't have '{application}' in my approved applications list.",
            "error": f"Application '{application}' not in allowlist."
        }

    app_info = allowlist[canonical_key]
    display_name = app_info.get("display_name", canonical_key)
    process_names = [p.lower() for p in app_info.get("process_names", [])]

    if not process_names:
        return {
            "success": False,
            "message": f"I don't have process details configured for {display_name}.",
            "error": "No process names mapped."
        }

    if psutil is None:
        return {
            "success": False,
            "message": "The process management utility is unavailable.",
            "error": "psutil not installed."
        }

    closed_count = 0
    errors = []

    try:
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                p_name = proc.info.get("name")
                if p_name and p_name.lower() in process_names:
                    proc.terminate()
                    closed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as ex:
                errors.append(str(ex))
    except Exception as e:
        return {
            "success": False,
            "message": f"I encountered an error while attempting to close {display_name}.",
            "error": str(e)
        }

    if closed_count > 0:
        return {
            "success": True,
            "message": f"I've closed {display_name} for you.",
            "data": {"app": canonical_key, "instances_closed": closed_count}
        }
    else:
        return {
            "success": True,
            "message": f"{display_name} is not currently running.",
            "data": {"app": canonical_key, "instances_closed": 0}
        }
