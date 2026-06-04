import json
import os
import sqlite3
from typing import Set, Dict, Any, Optional

DEFAULT_DB_FILE = "qrbot.db"
LEGACY_JSON_FILE = "bot_data.json"
DEFAULT_RUNTIME_LOG_FILE = "bot.log"
DB_PATH_ENV = "QRBOT_DB_PATH"
LEGACY_DB_FILE_ENV = "QRBOT_DB_FILE"
DATA_DIR_ENV = "QRBOT_DATA_DIR"
ACTIVITY_LOG_ENV = "QRBOT_ACTIVITY_LOG_FILE"
RUNTIME_LOG_ENV = "QRBOT_RUNTIME_LOG_FILE"
IMMEDIATE_FLUSH_ENV = "QRBOT_IMMEDIATE_FLUSH"


def _env_truthy(name: str, default: str = "1") -> bool:
    value = os.getenv(name, default)
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _ensure_dir(path: str) -> Optional[str]:
    """Create directory when possible and return absolute path."""
    if not path:
        return None

    candidate = os.path.abspath(path)
    try:
        os.makedirs(candidate, exist_ok=True)
    except OSError:
        return None

    return candidate if os.path.isdir(candidate) and os.access(candidate, os.W_OK) else None


def _resolve_data_dir() -> str:
    """Resolve preferred persistent data directory."""
    data_dir = os.getenv(DATA_DIR_ENV)
    if data_dir:
        ensured = _ensure_dir(data_dir)
        if ensured:
            return ensured

    for candidate in (
        "/data",
        "/var/data",
        "/var/lib/qrbot",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"),
        os.path.dirname(os.path.abspath(__file__)),
    ):
        ensured = _ensure_dir(candidate)
        if ensured:
            return ensured

    return os.path.dirname(os.path.abspath(__file__))


def _can_write_to_dir(path: str) -> bool:
    """Return True when directory exists and current process can write to it."""
    return os.path.isdir(path) and os.access(path, os.W_OK)


def _resolve_writable_file_path(env_name: str, default_filename: str, base_dir: Optional[str] = None) -> str:
    """Resolve file path from env, but fall back if parent directory is unavailable."""
    env_file = os.getenv(env_name)
    if env_file:
        candidate = os.path.abspath(env_file)
        parent_dir = os.path.dirname(candidate) or "."
        if _can_write_to_dir(parent_dir):
            return candidate

    root_dir = os.path.abspath(base_dir) if base_dir else _resolve_data_dir()
    return os.path.join(root_dir, default_filename)


def _resolve_db_path() -> str:
    """Resolve SQLite database path."""
    env_file = os.getenv(DB_PATH_ENV) or os.getenv(LEGACY_DB_FILE_ENV)
    if env_file:
        return os.path.abspath(env_file)

    return os.path.join(_resolve_data_dir(), DEFAULT_DB_FILE)


def resolve_runtime_log_path(base_dir: Optional[str] = None) -> str:
    """Resolve runtime log path with persistent-storage-first strategy."""
    return _resolve_writable_file_path(RUNTIME_LOG_ENV, DEFAULT_RUNTIME_LOG_FILE, base_dir)


