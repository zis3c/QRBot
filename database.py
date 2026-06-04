import json
import os
from typing import Set, Dict, Any, Optional

DEFAULT_DB_FILE = "bot_data.json"
DEFAULT_RUNTIME_LOG_FILE = "bot.log"
DB_FILE_ENV = "QRBOT_DB_FILE"
DATA_DIR_ENV = "QRBOT_DATA_DIR"
ACTIVITY_LOG_ENV = "QRBOT_ACTIVITY_LOG_FILE"
RUNTIME_LOG_ENV = "QRBOT_RUNTIME_LOG_FILE"


def _resolve_data_dir() -> str:
    """Resolve the preferred persistent data directory."""
    data_dir = os.getenv(DATA_DIR_ENV)
    if data_dir:
        return os.path.abspath(data_dir)

    if os.path.isdir("/var/data"):
        return "/var/data"

    return os.path.dirname(os.path.abspath(__file__))


def _can_write_to_dir(path: str) -> bool:
    """Return True when the directory exists and current process can write to it."""
    return os.path.isdir(path) and os.access(path, os.W_OK)


def _resolve_writable_file_path(env_name: str, default_filename: str, base_dir: Optional[str] = None) -> str:
    """Resolve file path from env, but fall back if parent directory is unavailable."""
    env_file = os.getenv(env_name)
    if env_file:
        candidate = os.path.abspath(env_file)
        parent_dir = os.path.dirname(candidate) or "."
        if _can_write_to_dir(parent_dir):
            return candidate
        print(f"Warning: {env_name} directory not writable: {parent_dir}. Falling back to local data directory.")

    root_dir = os.path.abspath(base_dir) if base_dir else _resolve_data_dir()
    return os.path.join(root_dir, default_filename)


