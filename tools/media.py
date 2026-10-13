"""
Media Tool Module for William-1 (v0.2).
Controls media playback (play/pause, next, previous, volume adjustments)
via operating system virtual key events with cross-platform detection.
"""

import os
import platform
import ctypes
from typing import Dict, Any


# Virtual Key Codes on Windows
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


def _send_vk(vk_code: int):
    """Sends keydown and keyup for given virtual key code."""
    if platform.system() == "Windows":
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)


def play_pause() -> Dict[str, Any]:
    """
    Toggles media playback (Play / Pause).
    """
    if platform.system() != "Windows":
        return {
            "success": False,
            "message": f"Media control is not supported on {platform.system()}.",
            "error": "Unsupported platform."
        }

    try:
        _send_vk(VK_MEDIA_PLAY_PAUSE)
        return {"success": True, "message": "Media playback toggled.", "data": {"action": "play_pause"}}
    except Exception as e:
        return {"success": False, "message": "Could not toggle media playback.", "error": str(e)}


def next_track() -> Dict[str, Any]:
    """
    Skips to the next media track.
    """
    if platform.system() != "Windows":
        return {
            "success": False,
            "message": f"Media control is not supported on {platform.system()}.",
            "error": "Unsupported platform."
        }

    try:
        _send_vk(VK_MEDIA_NEXT_TRACK)
        return {"success": True, "message": "Skipped to next track.", "data": {"action": "next"}}
    except Exception as e:
        return {"success": False, "message": "Could not skip track.", "error": str(e)}


def previous_track() -> Dict[str, Any]:
    """
    Skips back to previous media track.
    """
    if platform.system() != "Windows":
        return {
            "success": False,
            "message": f"Media control is not supported on {platform.system()}.",
            "error": "Unsupported platform."
        }

    try:
        _send_vk(VK_MEDIA_PREV_TRACK)
        return {"success": True, "message": "Skipped to previous track.", "data": {"action": "previous"}}
    except Exception as e:
        return {"success": False, "message": "Could not return to previous track.", "error": str(e)}


def volume_up(steps: int = 2) -> Dict[str, Any]:
    """
    Increases volume by a number of steps.
    """
    if platform.system() != "Windows":
        return {
            "success": False,
            "message": f"Volume control is not supported on {platform.system()}.",
            "error": "Unsupported platform."
        }

    try:
        count = max(1, min(20, int(steps)))
        for _ in range(count):
            _send_vk(VK_VOLUME_UP)
        return {"success": True, "message": f"Volume increased by {count * 2} percent.", "data": {"steps": count}}
    except Exception as e:
        return {"success": False, "message": "Could not increase volume.", "error": str(e)}


def volume_down(steps: int = 2) -> Dict[str, Any]:
    """
    Decreases volume by a number of steps.
    """
    if platform.system() != "Windows":
        return {
            "success": False,
            "message": f"Volume control is not supported on {platform.system()}.",
            "error": "Unsupported platform."
        }

    try:
        count = max(1, min(20, int(steps)))
        for _ in range(count):
            _send_vk(VK_VOLUME_DOWN)
        return {"success": True, "message": f"Volume decreased by {count * 2} percent.", "data": {"steps": count}}
    except Exception as e:
        return {"success": False, "message": "Could not decrease volume.", "error": str(e)}