class Database:
    def __init__(self):
        self.filename = _resolve_db_path()
        self.data_dir = os.path.dirname(self.filename) or "."
        self.activity_log_file = _resolve_writable_file_path(ACTIVITY_LOG_ENV, "activity.log", self.data_dir)
        self.runtime_log_file = resolve_runtime_log_path(self.data_dir)
        self.legacy_json_path = os.path.join(self.data_dir, LEGACY_JSON_FILE)
        self.immediate_flush = _env_truthy(IMMEDIATE_FLUSH_ENV, "1")
        self.users: Dict[int, Dict[str, float]] = {}
        self.banned: Set[int] = set()
        self.stats: Dict[str, Any] = {
            "commands": {},
            "performance": {"total_time": 0.0, "count": 0},
            "errors": {},
        }
        self.pending_broadcasts: Dict[str, Any] = {}
        self.security: Dict[str, Any] = {}
        self.user_prefs: Dict[str, Any] = {}
        self.meta: Dict[str, Any] = {"last_maintenance_date": ""}
        self._dirty = False
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.filename)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _initialize(self):
        os.makedirs(self.data_dir, exist_ok=True)
        db_exists = os.path.exists(self.filename) and os.path.getsize(self.filename) > 0
        with self._connect() as conn:
            self._create_schema(conn)
        if not db_exists and os.path.exists(self.legacy_json_path):
            self._import_legacy_json()
        self.load()

    def _create_schema(self, conn: sqlite3.Connection):
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                joined_at REAL NOT NULL DEFAULT 0,
                last_active REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS banned_users (
                user_id INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pending_broadcasts (
                admin_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                timestamp REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS security (
                user_id TEXT PRIMARY KEY,
                violations INTEGER NOT NULL DEFAULT 0,
                penalty_end REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS user_prefs (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        conn.commit()

    def _reset_in_memory(self):
        self.users = {}
        self.banned = set()
        self.stats = {
            "commands": {},
            "performance": {"total_time": 0.0, "count": 0},
            "errors": {},
        }
        self.pending_broadcasts = {}
        self.security = {}
        self.user_prefs = {}
        self.meta = {"last_maintenance_date": ""}

    def _normalize_loaded_data(self):
        raw_users = self.users
        if isinstance(raw_users, list):
            self.users = {int(uid): {"joined_at": 0, "last_active": 0} for uid in raw_users}
        else:
            self.users = {
                int(k): {
                    "joined_at": float((v or {}).get("joined_at", 0) or 0),
                    "last_active": float((v or {}).get("last_active", 0) or 0),
                }
                for k, v in raw_users.items()
            }

        self.banned = {int(uid) for uid in self.banned}

        raw_stats = self.stats or {}
        if "commands" not in raw_stats:
            self.stats = {
                "commands": raw_stats,
                "performance": {"total_time": 0.0, "count": 0},
                "errors": {},
            }
        else:
            self.stats = {
                "commands": dict(raw_stats.get("commands", {})),
                "performance": {
                    "total_time": float(raw_stats.get("performance", {}).get("total_time", 0.0) or 0.0),
                    "count": int(raw_stats.get("performance", {}).get("count", 0) or 0),
                },
                "errors": dict(raw_stats.get("errors", {})),
            }

        self.pending_broadcasts = {
            str(k): {
                "text": str((v or {}).get("text", "")),
                "timestamp": float((v or {}).get("timestamp", 0) or 0),
            }
            for k, v in self.pending_broadcasts.items()
        }
        self.security = {
            str(k): {
                "violations": int((v or {}).get("violations", 0) or 0),
                "penalty_end": float((v or {}).get("penalty_end", 0) or 0),
            }
            for k, v in self.security.items()
        }
        self.user_prefs = {str(k): (v or {}) for k, v in self.user_prefs.items()}
        raw_meta = self.meta if isinstance(self.meta, dict) else {}
        self.meta = {"last_maintenance_date": str(raw_meta.get("last_maintenance_date", "") or "")}

    def _import_legacy_json(self):
        try:
            with open(self.legacy_json_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.users = data.get("users", {})
            self.banned = set(data.get("banned", []))
            self.stats = data.get("stats", {})
            self.pending_broadcasts = data.get("pending_broadcasts", {})
            self.security = data.get("security", {})
            self.user_prefs = data.get("user_prefs", {})
            self.meta = data.get("meta", {})
            self._normalize_loaded_data()
            self._dirty = True
            self.flush()
        except Exception as e:
            print(f"⚠️ Error importing legacy JSON database: {e}")

    def load(self):
        self._reset_in_memory()
        try:
            with self._connect() as conn:
                for row in conn.execute("SELECT user_id, joined_at, last_active FROM users"):
                    self.users[int(row["user_id"])] = {
                        "joined_at": float(row["joined_at"] or 0),
                        "last_active": float(row["last_active"] or 0),
                    }

                self.banned = {
                    int(row["user_id"]) for row in conn.execute("SELECT user_id FROM banned_users")
                }

                for row in conn.execute("SELECT key, value FROM stats"):
                    self.stats[row["key"]] = json.loads(row["value"])

                for row in conn.execute("SELECT admin_id, text, timestamp FROM pending_broadcasts"):
                    self.pending_broadcasts[str(row["admin_id"])] = {
                        "text": row["text"],
                        "timestamp": float(row["timestamp"] or 0),
                    }

                for row in conn.execute("SELECT user_id, violations, penalty_end FROM security"):
                    self.security[str(row["user_id"])] = {
                        "violations": int(row["violations"] or 0),
                        "penalty_end": float(row["penalty_end"] or 0),
                    }

                for row in conn.execute("SELECT user_id, data FROM user_prefs"):
                    self.user_prefs[str(row["user_id"])] = json.loads(row["data"])

                for row in conn.execute("SELECT key, value FROM meta"):
                    self.meta[str(row["key"])] = row["value"]

                self._normalize_loaded_data()
                self._dirty = False
        except Exception as e:
            print(f"⚠️ Error loading database: {e}")

    def save(self):
        """Mark data as dirty and flush immediately when configured."""
        self._dirty = True
        if self.immediate_flush:
            self.flush()

    def flush(self):
        """Write current state to SQLite if dirty."""
        if not self._dirty:
            return

        try:
            with self._connect() as conn:
                conn.execute("BEGIN")
                conn.execute("DELETE FROM users")
                conn.executemany(
                    "INSERT INTO users (user_id, joined_at, last_active) VALUES (?, ?, ?)",
                    [
                        (
                            int(user_id),
                            float(data.get("joined_at", 0) or 0),
                            float(data.get("last_active", 0) or 0),
                        )
                        for user_id, data in self.users.items()
                    ],
                )

                conn.execute("DELETE FROM banned_users")
                conn.executemany(
                    "INSERT INTO banned_users (user_id) VALUES (?)",
                    [(int(user_id),) for user_id in self.banned],
                )

                conn.execute("DELETE FROM stats")
                conn.executemany(
                    "INSERT INTO stats (key, value) VALUES (?, ?)",
                    [
                        ("commands", json.dumps(self.stats.get("commands", {}), ensure_ascii=False)),
                        (
                            "performance",
                            json.dumps(self.stats.get("performance", {"total_time": 0.0, "count": 0}), ensure_ascii=False),
                        ),
                        ("errors", json.dumps(self.stats.get("errors", {}), ensure_ascii=False)),
                    ],
                )

                conn.execute("DELETE FROM pending_broadcasts")
                conn.executemany(
                    "INSERT INTO pending_broadcasts (admin_id, text, timestamp) VALUES (?, ?, ?)",
                    [
                        (
                            str(admin_id),
                            str(data.get("text", "")),
                            float(data.get("timestamp", 0) or 0),
                        )
                        for admin_id, data in self.pending_broadcasts.items()
                    ],
                )

                conn.execute("DELETE FROM security")
                conn.executemany(
                    "INSERT INTO security (user_id, violations, penalty_end) VALUES (?, ?, ?)",
                    [
                        (
                            str(user_id),
                            int(data.get("violations", 0) or 0),
                            float(data.get("penalty_end", 0) or 0),
                        )
                        for user_id, data in self.security.items()
                    ],
                )

                conn.execute("DELETE FROM user_prefs")
                conn.executemany(
                    "INSERT INTO user_prefs (user_id, data) VALUES (?, ?)",
                    [
                        (str(user_id), json.dumps(data, ensure_ascii=False))
                        for user_id, data in self.user_prefs.items()
                    ],
                )

                conn.execute("DELETE FROM meta")
                conn.executemany(
                    "INSERT INTO meta (key, value) VALUES (?, ?)",
                    [(str(key), str(value)) for key, value in self.meta.items()],
                )

                conn.commit()
                self._dirty = False
        except Exception as e:
            print(f"⚠️ Error saving database: {e}")

    def add_user(self, user_id: int):
        import time

        if user_id not in self.users:
            self.users[user_id] = {
                "joined_at": time.time(),
                "last_active": time.time(),
            }
            self.save()

    def update_user_activity(self, user_id: int):
        import time

        if user_id in self.users:
            self.users[user_id]["last_active"] = time.time()
            self.save()
        else:
            self.add_user(user_id)

    def ban_user(self, user_id: int):
        self.banned.add(user_id)
        self.save()

    def unban_user(self, user_id: int):
        if user_id in self.banned:
            self.banned.remove(user_id)
            self.save()

    def is_banned(self, user_id: int) -> bool:
        return user_id in self.banned

    def increment_stat(self, command: str):
        if "commands" not in self.stats:
            self.stats["commands"] = {}
        self.stats["commands"][command] = self.stats["commands"].get(command, 0) + 1
        self.save()

    def record_performance(self, duration: float):
        if "performance" not in self.stats:
            self.stats["performance"] = {"total_time": 0.0, "count": 0}

        self.stats["performance"]["total_time"] += duration
        self.stats["performance"]["count"] += 1
        self.save()

    def record_error(self, error_type: str):
        if "errors" not in self.stats:
            self.stats["errors"] = {}
        self.stats["errors"][error_type] = self.stats["errors"].get(error_type, 0) + 1
        self.save()

    def reset_stats(self):
        self.stats = {
            "commands": {},
            "performance": {"total_time": 0.0, "count": 0},
            "errors": {},
        }
        self.save()

    def set_pending_broadcast(self, admin_id: int, text: str, timestamp: float):
        self.pending_broadcasts[str(admin_id)] = {"text": text, "timestamp": timestamp}
        self.save()

    def get_pending_broadcast(self, admin_id: int):
        return self.pending_broadcasts.get(str(admin_id))

    def clear_pending_broadcast(self, admin_id: int):
        if str(admin_id) in self.pending_broadcasts:
            del self.pending_broadcasts[str(admin_id)]
            self.save()

    def get_user_security(self, user_id: int) -> Dict[str, Any]:
        return self.security.get(str(user_id), {"violations": 0, "penalty_end": 0})

    def update_user_security(self, user_id: int, violations: int = None, penalty_end: float = None):
        uid = str(user_id)
        if uid not in self.security:
            self.security[uid] = {"violations": 0, "penalty_end": 0}

        if violations is not None:
            self.security[uid]["violations"] = violations
        if penalty_end is not None:
            self.security[uid]["penalty_end"] = penalty_end

        self.save()

    def set_user_style(self, user_id: int, template_name: str):
        uid = str(user_id)
        if uid not in self.user_prefs:
            self.user_prefs[uid] = {}
        self.user_prefs[uid]["style_template"] = template_name
        self.save()

    def get_user_style(self, user_id: int) -> str:
        uid = str(user_id)
        return self.user_prefs.get(uid, {}).get("style_template", "classic")

    def set_user_qr_style(self, user_id: int, fg_color: tuple, bg_color: tuple):
        """Save user's custom QR color settings."""
        uid = str(user_id)
        if uid not in self.user_prefs:
            self.user_prefs[uid] = {}

        self.user_prefs[uid]["custom_qr"] = {
            "fg_color": list(fg_color),
            "bg_color": list(bg_color),
        }
        self.save()

    def get_user_qr_style(self, user_id: int):
        """Get user's custom QR color settings."""
        uid = str(user_id)
        if uid in self.user_prefs:
            custom = self.user_prefs[uid].get("custom_qr")
            if custom:
                return (tuple(custom["fg_color"]), tuple(custom["bg_color"]))
        return None

    def clear_user_qr_style(self, user_id: int):
        """Clear user's custom QR settings."""
        uid = str(user_id)
        if uid in self.user_prefs:
            self.user_prefs[uid].pop("custom_qr", None)
            self.save()

    def get_last_maintenance_date(self) -> str:
        return str(self.meta.get("last_maintenance_date", "") or "")

    def set_last_maintenance_date(self, date_value: str):
        self.meta["last_maintenance_date"] = str(date_value or "")
        self.save()

    def log_action(self, name: str, action: str, details: str, role: str = "USER"):
        """Write clean activity log entry to activity.log."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {role}: {name} | ACTION: {action} | {details}\n"
        try:
            os.makedirs(os.path.dirname(self.activity_log_file), exist_ok=True)
            with open(self.activity_log_file, "a", encoding="utf-8") as handle:
                handle.write(log_entry)
        except Exception as e:
            print(f"⚠️ Failed to write activity log: {e}")


db = Database()