def _resolve_db_path() -> str:
    """Resolve database path with persistent-storage-first strategy."""
    env_file = os.getenv(DB_FILE_ENV)
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
        self.users: Dict[int, Dict[str, float]] = {} # user_id: {joined_at, last_active}
        self.banned: Set[int] = set()
        self.stats: Dict[str, Any] = {
            'commands': {},
            'performance': {'total_time': 0.0, 'count': 0},
            'errors': {}
        }
        self.pending_broadcasts: Dict[str, Any] = {} # admin_id: (text, timestamp)
        self.security: Dict[str, Any] = {} # user_id: {violations: int, penalty_end: float}
        self.user_prefs: Dict[str, Any] = {} # user_id: {style_template: str, custom_style: dict}
        self.meta: Dict[str, Any] = {"last_maintenance_date": ""}
        self._dirty = False
        self.load()

    def load(self):
        if not os.path.exists(self.filename):
            return
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Migrate users list to dict if necessary
                raw_users = data.get('users', [])
                if isinstance(raw_users, list):
                    self.users = {int(uid): {'joined_at': 0, 'last_active': 0} for uid in raw_users}
                else:
                    self.users = {int(k): v for k, v in raw_users.items()}
                    
                self.banned = set(data.get('banned', []))
                
                # Migrate stats if necessary
                raw_stats = data.get('stats', {})
                if 'commands' not in raw_stats:
                    self.stats = {
                        'commands': raw_stats,
                        'performance': {'total_time': 0.0, 'count': 0},
                        'errors': {}
                    }
                else:
                    self.stats = raw_stats

                # Load pending broadcasts
                self.pending_broadcasts = data.get('pending_broadcasts', {})
                # Load security data
                self.security = data.get('security', {})
                # Load user prefs
                self.user_prefs = data.get('user_prefs', {})
                # Load metadata
                raw_meta = data.get('meta', {})
                if isinstance(raw_meta, dict):
                    self.meta = {
                        "last_maintenance_date": str(raw_meta.get("last_maintenance_date", "") or "")
                    }
        except Exception as e:
            print(f"⚠️ Error loading database: {e}")

    def save(self):
        """Mark data as dirty. Actual write happens in flush()."""
        self._dirty = True

    def flush(self):
        """Write data to disk if dirty."""
        if not self._dirty:
            return
            
        data = {
            'users': self.users,
            'banned': list(self.banned),
            'stats': self.stats,
            'pending_broadcasts': self.pending_broadcasts,
            'security': self.security,
            'user_prefs': self.user_prefs,
            'meta': self.meta
        }
        
        # Atomic write: write to temp file then rename
        temp_filename = self.filename + ".tmp"
        try:
            db_dir = os.path.dirname(self.filename)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

            with open(temp_filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

            # Atomic replace (safe on both Windows and Unix).
            os.replace(temp_filename, self.filename)
            self._dirty = False
        except Exception as e:
            print(f"⚠️ Error saving database: {e}")
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    def add_user(self, user_id: int):
        import time
        if user_id not in self.users:
            self.users[user_id] = {
                'joined_at': time.time(),
                'last_active': time.time()
            }
            self.save()
            # Persist new user IDs immediately so they survive restarts.
            self.flush()
            
    def update_user_activity(self, user_id: int):
        import time
        if user_id in self.users:
            self.users[user_id]['last_active'] = time.time()
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
        if 'commands' not in self.stats:
            self.stats['commands'] = {}
        self.stats['commands'][command] = self.stats['commands'].get(command, 0) + 1
        self.save()
        
    def record_performance(self, duration: float):
        if 'performance' not in self.stats:
            self.stats['performance'] = {'total_time': 0.0, 'count': 0}
        
        self.stats['performance']['total_time'] += duration
        self.stats['performance']['count'] += 1
        self.save()
        
    def record_error(self, error_type: str):
        if 'errors' not in self.stats:
            self.stats['errors'] = {}
        self.stats['errors'][error_type] = self.stats['errors'].get(error_type, 0) + 1
        self.save()

    def reset_stats(self):
        self.stats = {
            'commands': {},
            'performance': {'total_time': 0.0, 'count': 0},
            'errors': {}
        }
        self.save()
        
    def set_pending_broadcast(self, admin_id: int, text: str, timestamp: float):
        self.pending_broadcasts[str(admin_id)] = {'text': text, 'timestamp': timestamp}
        self.save()
        
    def get_pending_broadcast(self, admin_id: int):
        return self.pending_broadcasts.get(str(admin_id))
        
    def clear_pending_broadcast(self, admin_id: int):
        if str(admin_id) in self.pending_broadcasts:
            del self.pending_broadcasts[str(admin_id)]
            self.save()

    def get_user_security(self, user_id: int) -> Dict[str, Any]:
        return self.security.get(str(user_id), {'violations': 0, 'penalty_end': 0})

    def update_user_security(self, user_id: int, violations: int = None, penalty_end: float = None):
        uid = str(user_id)
        if uid not in self.security:
            self.security[uid] = {'violations': 0, 'penalty_end': 0}
        
        if violations is not None:
            self.security[uid]['violations'] = violations
        if penalty_end is not None:
            self.security[uid]['penalty_end'] = penalty_end
            
        self.save()

    def set_user_style(self, user_id: int, template_name: str):
        uid = str(user_id)
        if uid not in self.user_prefs:
            self.user_prefs[uid] = {}
        self.user_prefs[uid]['style_template'] = template_name
        self.save()

    def get_user_style(self, user_id: int) -> str:
        uid = str(user_id)
        return self.user_prefs.get(uid, {}).get('style_template', 'classic')
    
    def set_user_qr_style(self, user_id: int, fg_color: tuple, bg_color: tuple):
        """Save user's custom QR color settings."""
        uid = str(user_id)
        if uid not in self.user_prefs:
            self.user_prefs[uid] = {}
        
        self.user_prefs[uid]['custom_qr'] = {
            'fg_color': list(fg_color),  # (r, g, b)
            'bg_color': list(bg_color)   # (r, g, b)
        }
        self.save()
    
    def get_user_qr_style(self, user_id: int):
        """Get user's custom QR color settings."""
        uid = str(user_id)
        if uid in self.user_prefs:
            custom = self.user_prefs[uid].get('custom_qr')
            if custom:
                return (tuple(custom['fg_color']), tuple(custom['bg_color']))
        return None
    
    def clear_user_qr_style(self, user_id: int):
        """Clear user's custom QR settings (reset to default)."""
        uid = str(user_id)
        if uid in self.user_prefs:
            self.user_prefs[uid].pop('custom_qr', None)
            self.save()

    def get_last_maintenance_date(self) -> str:
        return str(self.meta.get("last_maintenance_date", "") or "")

    def set_last_maintenance_date(self, date_value: str):
        self.meta["last_maintenance_date"] = str(date_value or "")
        self.save()
        # Persist immediately to survive sudden restarts.
        self.flush()

    # --- ACTIVITY LOGGING (FILE BASED) ---
    def log_action(self, name: str, action: str, details: str, role: str = "USER"):
        """Writes a clean activity log entry to activity.log.
        
        Format: [YYYY-MM-DD HH:MM:SS] USER: Name (id) | ACTION: action | details
        """
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {role}: {name} | ACTION: {action} | {details}\n"
        try:
            os.makedirs(os.path.dirname(self.activity_log_file), exist_ok=True)
            with open(self.activity_log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception as e:
            print(f"⚠️ Failed to write activity log: {e}")

# Global instance
db = Database()
