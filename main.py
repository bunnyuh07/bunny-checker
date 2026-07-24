import threading
import os
import time
import json
import telebot
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from telebot import types

from config import *
import checker

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
START_TIME = datetime.now()
AUTHORIZED_USERS = [ADMIN_ID]

# --- USAGE PERSISTENCE ---

def load_usage():
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_usage(data):
    with open(USAGE_FILE, "w") as f:
        json.dump(data, f)

def get_user_usage(uid):
    usage = load_usage()
    return usage.get(str(uid), 0)

def increment_usage(uid):
    usage = load_usage()
    uid_str = str(uid)
    usage[uid_str] = usage.get(uid_str, 0) + 1
    save_usage(usage)

# --- AUTHORIZATION SYSTEM ---

def is_authorized(uid):
    return uid in AUTHORIZED_USERS

# --- RESET TASK ---

def reset_daily_limits():
    """Background task to reset limits every 24 hours and notify users."""
    while True:
        # Wait 24 hours
        time.sleep(86400) 
        
        # Clear the usage file
        save_usage({})
        
        # Notify all users who have folders in users_data
        if os.path.exists(USERS_DIR):
            user_ids = [d for d in os.listdir(USERS_DIR) if os.path.isdir(os.path.join(USERS_DIR, d))]
            for uid in user_ids:
                try:
                    bot.send_message(uid, "🎁 <b>Your free plan has been reset!</b>\nYou have <b>4 free checks</b> available for the next 24 hours. Use /check to start!")
                except Exception:
                    continue

# Start the background reset thread
threading.Thread(target=reset_daily_limits, daemon=True).start()

# --- UTILS ---

def get_uptime():
    delta = datetime.now() - START_TIME
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"

def get_total_users():
    if not os.path.exists(USERS_DIR): return 0
    return len([d for d in os.listdir(USERS_DIR) if os.path.isdir(os.path.join(USERS_DIR, d))])

def get_progress_bar(percent):
    bar_length = 15
    filled = int(bar_length * percent / 100)
    return '🟢' * filled + '⚪' * (bar_length - filled)

def generate_status_text(uid):
    with file_lock:
        if uid not in user_stats: return "❌ Session expired."
        s = user_stats[uid]
        elapsed = time.time() - s["start_time"]
        percent = (s["checked"] / s["total"] * 100) if s["total"] > 0 else 0
        cpm = int((s["checked"] / elapsed) * 60) if elapsed > 0 else 0
        time_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))

        kw_list = sorted(s["detailed_hits"].items(), key=lambda x: x[1], reverse=True)
        top_kws = "\n".join([f"• {k}: {v}" for k, v in kw_list[:4]])
        more_kws = f"\n+ {len(kw_list) - 4} more services" if len(kw_list) > 4 else ""
        
        status_msg = "Checking..." if not s.get("stop_flag") else "Stopped 🛑"
        if percent >= 100: status_msg = "Completed ✅"

        return (
            f"📊 <b>Keyword Scan Progress</b>\n"
            f"<code>{get_progress_bar(percent)}</code> {percent:.1f}%\n"
            f"📈 <code>{s['checked']}/{s['total']} | CPM: {cpm}</code>\n"
            f"🕒 <code>{time_str} | {status_msg}</code>\n\n"
            f"🔥 <b>Hits Found: {s['keywords_good']}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{top_kws if top_kws else 'Waiting for hits...'}{more_kws}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>Valid:</b> <code>{s['good'] + s['keywords_good']}</code>\n"
            f"🎯 <b>Hits (KW):</b> <code>{s['keywords_good']}</code>\n"
            f"🔴 <b>Bad:</b> <code>{s['invalid']}</code> | 🟠 <b>Retry:</b> <code>{s['retries']}</code>"
        )

# --- ADMIN COMMANDS ---

@bot.message_handler(commands=['free'])
def enable_free_mode(message):
    global FREE_MODE
    if message.from_user.id != ADMIN_ID: return
    FREE_MODE = True
    bot.reply_to(message, "🔓 <b>Bot is now FREE for all users</b> (4 checks limit/24h).")

@bot.message_handler(commands=['paid'])
def enable_paid_mode(message):
    global FREE_MODE
    if message.from_user.id != ADMIN_ID: return
    FREE_MODE = False
    bot.reply_to(message, "🔒 <b>Bot is now PAID only.</b> Access restricted to authorized users.")

