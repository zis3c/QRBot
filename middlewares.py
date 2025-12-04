import time
import logging
from typing import Any, Awaitable, Callable, Dict, Set
from aiogram import BaseMiddleware
from aiogram.types import Message
import strings
from database import db
from aiogram.fsm.context import FSMContext
from admin import is_admin
import notifications

logger = logging.getLogger(__name__)

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit_light: float = 2.0, limit_heavy: float = 10.0):
        self.limit_light = limit_light
        self.limit_heavy = limit_heavy
        self.user_timeouts: Dict[int, float] = {}
        # Violations and penalties are now handled by db.security

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        current_time = time.time()
        
        # 0. Track User & Stats
        db.update_user_activity(user_id)
        command = event.text.split()[0] if event.text else "unknown"
        if event.photo: command = "photo"
        
        # Define valid commands to track
        VALID_COMMANDS = {
            "/start", "/help", "/about",
            "/textqr", "/urlqr", "/wifiqr", "/vcardqr", "/encodeqr", "/readerqr", "/geoqr",
            "/admin", "/ban", "/unban", "/system", "/stats", "/broadcast", "/logs", 
            "/users", "/userban", "/command", "/cancel", "/confirm", "/penalties", "/unpenalty"
        }
        
        if command in VALID_COMMANDS:
            db.increment_stat(command)
        
        # Log activity
        logger.info(f"User:{user_id} | Action:{command}")

        # 0.5 Admin Immunity
        if is_admin(user_id):
            return await handler(event, data)

        # 1. Check Ban
        if db.is_banned(user_id):
            return 

        # 2. Check Penalty (Persistent)
        security_data = db.get_user_security(user_id)
        penalty_end = security_data.get('penalty_end', 0)
        
        if current_time < penalty_end:
            # Still penalized
            return

        # 2.5 Check FSM State (Skip throttling if in flow)
        state: FSMContext = data.get('state')
        if state:
            current_state = await state.get_state()
            if current_state is not None:
                # User is in a conversational flow, skip throttling
                return await handler(event, data)

        # 3. Determine Limit
        # Group all QR commands together for security
        text = event.text or ""
        is_heavy = False
        
        # Treat all QR generation commands as heavy ONLY if they have arguments (actual generation)
        # or if it's a photo upload
        if event.photo:
            is_heavy = True
        elif text.startswith(('/wifiqr', '/readerqr', '/encodeqr', '/textqr', '/urlqr', '/vcardqr', '/geoqr')):
            # Check if command has arguments
            if len(text.split()) > 1:
                is_heavy = True
            
        limit = self.limit_heavy if is_heavy else self.limit_light
        
        # 4. Check Throttling
        if user_id in self.user_timeouts:
            last_time = self.user_timeouts[user_id]
            if current_time - last_time < limit:
                # Violation
                violations = security_data.get('violations', 0) + 1
                
                # Escalating Penalties
                # 1st-3rd violation: Warning (handled by cooldown msg)
                # 4th: 1 min
                # 5th: 5 min
                # 6th: 30 min
                # 7th: 2 hours
                # 8th+: 24 hours
                
                penalty_duration = 0
                if violations >= 8:
                    penalty_duration = 24 * 3600
                elif violations == 7:
                    penalty_duration = 2 * 3600
                elif violations == 6:
                    penalty_duration = 30 * 60
                elif violations == 5:
                    penalty_duration = 5 * 60
                elif violations >= 4:
                    penalty_duration = 60
                
                # Save violation count
                db.update_user_security(user_id, violations=violations)

                if penalty_duration > 0:
                    new_penalty_end = current_time + penalty_duration
                    db.update_user_security(user_id, penalty_end=new_penalty_end)
                    
                    # Notify User
                    await event.reply(f"⛔ You are sending commands too fast! You have been blocked for {penalty_duration} seconds.")
                    
                    # Alert Admin if high violation count
                    if violations >= 6:
                        if notifications.notify:
                            await notifications.notify.send_alert(
                                'WARNING', 
                                f"User: {user_id}\nViolations: {violations}\nPenalty: {penalty_duration}s",
                                key=f"violation_{user_id}"
                            )
                    return

                wait_time = int(limit - (current_time - last_time)) + 1
                await event.reply(strings.ERROR_COOLDOWN.format(seconds=wait_time))
                return 
        
        # Update last time
        self.user_timeouts[user_id] = current_time
        
        # Proceed with handler
        return await handler(event, data)

