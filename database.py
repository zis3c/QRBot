import json
import os
from typing import Set, Dict, Any

DB_FILE = "bot_data.json"

class Database:
    def __init__(self):
        self.filename = DB_FILE
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
        self._dirty = False
        self.load()

    def load(self):
        if not os.path.exists(self.filename):
            return
        try:
            with open(self.filename, 'r') as f:
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
            'user_prefs': self.user_prefs
        }
        
        # Atomic write: write to temp file then rename
        temp_filename = self.filename + ".tmp"
        try:
            with open(temp_filename, 'w') as f:
                json.dump(data, f, indent=4)
            
            # Atomic rename
            if os.path.exists(self.filename):
                os.remove(self.filename)
            os.rename(temp_filename, self.filename)
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

# Global instance
db = Database()