@bot.message_handler(commands=['add'])
def add_user(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        new_id = int(message.text.split()[1])
        if new_id not in AUTHORIZED_USERS:
            AUTHORIZED_USERS.append(new_id)
            bot.reply_to(message, f"✅ User <code>{new_id}</code> added to authorized list.")
    except: bot.reply_to(message, "⚠️ Usage: <code>/add [user_id]</code>")

@bot.message_handler(commands=['remove'])
def remove_user(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        target_id = int(message.text.split()[1])
        if target_id in AUTHORIZED_USERS:
            AUTHORIZED_USERS.remove(target_id)
            bot.reply_to(message, f"🗑 User <code>{target_id}</code> removed.")
    except: bot.reply_to(message, "⚠️ Usage: <code>/remove [user_id]</code>")

@bot.message_handler(commands=['list'])
def list_users(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    if not AUTHORIZED_USERS:
        return bot.reply_to(message, "📜 <b>The authorized list is empty.</b>")
    
    msg_text = "📋 <b>Authorized Users:</b>\n━━━━━━━━━━━━━━━━━━━━\n"
    for uid in AUTHORIZED_USERS:
        try:
            # Attempt to get user info to retrieve the username
            chat = bot.get_chat(uid)
            username = f"@{chat.username}" if chat.username else "No Username"
            msg_text += f"👤 <code>{uid}</code> | {username}\n"
        except Exception:
            # Fallback if the bot cannot access the user's info
            msg_text += f"👤 <code>{uid}</code> | (Info Hidden)\n"
            
    bot.send_message(message.chat.id, msg_text)

# --- USER COMMANDS ---

@bot.message_handler(commands=['start'])
def welcome(message):
    uid = message.from_user.id
    uptime = get_uptime()
    total_users = get_total_users()
    auth_status = "✅ Authorized" if is_authorized(uid) else "❌ Free Plan"
    
    welcome_text = (
        "🐰 <b>Welcome to Bunny Checker Version 0.1</b> 🐰\n\n"
        "🤖 <b>Your Microsoft Keyword Scanner</b>\n\n"
        "🛡 <b>Bot Health:</b>\n"
        "🟢 <b>Status:</b> Online\n"
        f"🕒 <b>Uptime:</b> {uptime}\n"
        f"👤 <b>Total Users:</b> {total_users}\n"
        f"🔑 <b>Your Rank:</b> {auth_status}\n\n"
        "💎 <b>Features:</b>\n"
        f"🔹 Multi-threaded ({THREADS} threads)\n"
        "🔹 Keyword Extraction & Validation\n"
        "🔹 Supports up to 70k lines\n\n"
        "📋 <b>Commands:</b>\n"
        "/check – Start a new scan 🚀\n"
        "/cancel – Cancel scan ❌\n\n"
    )
    
    if uid == ADMIN_ID:
        welcome_text += (
            "🛠 <b>Admin Controls:</b>\n"
            "<code>/add [id]</code> – Authorize user\n"
            "<code>/remove [id]</code> – Revoke access\n"
            "<code>/paid </code> – Paid Plans Only\n"
            "<code>/free [id]</code> – Free access To All\n"
            "<code>/list</code> – View authorized users\n\n"
        )
        
    welcome_text += (
        "👑 <b>Dev:</b> @ce_q3\n"
        "🤖 <b>Channel:</b> @Hacking_morocco"
    )
    try:
        with open("logo.png", "rb") as photo:
            bot.send_photo(message.chat.id, photo, caption=welcome_text)
    except: bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['check'])
def start_check(message):
    uid = message.chat.id
    
    # 1. Check if bot is in Paid Mode and user is NOT authorized
    if not FREE_MODE and not is_authorized(uid):
        unauth_msg = (
            "⚠️ <b>Access Denied</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "This bot is currently for <b>paid members only</b>.\n\n"
            "To purchase a subscription, contact:\n"
            "👑 <b>Admin:</b> @ce_q3"
        )
        return bot.reply_to(message, unauth_msg)

    # 2. If user is NOT authorized, check their 24h limit
    if not is_authorized(uid):
        usage_count = get_user_usage(uid)
        if usage_count >= 4:
            limit_msg = (
                "⚠️ <b>Limit Reached</b>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "You finished your free plan. You need to talk with admin @ce_q3 to buy a sub or wait 24 hr for the reset free plan."
            )
            return bot.reply_to(message, limit_msg)
        
        # Increment usage here so it counts as 1 of their 4 checks
        increment_usage(uid)

    get_user_folder(uid)
    user_stats[uid] = {"api_type": 1, "stop_flag": False}
    text = "🎯 <b>Keyword Scan Initialized.</b>\nPlease send your <b>Keywords</b> (Text or .txt):"
    bot.send_message(uid, text)
    bot.register_next_step_handler(message, process_keywords_input)

@bot.message_handler(commands=['cancel'])
def cancel_scan(message):
    uid = message.chat.id
    if uid in user_stats:
        with file_lock:
            user_stats[uid]["stop_flag"] = True
        bot.reply_to(message, "🛑 <b>Scan cancellation requested.</b>")
    else:
        bot.reply_to(message, "❌ No active scan found.")

# --- ENGINE ---

def run_checker_task(uid, accounts, paths):
    with file_lock:
        user_stats[uid].update({
            "invalid": 0, "good": 0, "keywords_good": 0, "total": len(accounts),
            "checked": 0, "stop_flag": False, "start_time": time.time(),
            "detailed_hits": {}, "retries": 0, "errors": 0
        })

    board = bot.send_message(uid, "⏳ <b>Initializing Status Board...</b>")

    def status_updater(msg_obj):
        while uid in user_stats:
            time.sleep(4)
            if user_stats[uid]["checked"] >= user_stats[uid]["total"] or user_stats[uid].get("stop_flag"): break
            try: bot.edit_message_text(generate_status_text(uid), uid, msg_obj.message_id)
            except: continue
        try: bot.edit_message_text(generate_status_text(uid), uid, msg_obj.message_id)
        except: pass

    def thread_worker():
        threading.Thread(target=status_updater, args=(board,), daemon=True).start()
        with ThreadPoolExecutor(max_workers=THREADS) as executor:
            with open(paths["keywords"], 'r') as f: 
                kws = [l.strip() for l in f if l.strip()]
            for acc in accounts:
                if user_stats[uid].get("stop_flag"): break
                executor.submit(checker.check_account, acc, kws, uid, paths)
        
        bot.send_message(uid, "🏁 <b>Process Ended.</b> Sending results...")
        for key in ["hits", "hits_no_kw"]:
            if os.path.exists(paths[key]) and os.path.getsize(paths[key]) > 0:
                with open(paths[key], 'rb') as f: bot.send_document(uid, f)

    threading.Thread(target=thread_worker, daemon=True).start()

# --- INPUT PROCESSING ---

def process_keywords_input(message):
    uid = message.chat.id
    paths = get_user_paths(uid)
    if message.text == '/cancel': return
    try:
        if message.content_type == 'document':
            data = bot.download_file(bot.get_file(message.document.file_id).file_path)
            kws = [k.strip() for k in data.decode('utf-8', 'ignore').splitlines() if k.strip()]
        else:
            kws = [k.strip() for line in message.text.split('\n') for k in line.split(',') if k.strip()]
        with open(paths["keywords"], "w", encoding="utf-8") as f: f.write("\n".join(kws))
        bot.reply_to(message, "✅ Keywords Saved. Now upload your <b>Combo (.txt)</b>:")
        bot.register_next_step_handler(message, handle_combo)
    except: bot.reply_to(message, "⚠️ Setup Error.")

def handle_combo(message):
    uid = message.chat.id
    paths = get_user_paths(uid)
    if message.text == '/cancel': return
    if message.content_type == 'document' and message.document.file_name.endswith('.txt'):
        data = bot.download_file(bot.get_file(message.document.file_id).file_path)
        lines = [l.strip() for l in data.decode('utf-8', 'ignore').splitlines() if l.strip()][:70000]
        with open(paths["combo"], 'w', encoding='utf-8') as f: f.write("\n".join(lines))
        for key in ["hits", "hits_no_kw"]:
            if os.path.exists(paths[key]): os.remove(paths[key])
        bot.reply_to(message, f"⚡ <b>Started check for {len(lines)} accounts.</b>")
        run_checker_task(uid, lines, paths)
    else: bot.reply_to(message, "⚠️ Please upload a valid .txt combo file.")

if __name__ == "__main__":
    print("Bunny Checker Running...")
    bot.infinity_polling(timeout=90, long_polling_timeout=5)