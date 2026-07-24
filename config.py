import threading
import os
import json

# --- DIRECTORY SETTINGS ---
USERS_DIR = "users_data"
USAGE_FILE = "usage_data.json" # Persistent storage for check counts
if not os.path.exists(USERS_DIR):
    os.makedirs(USERS_DIR)

# --- TELEGRAM BOT CONFIG ---
TOKEN = "8687803445:AAHihPu5K4SdWY58nZyPlRsgUL5OKOuiDy0"
ADMIN_ID = 7201751136

# --- GLOBAL SHARED STATE ---
user_stats = {} 
FREE_MODE = False  # Default to Paid only
file_lock = threading.Lock()

def get_user_folder(user_id):
    path = os.path.join(USERS_DIR, str(user_id))
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def get_user_paths(user_id):
    folder = get_user_folder(user_id)
    return {
        "combo": os.path.join(folder, "list.txt"),
        "keywords": os.path.join(folder, "keywords.txt"),
        "hits": os.path.join(folder, "keywords_result.txt"),
        "hits_no_kw": os.path.join(folder, "good_logins.txt"),
        "debug": os.path.join(folder, "debug.jsonl")
    }

THREADS = 15