"""
Files Tool Module for William-1 (v0.2).
Provides safe file operations strictly confined to configured root paths.
Supports named shortcuts (e.g. 'william-1 project'), strict path normalization,
and humanized file metadata formatting.
"""

import os
import time
import subprocess
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from config import config


def _humanize_bytes(size_bytes: int) -> str:
    """Formats raw byte counts into clean, humanized string (e.g. 6.2 GB, 450.5 KB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.1f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def _is_path_allowed(target_path: str) -> Tuple[bool, Optional[str]]:
    """
    Checks if target_path is within one of the allowed root directories.
    Strictly normalizes path to prevent directory traversal attacks ('../', symlinks).
    Returns: (is_allowed, resolved_absolute_normalized_path)
    """
    if not target_path:
        return False, None

    try:
        resolved = os.path.normpath(os.path.abspath(os.path.expanduser(target_path)))
        allowed_roots = config.get_allowed_root_paths().values()

        for root in allowed_roots:
            if not os.path.exists(root):
                continue
            root_abs = os.path.normpath(os.path.abspath(root))
            try:
                if os.path.commonpath([resolved, root_abs]) == root_abs:
                    return True, resolved
            except ValueError:
                # Different drives on Windows
                continue

        return False, resolved
    except Exception:
        return False, None


def _resolve_friendly_or_relative_path(path_or_name: str) -> Tuple[bool, str, str]:
    """
    Resolves friendly root names ('documents', 'downloads'), named shortcuts ('william-1 project'),
    or relative/absolute paths.
    Returns: (is_allowed, resolved_path, display_name)
    """
    if not path_or_name or not path_or_name.strip():
        roots = config.get_allowed_root_paths()
        docs = roots.get("documents", roots.get("home", os.getcwd()))
        return True, docs, "Documents"

    cleaned = path_or_name.strip().lower()

    # 0. Check episodic memory for "yesterday", "working on", "recent work"
    if any(k in cleaned for k in ("yesterday", "working on", "last session", "recent work", "last time")):
        try:
            from memory.memory_manager import memory_manager
            recent_proj = memory_manager.resolve_recent_project_from_episodic()
            if recent_proj:
                cleaned = recent_proj.lower()
                path_or_name = recent_proj
        except Exception:
            pass

    # 1. Check named shortcuts
    shortcuts = config.get_named_shortcuts()
    if cleaned in shortcuts:
        target = shortcuts[cleaned]
        is_allowed, resolved = _is_path_allowed(target)
        if is_allowed and resolved:
            return True, resolved, os.path.basename(resolved) or cleaned.title()

    # 1.5. Check project memory resolution (e.g. "my William-1 project", "William-1", etc.)
    try:
        from memory.memory_manager import memory_manager
        proj_candidate = cleaned
        for prefix in ("my ", "open ", "open my "):
            if proj_candidate.startswith(prefix):
                proj_candidate = proj_candidate[len(prefix):].strip()
        if proj_candidate.endswith(" project"):
            proj_candidate = proj_candidate[:-8].strip()

        mem_res = memory_manager.resolve_open_project_from_memory(proj_candidate)
        if mem_res.get("success") and mem_res.get("path"):
            target = mem_res["path"]
            is_allowed, resolved = _is_path_allowed(target)
            if is_allowed and resolved:
                return True, resolved, os.path.basename(resolved) or proj_candidate.title()
    except Exception:
        pass

    # 2. Check friendly root name
    roots = config.get_allowed_root_paths()
    if cleaned in roots:
        return True, roots[cleaned], cleaned.capitalize()

    # 3. Standard path check
    is_allowed, resolved = _is_path_allowed(path_or_name.strip())
    if is_allowed and resolved:
        return True, resolved, os.path.basename(resolved) or resolved
    else:
        return False, path_or_name.strip(), path_or_name.strip()


def open_folder(folder: str = "documents") -> Dict[str, Any]:
    """
    Opens a folder in File Explorer within permitted roots or named shortcuts.
    """
    is_allowed, resolved_path, display_name = _resolve_friendly_or_relative_path(folder)

    if not is_allowed:
        return {
            "success": False,
            "message": f"I cannot open '{folder}'. It is outside my permitted folders.",
            "error": "Path traversal or unauthorized root path."
        }

    if not os.path.exists(resolved_path):
        return {
            "success": False,
            "message": f"The folder '{display_name}' does not exist -- want me to open your Documents folder instead?",
            "error": "Folder not found.",
            "alternative": {
                "tool": "open_folder",
                "arguments": {"folder": "documents"},
                "suggestion": "Open Documents folder"
            }
        }

    if not os.path.isdir(resolved_path):
        return {
            "success": False,
            "message": f"'{display_name}' is a file, not a directory.",
            "error": "Not a directory."
        }

    try:
        os.startfile(resolved_path)
        return {
            "success": True,
            "message": f"I've opened your {display_name} folder.",
            "data": {"path": resolved_path, "display_name": display_name}
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"I encountered a problem opening the {display_name} folder.",
            "error": str(e)
        }


def open_file(file_path: str) -> Dict[str, Any]:
    """
    Opens a file with its default associated application if within allowed root paths.
    """
    is_allowed, resolved_path = _is_path_allowed(file_path)

    if not is_allowed:
        return {
            "success": False,
            "message": "I cannot open that file because it is outside my permitted folders.",
            "error": "Unauthorized file path."
        }

    if not resolved_path or not os.path.exists(resolved_path):
        fname = os.path.basename(file_path)
        return {
            "success": False,
            "message": f"I couldn't find the file '{fname}' -- want me to search for it across your documents?",
            "error": "File not found.",
            "alternative": {
                "tool": "search_files",
                "arguments": {"query": fname, "root_folder": "documents"},
                "suggestion": f"Search for {fname} in Documents"
            }
        }

    if not os.path.isfile(resolved_path):
        return {
            "success": False,
            "message": f"'{os.path.basename(file_path)}' is not a regular file.",
            "error": "Not a file."
        }

    try:
        os.startfile(resolved_path)
        return {
            "success": True,
            "message": f"I've opened {os.path.basename(resolved_path)} for you.",
            "data": {"path": resolved_path, "filename": os.path.basename(resolved_path)}
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"I was unable to open the file {os.path.basename(resolved_path)}.",
            "error": str(e)
        }


def list_directory(folder: str = "documents", max_items: int = 15) -> Dict[str, Any]:
    """
    Lists files and subdirectories within an allowed folder path or shortcut.
    """
    is_allowed, resolved_path, display_name = _resolve_friendly_or_relative_path(folder)

    if not is_allowed:
        return {
            "success": False,
            "message": f"Access to '{folder}' is restricted to permitted folders only.",
            "error": "Path traversal or unauthorized directory access."
        }

    if not os.path.exists(resolved_path) or not os.path.isdir(resolved_path):
        return {
            "success": False,
            "message": f"The folder '{display_name}' was not found.",
            "error": "Directory does not exist."
        }

    try:
        entries = os.listdir(resolved_path)
        items = []
        for entry in entries[:max_items]:
            entry_path = os.path.join(resolved_path, entry)
            is_dir = os.path.isdir(entry_path)
            items.append({
                "name": entry,
                "type": "folder" if is_dir else "file",
            })

        count_str = f"{len(items)} items" if len(items) == len(entries) else f"{len(items)} of {len(entries)} items"
        names_sample = ", ".join([it["name"] for it in items[:6]])

        return {
            "success": True,
            "message": f"In your {display_name} folder, I found {count_str}, including: {names_sample}.",
            "data": {
                "folder": display_name,
                "path": resolved_path,
                "total_count": len(entries),
                "items": items,
            }
        }
    except PermissionError:
        return {
            "success": False,
            "message": f"Permission was denied when attempting to view {display_name}.",
            "error": "Permission denied."
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Could not list contents of {display_name}.",
            "error": str(e)
        }


def search_files(
    query: str,
    root_folder: str = "documents",
    extension: str = "",
    max_results: int = 10,
) -> Dict[str, Any]:
    """
    Searches for files matching a name query and/or extension within an allowed root directory.
    """
    is_allowed, resolved_path, display_name = _resolve_friendly_or_relative_path(root_folder)

    if not is_allowed:
        return {
            "success": False,
            "message": "Search is restricted to permitted folders.",
            "error": "Unauthorized search root."
        }

    if not os.path.exists(resolved_path):
        return {
            "success": False,
            "message": f"The folder '{display_name}' does not exist.",
            "error": "Folder not found."
        }

    query_lower = query.lower().strip() if query else ""
    ext_lower = extension.lower().strip().lstrip(".")

    matches = []
    try:
        for root_dir, dirs, files in os.walk(resolved_path):
            rel_depth = os.path.relpath(root_dir, resolved_path).count(os.sep)
            if rel_depth > 4:
                dirs.clear()
                continue

            for fname in files:
                fname_lower = fname.lower()
                name_match = (query_lower in fname_lower) if query_lower else True
                ext_match = fname_lower.endswith("." + ext_lower) if ext_lower else True

                if name_match and ext_match:
                    full_path = os.path.join(root_dir, fname)
                    size_b = os.path.getsize(full_path) if os.path.exists(full_path) else 0
                    matches.append({
                        "name": fname,
                        "path": full_path,
                        "size": _humanize_bytes(size_b),
                    })
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break

        if matches:
            file_names = ", ".join([m["name"] for m in matches[:4]])
            msg = f"Found {len(matches)} matching file{'s' if len(matches) != 1 else ''}: {file_names}."
        else:
            msg = f"No files matching '{query}' were found in {display_name}."

        return {
            "success": True,
            "message": msg,
            "data": {"matches": matches, "query": query, "root": display_name}
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Encountered an error while searching for files.",
            "error": str(e)
        }


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Retrieves metadata (size, modified date, type) for a file within allowed paths.
    """
    is_allowed, resolved_path = _is_path_allowed(file_path)

    if not is_allowed:
        return {
            "success": False,
            "message": "Access to that file is restricted.",
            "error": "Unauthorized path."
        }

    if not resolved_path or not os.path.exists(resolved_path):
        return {
            "success": False,
            "message": f"Could not find '{os.path.basename(file_path)}'.",
            "error": "File not found."
        }

    try:
        stat_info = os.stat(resolved_path)
        size_formatted = _humanize_bytes(stat_info.st_size)
        mtime = datetime.fromtimestamp(stat_info.st_mtime).strftime("%B %d, %Y at %I:%M %p")

        is_dir = os.path.isdir(resolved_path)
        type_str = "Folder" if is_dir else f"{os.path.splitext(resolved_path)[1].upper().lstrip('.')} File"

        msg = f"'{os.path.basename(resolved_path)}' is a {type_str}, size {size_formatted}, last modified on {mtime}."

        return {
            "success": True,
            "message": msg,
            "data": {
                "name": os.path.basename(resolved_path),
                "path": resolved_path,
                "size": size_formatted,
                "modified": mtime,
                "type": type_str,
            }
        }
    except Exception as e:
        return {
            "success": False,
            "message": "Could not read file details.",
            "error": str(e)
        }


def delete_file(target_path: str) -> Dict[str, Any]:
    """
    Deletes a file or directory within permitted root paths (Level 3 destructive - requires confirmation).
    """
    is_allowed, resolved_path = _is_path_allowed(target_path)
    if not is_allowed:
        return {
            "success": False,
            "message": f"I cannot delete '{target_path}'. It is outside my permitted root folders.",
            "error": "Access restricted. Target path is outside permitted sandbox roots."
        }

    if not resolved_path or not os.path.exists(resolved_path):
        return {
            "success": False,
            "message": f"The target '{os.path.basename(target_path)}' does not exist.",
            "error": "File or folder not found."
        }

    try:
        base = os.path.basename(resolved_path)
        if os.path.isdir(resolved_path):
            import shutil
            shutil.rmtree(resolved_path)
            target_type = "folder"
        else:
            os.remove(resolved_path)
            target_type = "file"

        return {
            "success": True,
            "message": f"I have permanently deleted the {target_type} '{base}'.",
            "data": {"path": resolved_path, "target_type": target_type}
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to delete '{os.path.basename(target_path)}'.",
            "error": str(e)
        }
