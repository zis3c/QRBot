import os
from dotenv import load_dotenv
from aiogram import Router, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
import strings
import json
from database import db
import psutil
import time
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext
from states import BroadcastStates, BanUserStates, UnbanUserStates, UnpenaltyUserStates

load_dotenv()

router = Router()

# Load Admin IDs from env
ADMIN_IDS = set()
raw_admins = os.getenv("ADMIN_IDS", "")
if raw_admins:
    try:
        ADMIN_IDS = {int(x.strip()) for x in raw_admins.split(",") if x.strip()}
    except ValueError:
        print("⚠️ Error parsing ADMIN_IDS")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

@router.message(Command("admin"))
async def admin_help(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply(strings.ADMIN_ONLY)
        return
    await message.reply(strings.ADMIN_HELP, parse_mode='Markdown')

@router.message(Command("ban"))
async def ban_user(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.reply(strings.ADMIN_ONLY)
        return

    args = message.text.split()
    if len(args) < 2:
        await state.set_state(BanUserStates.waiting_for_user_id)
        await message.reply(strings.PROMPT_BAN_USER_ID)
        return

    await process_ban_user(message, args[1])

@router.message(BanUserStates.waiting_for_user_id)
async def process_ban_user_id(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    await process_ban_user(message, message.text)

async def process_ban_user(message: types.Message, user_id_str: str):
    try:
        target_id = int(user_id_str)
        
        # Self-ban check
        if target_id == message.from_user.id:
            await message.reply("⛔ You cannot ban yourself!")
            return
            
        db.ban_user(target_id)
        await message.reply(strings.ADMIN_BAN_SUCCESS.format(user_id=target_id))
    except ValueError:
        await message.reply("⚠️ Invalid User ID.")

@router.message(Command("unban"))
async def unban_user(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.reply(strings.ADMIN_ONLY)
        return

    args = message.text.split()
    if len(args) < 2:
        await state.set_state(UnbanUserStates.waiting_for_user_id)
        await message.reply(strings.PROMPT_UNBAN_USER_ID)
        return

    await process_unban_user(message, args[1])

@router.message(UnbanUserStates.waiting_for_user_id)
async def process_unban_user_id(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    await process_unban_user(message, message.text)

async def process_unban_user(message: types.Message, user_id_str: str):
    try:
        target_id = int(user_id_str)
        db.unban_user(target_id)
        await message.reply(strings.ADMIN_UNBAN_SUCCESS.format(user_id=target_id))
    except ValueError:
        await message.reply("⚠️ Invalid User ID.")

START_TIME = time.time()

@router.message(Command("system"))
async def system_stats(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    cpu = psutil.cpu_percent()
    ram = psutil.virtual_memory().percent
    uptime = int(time.time() - START_TIME)
    
    msg = f"""
🖥️ *System Status*

CPU: {cpu}%
RAM: {ram}%
Uptime: {uptime}s
    """
    await message.reply(msg, parse_mode='Markdown')

@router.message(Command("broadcast"))
async def broadcast(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await state.set_state(BroadcastStates.waiting_for_message)
        await message.reply(strings.PROMPT_BROADCAST_MESSAGE)
        return
        
    await process_broadcast_text(message, text)

@router.message(BroadcastStates.waiting_for_message)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    await process_broadcast_text(message, message.text)

async def process_broadcast_text(message: types.Message, text: str):
    count = len(db.users)
    # Store text and current time in DB
    db.set_pending_broadcast(message.from_user.id, text, time.time())
    
    # Add confirm/cancel keyboard
    kb = [
        [KeyboardButton(text="Confirm"), KeyboardButton(text="Cancel")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
    
    await message.reply(strings.ADMIN_BROADCAST_CONFIRM.format(count=count, text=text), reply_markup=keyboard)

@router.message(F.text == "Confirm")
async def confirm_broadcast(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    user_id = message.from_user.id
    broadcast_data = db.get_pending_broadcast(user_id)
    
    if not broadcast_data:
        await message.reply(strings.ADMIN_NO_BROADCAST, reply_markup=ReplyKeyboardRemove())
        return
        
    text = broadcast_data['text']
    timestamp = broadcast_data['timestamp']
    
    # Check timeout (30 minutes = 1800 seconds)
    if time.time() - timestamp > 1800:
        db.clear_pending_broadcast(user_id)
        await message.reply("❌ Broadcast request expired.", reply_markup=ReplyKeyboardRemove())
        return
        
    db.clear_pending_broadcast(user_id) # Clear pending
    
    count = 0
    for uid in db.users:
        try:
            await message.bot.send_message(uid, f"📢 *Announcement*\n\n{text}", parse_mode='Markdown')
            count += 1
        except Exception:
            pass # User blocked bot
            
    await message.reply(strings.ADMIN_BROADCAST_SUCCESS.format(count=count), reply_markup=ReplyKeyboardRemove())

@router.message(F.text == "Cancel")
async def cancel_broadcast(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    user_id = message.from_user.id
    if db.get_pending_broadcast(user_id):
        db.clear_pending_broadcast(user_id)
        await message.reply(strings.ADMIN_BROADCAST_CANCEL, reply_markup=ReplyKeyboardRemove())
    else:
        await message.reply(strings.ADMIN_NO_BROADCAST, reply_markup=ReplyKeyboardRemove())

@router.message(Command("logs"))
async def get_logs(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    if os.path.exists("bot.log"):
        await message.reply_document(FSInputFile("bot.log"))
    else:
        await message.reply("⚠️ No log file found.")

@router.message(Command("stats"))
async def stats(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    total_users = len(db.users)
    
    now = time.time()
    active_today = sum(1 for u in db.users.values() if u.get('last_active', 0) > now - 86400)
    active_week = sum(1 for u in db.users.values() if u.get('last_active', 0) > now - 7*86400)
    
    perf = db.stats.get('performance', {'total_time': 0, 'count': 0})
    avg_time = (perf['total_time'] / perf['count']) if perf['count'] > 0 else 0
    
    errors = db.stats.get('errors', {})
    error_summary = "\n".join([f"- {k}: {v}" for k, v in errors.items()]) or "None"
    
    msg = f"""
📊 *Admin Dashboard*

👥 *User Stats*
Total: {total_users}
Active (24h): {active_today}
Active (7d): {active_week}

⚡ *Performance*
Avg Gen Time: {avg_time:.3f}s
Total Gens: {perf['count']}

⚠️ *Errors*
{error_summary}

🛠 *Commands*
/users - List all User IDs
/userban - List Banned Users
/command - View Command Usage
    """
    await message.reply(msg, parse_mode='Markdown')

@router.message(Command("users"))
async def list_users(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    if not db.users:
        await message.reply("👥 No users found.")
        return

    user_list = "\n".join([f"{i+1}. {uid}" for i, uid in enumerate(db.users.keys())])
    # Simple truncation to avoid hitting telegram limits (4096 chars)
    if len(user_list) > 4000:
        user_list = user_list[:4000] + "\n... (truncated)"
        
    await message.reply(f"👥 *User List* ({len(db.users)})\n\n{user_list}", parse_mode='Markdown')

@router.message(Command("userban"))
async def list_banned(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    if not db.banned:
        await message.reply("🚫 No banned users.")
        return

    banned_list = "\n".join([f"{i+1}. {uid}" for i, uid in enumerate(db.banned)])
    await message.reply(f"🚫 *Banned Users* ({len(db.banned)})\n\n{banned_list}", parse_mode='Markdown')

@router.message(Command("command"))
async def list_commands(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    msg = f"""
🔢 *Command Usage*
```
{json.dumps(db.stats, indent=2)}
```
    """
    await message.reply(msg, parse_mode='Markdown')

@router.message(Command("penalties"))
async def list_penalties(message: types.Message):
    if not is_admin(message.from_user.id): return
    
    penalties = []
    current_time = time.time()
    for uid, data in db.security.items():
        penalty_end = data.get('penalty_end', 0)
        if penalty_end > current_time:
            remaining = int(penalty_end - current_time)
            penalties.append(f"User: `{uid}` | Remaining: {remaining}s")
            
    if not penalties:
        await message.reply("✅ No active penalties.")
    else:
        await message.reply("⚠️ *Active Penalties*\n\n" + "\n".join(penalties), parse_mode='Markdown')

@router.message(Command("unpenalty"))
async def unpenalty_user(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    
    args = message.text.split()
    if len(args) < 2:
        await state.set_state(UnpenaltyUserStates.waiting_for_user_id)
        await message.reply(strings.PROMPT_UNPENALTY_USER_ID)
        return
        
    await process_unpenalty_user(message, args[1])

@router.message(UnpenaltyUserStates.waiting_for_user_id)
async def process_unpenalty_user_id(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    await process_unpenalty_user(message, message.text)

async def process_unpenalty_user(message: types.Message, user_id_str: str):
    target_id = user_id_str
    if target_id in db.security:
        db.security[target_id]['penalty_end'] = 0
        db.security[target_id]['violations'] = 0
        db.save()
        await message.reply(f"✅ Penalty removed for user `{target_id}`.", parse_mode='Markdown')
    else:
        await message.reply("⚠️ User not found in security database.")
