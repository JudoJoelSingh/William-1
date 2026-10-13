"""
Memory Store for William-1 Persistent Memory Layer (v0.3+).
SQLite backend with WAL mode, parameterised queries, graceful corruption
recovery, and schema migrations.

Schema v2 adds:
  - memories.deleted_at      (soft-delete; NULL means active)
  - memories.is_deleted      (index-friendly boolean flag, 0/1)
  - memory_settings defaults for new v0.3+ keys
"""

import os
import sqlite3
import shutil
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from config import config
from utils.logger import AuditLogger


CURRENT_SCHEMA_VERSION = 2


class MemoryStore:
    """
    Thread-safe SQLite store managing versioned memory records, projects,
    events, and session summaries with ACID transaction guarantees.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.MEMORY_DB_PATH
        self._ensure_directory()
        self._init_database()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_directory(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=10.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA foreign_keys = ON;")
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            raise
        return conn

    def _init_database(self):
        corrupt_conn = None
        try:
            corrupt_conn = self._get_connection()
            corrupt_conn.execute("SELECT 1;").fetchone()
            self._run_migrations(corrupt_conn)
        except sqlite3.DatabaseError as e:
            # Close the corrupt connection BEFORE moving the file (Windows file-lock)
            if corrupt_conn:
                try:
                    corrupt_conn.close()
                except Exception:
                    pass
            print(f"[Memory Recovery] Detected corrupt database ({e}). Backing up and re-initialising.")
            self._recover_corrupted_database()
            with self._get_connection() as conn:
                self._run_migrations(conn)

    def _recover_corrupted_database(self):
        if os.path.exists(self.db_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            corrupt_backup = f"{self.db_path}.corrupted_{timestamp}.bak"
            try:
                shutil.move(self.db_path, corrupt_backup)
                print(f"[Memory Recovery] Corrupted DB backed up to: {corrupt_backup}")
                AuditLogger.log(
                    user_request="system",
                    tool_name="memory_store_recovery",
                    arguments={"corrupted_file": self.db_path, "backup": corrupt_backup},
                    result="Corrupt DB backed up; fresh DB created",
                    status="EXECUTED",
                    permission_level="LEVEL_1_SAFE",
                )
            except Exception as ex:
                print(f"[Memory Recovery] Could not move corrupted file: {ex}")
                try:
                    os.remove(self.db_path)
                except Exception:
                    pass

    def _run_migrations(self, conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
        """)
        row = conn.execute("SELECT MAX(version) AS ver FROM schema_version;").fetchone()
        current_ver = row["ver"] if row and row["ver"] is not None else 0

        if current_ver < 1:
            self._apply_migration_v1(conn)
        if current_ver < 2:
            self._apply_migration_v2(conn)

    def _apply_migration_v1(self, conn: sqlite3.Connection):
        """Initial baseline schema."""
        now = datetime.now().isoformat()

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT DEFAULT 'user',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_accessed_at TEXT,
                confidence REAL DEFAULT 1.0,
                expires_at TEXT,
                deleted_at TEXT,
                is_deleted INTEGER DEFAULT 0
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_cat ON memories(category);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_content ON memories(content);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(is_deleted);")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                status TEXT DEFAULT 'active',
                technology_stack TEXT,
                current_blocker TEXT,
                next_task TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS project_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_project_events_pid ON project_events(project_id);")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL,
                retention_until TEXT
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_summaries_session ON conversation_summaries(session_id);")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        # Seed default settings
        defaults = [
            ("memory_enabled",      "true"),
            ("auto_capture",        "true"),
            ("confirm_before_save", "false"),
            ("retention_days",      "30"),
            ("top_k",               "5"),
            ("max_token_budget",    "500"),
            ("local_only",          "false"),
        ]
        for k, v in defaults:
            conn.execute("INSERT OR IGNORE INTO memory_settings (key, value) VALUES (?, ?);", (k, v))

        conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (1, ?);", (now,))
        conn.commit()

    def _apply_migration_v2(self, conn: sqlite3.Connection):
        """
        v2: soft-delete columns on memories (if upgrading from v1),
        additional default settings keys.
        """
        now = datetime.now().isoformat()

        # Add columns only if absent (SQLite has no IF NOT EXISTS for columns)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(memories);")}
        if "deleted_at" not in cols:
            conn.execute("ALTER TABLE memories ADD COLUMN deleted_at TEXT;")
        if "is_deleted" not in cols:
            conn.execute("ALTER TABLE memories ADD COLUMN is_deleted INTEGER DEFAULT 0;")
            conn.execute("UPDATE memories SET is_deleted = 0 WHERE is_deleted IS NULL;")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_active ON memories(is_deleted);"
            )

        # Ensure new settings keys exist
        extra_defaults = [
            ("auto_capture",        "true"),
            ("confirm_before_save", "false"),
            ("top_k",               "5"),
            ("max_token_budget",    "500"),
            ("local_only",          "false"),
        ]
        for k, v in extra_defaults:
            conn.execute("INSERT OR IGNORE INTO memory_settings (key, value) VALUES (?, ?);", (k, v))

        conn.execute("INSERT OR IGNORE INTO schema_version (version, applied_at) VALUES (2, ?);", (now,))
        conn.commit()

    # ------------------------------------------------------------------
    # Memory CRUD
    # ------------------------------------------------------------------

    def insert_memory(
        self,
        category: str,
        content: str,
        source: str = "user",
        confidence: float = 1.0,
        expires_at: Optional[str] = None,
    ) -> int:
        """Inserts a new active memory record."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO memories
                  (category, content, source, created_at, updated_at,
                   last_accessed_at, confidence, expires_at, is_deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0);
                """,
                (category, content, source, now, now, now, confidence, expires_at),
            )
            conn.commit()
            return cursor.lastrowid

    def update_memory(self, memory_id: int, content: str, category: Optional[str] = None) -> bool:
        """Updates an existing memory's content and bumps updated_at."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if category:
                cursor.execute(
                    "UPDATE memories SET content=?, category=?, updated_at=? WHERE id=? AND is_deleted=0;",
                    (content, category, now, memory_id),
                )
            else:
                cursor.execute(
                    "UPDATE memories SET content=?, updated_at=? WHERE id=? AND is_deleted=0;",
                    (content, now, memory_id),
                )
            conn.commit()
            return cursor.rowcount > 0

    def touch_memory_accessed(self, memory_id: int):
        """Updates last_accessed_at timestamp."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE memories SET last_accessed_at=? WHERE id=? AND is_deleted=0;",
                (now, memory_id),
            )
            conn.commit()

    def get_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Returns a single active memory by ID."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id=? AND is_deleted=0;", (memory_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_memories(self, category: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Lists active memories, optionally filtered by category."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            if category:
                rows = conn.execute(
                    """SELECT * FROM memories
                       WHERE category=? AND is_deleted=0
                         AND (expires_at IS NULL OR expires_at > ?)
                       ORDER BY updated_at DESC LIMIT ?;""",
                    (category, now, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM memories
                       WHERE is_deleted=0
                         AND (expires_at IS NULL OR expires_at > ?)
                       ORDER BY updated_at DESC LIMIT ?;""",
                    (now, limit),
                ).fetchall()
            return [dict(r) for r in rows]

    def soft_delete_memory(self, memory_id: int) -> bool:
        """Soft-deletes a memory (marks is_deleted=1, records timestamp)."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE memories SET is_deleted=1, deleted_at=? WHERE id=? AND is_deleted=0;",
                (now, memory_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_memory(self, memory_id: int) -> bool:
        """Hard-deletes a memory by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE id=?;", (memory_id,))
            conn.commit()
            return cursor.rowcount > 0

    def soft_delete_memories_matching(self, keyword: str) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Soft-deletes active memories containing keyword.
        Returns (count_deleted, list_of_deleted_records) for audit trail.
        """
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE content LIKE ? AND is_deleted=0;",
                (f"%{keyword}%",),
            ).fetchall()
            if not rows:
                return 0, []
            ids = [r["id"] for r in rows]
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"UPDATE memories SET is_deleted=1, deleted_at=? WHERE id IN ({placeholders});",
                [now] + ids,
            )
            conn.commit()
            return len(ids), [dict(r) for r in rows]

    def delete_memories_matching(self, keyword: str) -> int:
        """Hard-deletes memories containing keyword. Returns count."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memories WHERE content LIKE ?;", (f"%{keyword}%",))
            conn.commit()
            return cursor.rowcount

    def find_candidates_by_category(self, category: str, limit: int = 100) -> List[Dict[str, Any]]:
        """All active memories for a category (for deduplication scanning)."""
        return self.list_memories(category=category, limit=limit)

    # ------------------------------------------------------------------
    # Expiry / cleanup
    # ------------------------------------------------------------------

    def purge_expired_memories(self) -> int:
        """Soft-deletes memories whose expires_at is in the past. Returns count."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE memories SET is_deleted=1, deleted_at=? "
                "WHERE is_deleted=0 AND expires_at IS NOT NULL AND expires_at <= ?;",
                (now, now),
            )
            conn.commit()
            return cursor.rowcount

    def purge_expired_summaries(self) -> int:
        """Hard-deletes conversation summaries past their retention_until date. Returns count."""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM conversation_summaries "
                "WHERE retention_until IS NOT NULL AND retention_until <= ?;",
                (now,),
            )
            conn.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Projects & Events
    # ------------------------------------------------------------------

    def upsert_project(
        self,
        name: str,
        description: Optional[str] = None,
        status: Optional[str] = None,
        technology_stack: Optional[str] = None,
        current_blocker: Optional[str] = None,
        next_task: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        name_clean = name.strip()
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM projects WHERE LOWER(name)=LOWER(?);", (name_clean,)
            ).fetchone()
            if existing:
                new_desc = description if description is not None else existing["description"]
                new_status = status if status is not None else existing["status"]
                new_stack = technology_stack if technology_stack is not None else existing["technology_stack"]
                new_blocker = current_blocker if current_blocker is not None else existing["current_blocker"]
                new_next = next_task if next_task is not None else existing["next_task"]
                conn.execute(
                    """UPDATE projects SET description=?, status=?, technology_stack=?,
                       current_blocker=?, next_task=?, updated_at=? WHERE id=?;""",
                    (new_desc, new_status, new_stack, new_blocker, new_next, now, existing["id"]),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM projects WHERE id=?;", (existing["id"],)).fetchone()
                return dict(row)
            else:
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT INTO projects
                       (name, description, status, technology_stack, current_blocker, next_task, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                    (
                        name_clean,
                        description or "",
                        status or "active",
                        technology_stack or "",
                        current_blocker or "",
                        next_task or "",
                        now, now,
                    ),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM projects WHERE id=?;", (cursor.lastrowid,)).fetchone()
                return dict(row)

    def get_project(self, name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE LOWER(name)=LOWER(?);", (name.strip(),)
            ).fetchone()
            return dict(row) if row else None

    def list_projects(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC;").fetchall()
            return [dict(r) for r in rows]

    def delete_project(self, name: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM projects WHERE LOWER(name)=LOWER(?);", (name.strip(),))
            conn.commit()
            return cursor.rowcount > 0

    def add_project_event(self, project_id: int, event_type: str, summary: str) -> int:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO project_events (project_id, event_type, summary, created_at) VALUES (?, ?, ?, ?);",
                (project_id, event_type, summary, now),
            )
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?;", (now, project_id))
            conn.commit()
            return cursor.lastrowid

    def get_project_events(self, project_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM project_events WHERE project_id=? ORDER BY created_at DESC LIMIT ?;",
                (project_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Episodic Summaries
    # ------------------------------------------------------------------

    def insert_conversation_summary(
        self, session_id: str, summary: str, retention_until: Optional[str] = None
    ) -> int:
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversation_summaries (session_id, summary, created_at, retention_until) VALUES (?, ?, ?, ?);",
                (session_id, summary, now, retention_until),
            )
            conn.commit()
            return cursor.lastrowid

    def list_recent_summaries(self, limit: int = 5) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM conversation_summaries ORDER BY created_at DESC LIMIT ?;", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Settings (key-value)
    # ------------------------------------------------------------------

    def get_setting(self, key: str, default: str = "") -> str:
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM memory_settings WHERE key=?;", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO memory_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
                (key, value),
            )
            conn.commit()

    # ------------------------------------------------------------------
    # Export / Import helpers
    # ------------------------------------------------------------------

    def export_non_sensitive_memories(self) -> List[Dict[str, Any]]:
        """Returns all active memories without any redacted/secret content."""
        from memory.memory_policy import contains_secrets
        raw = self.list_memories(limit=10000)
        safe = []
        for m in raw:
            has_secret, _ = contains_secrets(m.get("content", ""))
            if not has_secret:
                safe.append(m)
        return safe
