"""
William-1 Persistent Memory Layer (v0.3+).
Exports key components for memory management, retrieval, and storage.
"""

from memory.memory_manager import memory_manager, MemoryManager, WorkingMemory
from memory.memory_store import MemoryStore
from memory.memory_settings import MemorySettings
from memory.project_memory import ProjectMemoryManager
from memory.conversation_summary import ConversationSummaryManager
from memory.memory_retrieval import MemoryRetrievalEngine
from memory.memory_policy import (
    is_valid_memory_candidate,
    contains_secrets,
    contains_sensitive_personal_info,
    is_preference_update,
)

__all__ = [
    "memory_manager",
    "MemoryManager",
    "WorkingMemory",
    "MemoryStore",
    "MemorySettings",
    "ProjectMemoryManager",
    "ConversationSummaryManager",
    "MemoryRetrievalEngine",
    "is_valid_memory_candidate",
    "contains_secrets",
    "contains_sensitive_personal_info",
    "is_preference_update",
]
