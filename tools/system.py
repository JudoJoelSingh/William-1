"""
System Tool Module for William-1 (v0.2).
Provides real-time system telemetry and controls with humanized units,
rounded numbers, and OS platform validation.
"""

import os
import sys
import platform
import subprocess
import ctypes
from datetime import datetime
from typing import Dict, Any, Optional
import json
from config import config

try:
    import psutil
except ImportError:
    psutil = None


def get_battery_status() -> Dict[str, Any]:
    """
    Retrieves current battery percentage, charging state, and estimated runtime.
    Humanizes phrasing: e.g. "You're at 68 percent and charging".
    """
    if psutil is None:
        return {
            "success": False,
            "message": "System monitoring utility is unavailable.",
            "error": "psutil not installed."
        }

    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return {
                "success": True,
                "message": "This computer is connected to desktop AC power without a battery.",
                "data": {"has_battery": False, "plugged_in": True}
            }

        percent = round(battery.percent)
        is_plugged = battery.power_plugged

        if is_plugged:
            msg = f"You're at {percent} percent and charging."
        else:
            time_left_str = ""
            if battery.secsleft > 0 and battery.secsleft != psutil.POWER_TIME_UNLIMITED:
                hrs = battery.secsleft // 3600
                mins = (battery.secsleft % 3600) // 60
                if hrs > 0:
                    time_left_str = f" with about {hrs} hour{'s' if hrs != 1 else ''} and {mins} minute{'s' if mins != 1 else ''} remaining"
                else:
                    time_left_str = f" with about {mins} minute{'s' if mins != 1 else ''} remaining"

            msg = f"Your battery is at {percent} percent, discharging on battery power{time_left_str}."

        return {
            "success": True,
            "message": msg,
            "data": {
                "percent": percent,
                "charging": is_plugged,
                "seconds_left": battery.secsleft if battery.secsleft > 0 else None,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Could not read battery status.",
            "error": str(e)
        }


def get_cpu_usage() -> Dict[str, Any]:
    """
    Retrieves the current CPU utilization percentage and core count.
    """
    if psutil is None:
        return {
            "success": False,
            "message": "System monitoring utility is unavailable.",
            "error": "psutil not installed."
        }

    try:
        cpu_pct = round(psutil.cpu_percent(interval=0.1))
        core_count = psutil.cpu_count(logical=True)
        msg = f"Current CPU utilization is at {cpu_pct} percent across {core_count} logical cores."

        return {
            "success": True,
            "message": msg,
            "data": {
                "cpu_percent": cpu_pct,
                "cores": core_count,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Could not retrieve CPU utilization.",
            "error": str(e)
        }


def get_ram_usage() -> Dict[str, Any]:
    """
    Retrieves current RAM memory utilization with humanized gigabytes.
    """
    if psutil is None:
        return {
            "success": False,
            "message": "System monitoring utility is unavailable.",
            "error": "psutil not installed."
        }

    try:
        mem = psutil.virtual_memory()
        total_gb = mem.total / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)
        avail_gb = mem.available / (1024 ** 3)
        percent = round(mem.percent)

        msg = f"Memory usage is at {percent} percent. Using {used_gb:.1f} GB of {total_gb:.1f} GB total RAM, with {avail_gb:.1f} GB available."

        return {
            "success": True,
            "message": msg,
            "data": {
                "total_gb": round(total_gb, 1),
                "used_gb": round(used_gb, 1),
                "available_gb": round(avail_gb, 1),
                "percent": percent,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Could not retrieve memory statistics.",
            "error": str(e)
        }


def get_disk_usage(path: str = "C:\\") -> Dict[str, Any]:
    """
    Retrieves primary storage disk usage with humanized gigabytes.
    """
    if psutil is None:
        return {
            "success": False,
            "message": "System monitoring utility is unavailable.",
            "error": "psutil not installed."
        }

    target_path = "C:\\" if platform.system() == "Windows" else "/"
    try:
        usage = psutil.disk_usage(target_path)
        total_gb = usage.total / (1024 ** 3)
        used_gb = usage.used / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        percent = round(usage.percent)

        drive_label = "C drive" if platform.system() == "Windows" else "main drive"
        msg = f"Your {drive_label} is {percent} percent full, with {free_gb:.1f} GB free of {total_gb:.1f} GB total."

        return {
            "success": True,
            "message": msg,
            "data": {
                "path": target_path,
                "total_gb": round(total_gb, 1),
                "used_gb": round(used_gb, 1),
                "free_gb": round(free_gb, 1),
                "percent": percent,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Could not read disk storage information.",
            "error": str(e)
        }


def get_os_info() -> Dict[str, Any]:
    """
    Retrieves operating system details and system platform.
    """
    try:
        os_name = platform.system()
        os_release = platform.release()
        os_version = platform.version()
        arch = platform.machine()
        node = platform.node()

        msg = f"Running {os_name} {os_release} on host {node} with {arch} architecture."

        return {
            "success": True,
            "message": msg,
            "data": {
                "system": os_name,
                "release": os_release,
                "version": os_version,
                "architecture": arch,
                "hostname": node,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Could not retrieve operating system details.",
            "error": str(e)
        }


def get_datetime() -> Dict[str, Any]:
    """
    Retrieves current time, date, and day of week in natural prose.
    """
    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M %p").lstrip("0")
    msg = f"It is currently {time_str} on {date_str}."

    return {
        "success": True,
        "message": msg,
        "data": {
            "time": time_str,
            "date": date_str,
            "iso": now.isoformat(),
        }
    }


# --- System Controls with Fast Platform Checks ---

def set_volume(level: int) -> Dict[str, Any]:
    """
    Sets master audio volume level (0 to 100).
    """
    if platform.system() != "Windows":
        return {
            "success": False,
            "message": f"Volume control is not supported on {platform.system()}.",
            "error": "Unsupported platform."
        }

    try:
        level = int(level)
    except (ValueError, TypeError):
        return {"success": False, "message": "Volume level must be an integer between 0 and 100.", "error": "Invalid level."}

    level = max(0, min(100, level))

    try:
        VK_VOLUME_DOWN = 0xAE
        VK_VOLUME_UP = 0xAF
        for _ in range(50):
            ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)

        steps_up = level // 2
        for _ in range(steps_up):
            ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)

        return {
            "success": True,
            "message": f"I have set the master volume to {level} percent.",
            "data": {"volume": level}
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Unable to adjust system volume.",
            "error": str(e)
        }


def mute() -> Dict[str, Any]:
    """
    Toggles or mutes master system audio.
    """
    if platform.system() != "Windows":
        return {"success": False, "message": f"Audio mute is not supported on {platform.system()}.", "error": "Unsupported platform."}

    try:
        VK_VOLUME_MUTE = 0xAD
        ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
        return {"success": True, "message": "Audio mute toggled.", "data": {"muted": True}}
    except Exception as e:
        return {"success": False, "message": "Failed to mute audio.", "error": str(e)}


def unmute() -> Dict[str, Any]:
    """
    Unmutes master system audio.
    """
    return mute()


def lock_computer() -> Dict[str, Any]:
    """
    Locks the user workstation.
    """
    if platform.system() != "Windows":
        return {"success": False, "message": f"Workstation lock is not supported on {platform.system()}.", "error": "Unsupported platform."}

    try:
        res = ctypes.windll.user32.LockWorkStation()
        if res:
            return {"success": True, "message": "I've locked your computer.", "data": {"locked": True}}
        return {"success": False, "message": "Could not lock the computer.", "error": "LockWorkStation returned 0"}
    except Exception as e:
        return {"success": False, "message": "Error while locking workstation.", "error": str(e)}


def sleep_system() -> Dict[str, Any]:
    """
    Puts the computer into sleep/suspend mode.
    """
    if platform.system() != "Windows":
        return {"success": False, "message": f"Sleep control is not supported on {platform.system()}.", "error": "Unsupported platform."}

    try:
        ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
        return {"success": True, "message": "Putting the computer to sleep.", "data": {"sleeping": True}}
    except Exception as e:
        return {"success": False, "message": "Unable to suspend computer.", "error": str(e)}


def restart_system(delay_seconds: int = 5) -> Dict[str, Any]:
    """
    Initiates a graceful system restart.
    """
    if platform.system() != "Windows":
        return {"success": False, "message": f"Restart control is not supported on {platform.system()}.", "error": "Unsupported platform."}

    try:
        subprocess.run(["shutdown", "/r", "/t", str(int(delay_seconds))], check=True, shell=False)
        return {
            "success": True,
            "message": f"System restart scheduled in {delay_seconds} seconds.",
            "data": {"restarting": True, "delay": delay_seconds}
        }
    except Exception as e:
        return {"success": False, "message": "Could not initiate system restart.", "error": str(e)}


def shutdown_system(delay_seconds: int = 5) -> Dict[str, Any]:
    """
    Initiates a graceful system shutdown.
    """
    if platform.system() != "Windows":
        return {"success": False, "message": f"Shutdown control is not supported on {platform.system()}.", "error": "Unsupported platform."}

    try:
        subprocess.run(["shutdown", "/s", "/t", str(int(delay_seconds))], check=True, shell=False)
        return {
            "success": True,
            "message": f"System shutdown scheduled in {delay_seconds} seconds.",
            "data": {"shutting_down": True, "delay": delay_seconds}
        }
    except Exception as e:
        return {"success": False, "message": "Could not initiate system shutdown.", "error": str(e)}

def get_system_health() -> Dict[str, Any]:
    """
    Synthesizes an intelligent system health briefing covering battery, memory pressure,
    disk space, and CPU load, paired with one useful actionable observation.
    """
    health_data = {}
    
    battery = get_battery_status()
    if battery.get("success"):
        health_data["battery"] = battery["data"]
        
    cpu = get_cpu_usage()
    if cpu.get("success"):
        health_data["cpu"] = cpu["data"]
        
    ram = get_ram_usage()
    if ram.get("success"):
        health_data["ram"] = ram["data"]
        
    disk = get_disk_usage()
    if disk.get("success"):
        health_data["disk"] = disk["data"]

    # 1. Synthesize core telemetry metrics
    bat_info = health_data.get("battery", {})
    cpu_info = health_data.get("cpu", {})
    ram_info = health_data.get("ram", {})
    disk_info = health_data.get("disk", {})

    bat_pct = bat_info.get("percent")
    is_charging = bat_info.get("is_charging", False)
    has_bat = bat_info.get("has_battery", True)

    cpu_pct = cpu_info.get("cpu_percent", 0)
    ram_pct = ram_info.get("percent", 0)
    ram_free_gb = ram_info.get("available_gb", 0)

    disk_pct = disk_info.get("percent", 0)
    disk_free_gb = disk_info.get("free_gb", 0)

    # Power status phrasing
    if not has_bat:
        power_str = "running on AC power"
    elif is_charging:
        power_str = f"battery is at {bat_pct} percent and charging"
    else:
        power_str = f"battery is at {bat_pct} percent on battery power"

    # Memory pressure phrasing
    if ram_pct >= 85:
        ram_desc = f"memory pressure is elevated at {ram_pct} percent with {ram_free_gb} gigabytes free"
    else:
        ram_desc = f"memory is healthy at {ram_pct} percent with {ram_free_gb} gigabytes available"

    disk_desc = f"primary drive has {disk_free_gb} gigabytes free ({disk_pct} percent full)"

    # 2. Derive one useful, high-value observation
    observation = ""
    if disk_pct >= 90 or (disk_free_gb > 0 and disk_free_gb < 15):
        observation = f"Storage is running low with only {disk_free_gb} gigabytes remaining; consider clearing temporary files."
    elif ram_pct >= 85:
        observation = f"Memory pressure is high at {ram_pct} percent; closing inactive applications or browser tabs will boost performance."
    elif cpu_pct >= 80:
        observation = f"CPU load is temporarily high at {cpu_pct} percent from active background tasks."
    elif has_bat and not is_charging and bat_pct is not None and bat_pct <= 20:
        observation = f"Battery is running low at {bat_pct} percent; plugging into your charger soon is advised."
    elif ram_pct <= 60 and cpu_pct <= 40:
        observation = "All core systems are nominal with abundant memory and disk headroom."
    else:
        observation = "System performance is steady and balanced across all subsystems."

    briefing_msg = f"Your computer is running well. You're {power_str}, {ram_desc}, and your {disk_desc}. One observation: {observation}"

    return {
        "success": True,
        "message": briefing_msg,
        "data": {
            "health": health_data,
            "observation": observation,
            "summary": briefing_msg
        }
    }


def get_recent_actions(limit: int = 5) -> Dict[str, Any]:
    """
    Retrieves the most recent actions executed by the assistant from the JSONL log.
    """
    log_file = config.JSONL_LOG_FILE
    if not os.path.exists(log_file):
        return {
            "success": True,
            "message": "I haven't performed any actions yet in this session.",
            "data": {"actions": []}
        }
        
    actions = []
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in reversed(lines):
                if not line.strip():
                    continue
                try:
                    action_data = json.loads(line)
                    actions.append(action_data)
                    if len(actions) >= limit:
                        break
                except json.JSONDecodeError:
                    pass
                    
        if not actions:
            return {
                "success": True,
                "message": "I haven't performed any actions recently.",
                "data": {"actions": []}
            }
            
        action_summaries = []
        for a in actions:
            tool = a.get("tool", a.get("tool_name", "unknown"))
            status = a.get("status", "unknown")
            perm = a.get("permission_level", "L1")
            clean_perm = "L1" if "Level 1" in perm or "L1" in perm else "L2" if "Level 2" in perm else "L3"
            action_summaries.append(f"{tool} ({clean_perm}, {status})")
            
        msg = f"My most recent actions were: {', '.join(action_summaries)}."
        return {
            "success": True,
            "message": msg,
            "data": {"actions": actions}
        }
    except Exception as e:
        return {
            "success": False,
            "message": "I couldn't read the action log.",
            "error": str(e)
        }


def explain_last_action() -> Dict[str, Any]:
    """
    Reads the most recent action from the action log and produces an accurate,
    transparent spoken recap clearly distinguishing what William said from what William did.
    """
    log_file = config.JSONL_LOG_FILE
    if not os.path.exists(log_file):
        return {
            "success": True,
            "message": "I haven't executed any actions on your computer yet.",
            "data": {}
        }

    last_record = None
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in reversed(lines):
                line_str = line.strip()
                if not line_str:
                    continue
                try:
                    data = json.loads(line_str)
                    # Skip queries about what we just did to avoid recursive introspection
                    tool = data.get("tool", data.get("tool_name", ""))
                    if tool in ("explain_last_action", "get_recent_actions"):
                        continue
                    last_record = data
                    break
                except Exception:
                    pass

        if not last_record:
            return {
                "success": True,
                "message": "No previous system tool actions have been recorded yet.",
                "data": {}
            }

        tool_name = last_record.get("tool", last_record.get("tool_name", "unknown"))
        user_request = last_record.get("transcript", "your request")
        perm_level = last_record.get("permission_level", "Level 1 (Safe)")
        status = last_record.get("status", "EXECUTED")
        result_desc = last_record.get("result", "") or last_record.get("error", "completed")
        args = last_record.get("arguments", {})

        friendly_tool = tool_name.replace("_", " ")
        args_summary = ", ".join(f"{k} as {v}" for k, v in args.items()) if args else "no extra parameters"

        recap = (
            f"For your request '{user_request}', what I announced was that I was executing {friendly_tool}. "
            f"What I actually did on your system was execute the {tool_name} tool with {args_summary} "
            f"under {perm_level}, which resulted in: {result_desc} (status: {status})."
        )

        return {
            "success": True,
            "message": recap,
            "data": {
                "user_request": user_request,
                "tool": tool_name,
                "permission_level": perm_level,
                "status": status,
                "arguments": args,
                "result": result_desc
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": "I was unable to inspect the recent action log.",
            "error": str(e)
        }
