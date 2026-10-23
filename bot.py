import sys
import asyncio
import json
import os
import re
import time
from datetime import datetime, timedelta
from urllib import parse, request as urllib_request
from urllib.error import HTTPError
import base64
import logging

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import Client, filters, ContinuePropagation
from pyrogram.enums import ParseMode, ChatMemberStatus, MessageEntityType
from pyrogram.types import (
    ChatJoinRequest,
    ChatMemberUpdated,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= HELPER FUNCTIONS =================
def _validate_pyrogram_session_string(session_string):
    if not session_string:
        return ""
    normalized = session_string.replace("-", "+").replace("_", "/")
    normalized += "=" * (-len(normalized) % 4)
    try:
        decoded = base64.b64decode(normalized)
    except Exception:
        return session_string
    return session_string

def _clean_secret(name, default=""):
    value = os.getenv(name, default)
    return value.strip().strip("\"'")

# ================= LOAD ENV =================
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

# ================= CONFIG =================
API_ID = int(os.getenv("API_ID", ""))
API_HASH = _clean_secret("API_HASH", "")
BOT_TOKEN = _clean_secret("BOT_TOKEN", "")
STRING_SESSION = _validate_pyrogram_session_string(_clean_secret("STRING_SESSION", ""))
MONGO_URI = _clean_secret("MONGO_URI", "")

ADMIN_CHAT_IDS_STR = os.getenv("ADMIN_CHAT_ID", "")
ADMIN_CHAT_IDS = [int(x.strip()) for x in ADMIN_CHAT_IDS_STR.split(",") if x.strip().strip("-").isdigit()]
if not ADMIN_CHAT_IDS:
    ADMIN_CHAT_IDS = []
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip().strip("-").isdigit()]
if not ADMIN_IDS:
    ADMIN_IDS = []

CHANNEL_ID = int(os.getenv("CHANNEL_ID", ""))
TEMPLATE_CHANNEL_ID = int(os.getenv("TEMPLATE_CHANNEL_ID", ""))

EMOJI_VIP = os.getenv("EMOJI_VIP", "")
EMOJI_SURESHOT = os.getenv("EMOJI_SURESHOT", "")
EMOJI_NUMBERSHOT = os.getenv("EMOJI_NUMBERSHOT", "")
EMOJI_HACK = os.getenv("EMOJI_HACK", "")
EMOJI_CHALLENGE = os.getenv("EMOJI_CHALLENGE", "")

TEXT_VIP = "VIP Session"
TEXT_SURESHOT = "SureShot"
TEXT_NUMBERSHOT = "Number Shot"
TEXT_HACK = "Hack APK"
TEXT_CHALLENGE = "2k to 55k Compounding"

LINK_VIP = ""
LINK_SURESHOT = ""
LINK_NUMBERSHOT = ""
LINK_CHALLENGE = ""

# ================= INIT CLIENTS =================
app = Client(
    "advanced_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

if STRING_SESSION:
    user_app = Client("user", api_id=API_ID, api_hash=API_HASH, session_string=STRING_SESSION)
else:
    user_app = None

client_mongo = AsyncIOMotorClient(MONGO_URI)
db = client_mongo["tg_autoaccept"]
users_col = None
settings_col = None
admin_messages_col = None

async def init_db(bot_username):
    global users_col, settings_col, admin_messages_col
    users_col = db[f"{bot_username}_users"]
    settings_col = db[f"{bot_username}_settings"]
    admin_messages_col = db[f"{bot_username}_admin_messages"]
    
    try:
        users_col.create_index("user_id", unique=True)
        admin_messages_col.create_index("admin_message_id", unique=True)
    except Exception as e:
        logger.warning(f"Failed to create database indexes: {e}")
        
    logger.info(f"Initialized database collections: {bot_username}_users, {bot_username}_settings, {bot_username}_admin_messages")

# ================= SCHEDULER =================
scheduler = AsyncIOScheduler()

# Per-user lock to prevent double-processing when a user clicks the same button multiple times
_active_callback_users = set()
_reply_markup_cache = {}
_user_state_cache = {}
_user_language_cache = {}

async def send_followup_message(user_id, step):
    state = await get_user_state(user_id)
    # Only send follow-ups if they haven't submitted recharge proof or reached LIVE_CHAT yet
    if state not in ("WAITING_FOR_DEPOSIT_PROOF", "LIVE_CHAT"):
        try:
            lang = await get_user_language(user_id)
            if lang == "hi":
                if step == 1:
                    text = "भाई, तुम कहाँ गायब हो गए? 🤔"
                elif step == 2:
                    text = "भाई, मुझे अनदेखा मत करो। तुमने पहले ही पहला कदम उठा लिया है। बस कुछ और कदम, और तुम हर दिन 10,000 रुपये से अधिक की अपनी पहली कमाई देखोगे। 💰📈"
                elif step == 3:
                    text = "यदि आपको अभी भी कोई संदेह है, तो मेरा मुख्य वीडियो देखें। यह चैनल पर पिन किया गया है और यहाँ चैट में भी उपलब्ध है। यह वीडियो आपके सभी सवालों के जवाब देगा। 🎥👇"
                    await update_user_state(user_id, "LIVE_CHAT")
            else:
                if step == 1:
                    text = "Bro, why did you disappear? 🤔"
                elif step == 2:
                    text = "Bro, don't ignore me. You've already taken the first step. Take a few more, and you'll see your first earnings of over 10,000 INR a day. 💰📈"
                elif step == 3:
                    text = "If you’re still having doubts, watch my main video. It’s pinned to the channel and is also available here in the chat. The video will answer all your questions. 🎥👇"
                    await update_user_state(user_id, "LIVE_CHAT")
                
            await app.send_message(chat_id=user_id, text=text)
            logger.info(f"Sent inactivity follow-up {step} to user {user_id}")
        except Exception as e:
            logger.warning(f"Failed to send follow-up {step} to user {user_id}: {e}")

def schedule_followups(user_id):
    now = datetime.now()
    scheduler.add_job(
        send_followup_message,
        "date",
        run_date=now + timedelta(minutes=10),
        args=[user_id, 1],
        id=f"followup_{user_id}_10m",
        replace_existing=True
    )
    scheduler.add_job(
        send_followup_message,
        "date",
        run_date=now + timedelta(minutes=30),
        args=[user_id, 2],
        id=f"followup_{user_id}_30m",
        replace_existing=True
    )
    scheduler.add_job(
        send_followup_message,
        "date",
        run_date=now + timedelta(minutes=60),
        args=[user_id, 3],
        id=f"followup_{user_id}_60m",
        replace_existing=True
    )

def cancel_user_jobs(user_id):
    for suffix in ("_10m", "_30m", "_60m"):
        try:
            scheduler.remove_job(f"followup_{user_id}{suffix}")
        except Exception:
            pass

async def check_and_schedule_pending_transitions():
    logger.info("Scanning database for users in WAITING_FOR_YES or early states...")
    now = time.time()
    try:
        users = users_col.find({"current_state": {"$in": ["NEW_USER", "WAITING_FOR_YES", "COMPLETED", "WAITING_FOR_REGISTRATION"]}})
        count = 0
        async for doc in users:
            user_id = doc["user_id"]
            join_timestamp = doc.get("join_timestamp", now)
            elapsed = now - join_timestamp
            
            # Reschedule remaining jobs:
            # 10m job
            if elapsed < 600:
                scheduler.add_job(
                    send_followup_message,
                    "date",
                    run_date=datetime.now() + timedelta(seconds=(600 - elapsed)),
                    args=[user_id, 1],
                    id=f"followup_{user_id}_10m",
                    replace_existing=True
                )
            # 30m job
            if elapsed < 1800:
                scheduler.add_job(
                    send_followup_message,
                    "date",
                    run_date=datetime.now() + timedelta(seconds=(1800 - elapsed)),
                    args=[user_id, 2],
                    id=f"followup_{user_id}_30m",
                    replace_existing=True
                )
            # 60m job
            if elapsed < 3600:
                scheduler.add_job(
                    send_followup_message,
                    "date",
                    run_date=datetime.now() + timedelta(seconds=(3600 - elapsed)),
                    args=[user_id, 3],
                    id=f"followup_{user_id}_60m",
                    replace_existing=True
                )
                count += 1
            else:
                logger.info(f"User {user_id} exceeded timeout on startup. Transitioning to LIVE_CHAT.")
                await update_user_state(user_id, "LIVE_CHAT")
        logger.info(f"Scan complete. Rescheduled {count} pending follow-up sets.")
    except Exception as e:
        logger.error(f"Failed during check_and_schedule_pending_transitions: {e}")

# ================= DATABASE HELPERS =================
async def add_user(user_obj, status="pending", state=None):
    update_doc = {"status": status}
    if state is not None:
        update_doc["current_state"] = state
        _user_state_cache[user_obj.id] = state
        update_doc["join_timestamp"] = time.time()
        update_doc["registered_player_id"] = None

    await users_col.update_one(
        {"user_id": user_obj.id},
        {
            "$setOnInsert": {
                "user_id": user_obj.id,
                "name": user_obj.first_name or "",
                "username": user_obj.username or "",
                "interaction_history": []
            },
            "$set": update_doc,
        },
        upsert=True,
    )

async def get_user_state(user_id):
    if user_id in _user_state_cache:
        return _user_state_cache[user_id]
    doc = await users_col.find_one({"user_id": user_id}, {"current_state": 1})
    state = doc.get("current_state") if doc else None
    _user_state_cache[user_id] = state
    return state

async def update_user_state(user_id, state):
    _user_state_cache[user_id] = state
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"current_state": state}},
        upsert=True
    )

async def get_user_language(user_id):
    if user_id in _user_language_cache:
        return _user_language_cache[user_id]
    doc = await users_col.find_one({"user_id": user_id}, {"language": 1})
    lang = "en"
    if doc and "language" in doc:
        lang = doc["language"]
    _user_language_cache[user_id] = lang
    return lang

async def set_user_language(user_id, lang):
    _user_language_cache[user_id] = lang
    await users_col.update_one({"user_id": user_id}, {"$set": {"language": lang}})

async def update_status(user_id, status):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"status": status}},
        upsert=True,
    )

async def log_interaction(user_id, button_name):
    await users_col.update_one(
        {"user_id": user_id},
        {
            "$push": {
                "interaction_history": {
                    "button": button_name,
                    "timestamp": time.time()
                }
            }
        },
        upsert=True
    )

async def update_registered_player_id(user_id, player_id):
    await users_col.update_one(
        {"user_id": user_id},
        {"$set": {"registered_player_id": player_id}},
        upsert=True
    )

async def get_registered_player_id(user_id):
    doc = await users_col.find_one({"user_id": user_id}, {"registered_player_id": 1})
    return doc.get("registered_player_id") if doc else None

async def add_template_msg_id(msg_type, msg_id):
    await settings_col.update_one(
        {"type": msg_type},
        {"$push": {"msg_ids": msg_id}},
        upsert=True
    )

async def clear_template_msgs(msg_type):
    await settings_col.update_one(
        {"type": msg_type},
        {"$set": {"msg_ids": []}},
        upsert=True
    )

async def get_template_msg_ids(msg_type):
    doc = await settings_col.find_one({"type": msg_type})
    return doc.get("msg_ids", []) if doc else []

async def get_bot_setting(key, default_value):
    doc = await settings_col.find_one({"type": "bot_config"})
    if doc and key in doc:
        return doc[key]
    return default_value

async def set_bot_setting(key, value):
    await settings_col.update_one(
        {"type": "bot_config"},
        {"$set": {key: value}},
        upsert=True
    )

async def get_pending_user_ids():
    return [doc["user_id"] async for doc in users_col.find({"status": "pending"}, {"user_id": 1})]

async def save_admin_message_mapping(admin_message_id, user_id):
    await admin_messages_col.update_one(
        {"admin_message_id": admin_message_id},
        {
            "$set": {
                "admin_message_id": admin_message_id,
                "user_id": user_id,
                "timestamp": time.time()
            }
        },
        upsert=True
    )

async def get_user_id_from_admin_message(admin_message_id):
    doc = await admin_messages_col.find_one({"admin_message_id": admin_message_id}, {"user_id": 1})
    return doc.get("user_id") if doc else None

# ================= BOT API =================
async def approve_join_request_via_bot_api(chat_id, user_id):
    def _send_request():
        payload = parse.urlencode({
            "chat_id": chat_id,
            "user_id": user_id,
        }).encode()
        req = urllib_request.Request(
            url=f"https://api.telegram.org/bot{BOT_TOKEN}/approveChatJoinRequest",
            data=payload,
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"ok": False, "description": f"HTTP {exc.code}: {body}"}

    try:
        data = await asyncio.to_thread(_send_request)
    except Exception as exc:
        return False, f"Bot API request failed: {exc}"

    if data.get("ok"):
        return True, "approved"
    return False, data.get("description", "Unknown Bot API error")

# ================= PREMIUM DETECTION =================
USER_SESSION_IS_PREMIUM = None

async def has_premium_emoji(msg):
    entities = msg.entities or []
    caption_entities = msg.caption_entities or []
    for entity in entities + caption_entities:
        if entity.type == MessageEntityType.CUSTOM_EMOJI or getattr(entity, "custom_emoji_id", None):
            return True
    return False

async def is_premium_user_session(client):
    global USER_SESSION_IS_PREMIUM
    if USER_SESSION_IS_PREMIUM is None:
        try:
            me = await client.get_me()
            USER_SESSION_IS_PREMIUM = bool(getattr(me, "is_premium", False))
        except Exception:
            USER_SESSION_IS_PREMIUM = False
    return USER_SESSION_IS_PREMIUM

async def send_dynamic_template(user_id, msg_type, extra_reply_markup=None):
    lang = await get_user_language(user_id)
    lang_msg_type = f"{msg_type}_{lang}"
    
    msg_ids = await get_template_msg_ids(lang_msg_type)
    if not msg_ids:
        msg_ids = await get_template_msg_ids(msg_type)
        if not msg_ids:
            return []

    sent_message_ids = []
    for i, msg_id in enumerate(msg_ids):
        try:
            rm_dict = None
            
            # Optimization 1: Only fetch & merge reply markup if extra_reply_markup is provided
            if i == len(msg_ids) - 1 and extra_reply_markup:
                cache_key = (TEMPLATE_CHANNEL_ID, msg_id)
                orig_rm = None
                
                # Optimization 2: Use in-memory cache for original reply markups to avoid duplicate get_messages requests
                if cache_key in _reply_markup_cache:
                    orig_rm = _reply_markup_cache[cache_key]
                else:
                    try:
                        orig_msg = await app.get_messages(TEMPLATE_CHANNEL_ID, msg_id)
                        if orig_msg and orig_msg.reply_markup:
                            import json
                            orig_rm = json.loads(str(orig_msg.reply_markup))
                        _reply_markup_cache[cache_key] = orig_rm
                    except Exception as get_err:
                        logger.error(f"Failed to fetch template message {msg_id} for markup: {get_err}")
                
                import json
                extra_dict = json.loads(str(extra_reply_markup))
                
                if orig_rm and "inline_keyboard" in orig_rm:
                    # Create a copy to avoid mutating cache
                    import copy
                    rm_dict = copy.deepcopy(orig_rm)
                    rm_dict["inline_keyboard"].extend(extra_dict.get("inline_keyboard", []))
                else:
                    rm_dict = extra_dict

            success, data = await copy_message_via_bot_api(
                chat_id=user_id,
                from_chat_id=TEMPLATE_CHANNEL_ID,
                message_id=msg_id,
                reply_markup=rm_dict
            )
            if not success:
                raise Exception(data.get("description", "Bot API copyMessage failed"))
            
            sent_message_ids.append(data["result"]["message_id"])
            
            # Optimization 3: Only sleep if there are more messages to send in the template
            if i < len(msg_ids) - 1:
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Bot failed to send {msg_type} to {user_id}: {e}")

    return sent_message_ids

def strip_emojis(text):
    cleaned = []
    for char in text:
        cp = ord(char)
        is_emoji = (
            (0x2600 <= cp <= 0x27BF) or
            (0x1F000 <= cp <= 0x1F9FF) or
            (0x1FA00 <= cp <= 0x1FAFF) or
            (0xFE00 <= cp <= 0xFE0F)
        )
        if not is_emoji:
            cleaned.append(char)
    result = "".join(cleaned).strip()
    return re.sub(r'\s+', ' ', result)

# ================= STATE MACHINE (ADMIN) =================
admin_states = {}

@app.on_message(filters.private & filters.user(ADMIN_IDS), group=0)
async def state_handler(client, message):
    user_id = message.from_user.id
    
    if user_id not in admin_states:
        # Inspect custom emojis first (so admins can easily grab IDs at any time when not in a state)
        entities = message.entities or []
        caption_entities = message.caption_entities or []
        for entity in entities + caption_entities:
            if entity.type == MessageEntityType.CUSTOM_EMOJI:
                emoji_id = entity.custom_emoji_id
                await message.reply(
                    f"⭐ **Telegram Premium Emoji ID Detected!**\n\n"
                    f"Emoji ID: `{emoji_id}`\n\n"
                    f"You can copy this ID and set it in **Settings** ➡️ **Configure Service Buttons**."
                )
                return
    else:
        if message.text and message.text.startswith("/"):
            del admin_states[user_id]
            await message.reply("State cancelled because you sent a command.")
            raise ContinuePropagation

        state_data = admin_states[user_id]
        msg_type = state_data["msg_type"]
        prompt_msg_id = state_data.get("prompt_msg_id")
        last_saved_msg_id = state_data.get("last_saved_msg_id")
        current_keyboard = state_data.get("keyboard", [])

        if msg_type == "delay_input":
            try:
                delay_val = int(message.text.strip())
                await set_bot_setting("auto_accept_delay", max(0, delay_val))
                status_text = f"✅ **Auto-Accept Delay set to {max(0, delay_val)} seconds!**"
            except Exception:
                status_text = "❌ Invalid number. Please send a valid number of seconds."
            
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Settings", callback_data="admin_settings")]])
            await client.send_message(chat_id=user_id, text=status_text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
            del admin_states[user_id]
            return

        if msg_type == "admin_link_input":
            text_val = message.text.strip()
            normalized_link = text_val
            if normalized_link.startswith("@"):
                normalized_link = f"https://t.me/{normalized_link[1:]}"
            elif not normalized_link.startswith("http://") and not normalized_link.startswith("https://"):
                if normalized_link.startswith("t.me/"):
                    normalized_link = "https://" + normalized_link
                else:
                    normalized_link = f"https://t.me/{normalized_link}"
            
            await set_bot_setting("admin_contact_link", normalized_link)
            status_text = f"✅ **Admin Contact Link set to:**\n`{normalized_link}`"
            
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Settings", callback_data="admin_settings")]])
            await client.send_message(chat_id=user_id, text=status_text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
            del admin_states[user_id]
            return

        if msg_type.startswith("emoji_input_"):
            btn_key = msg_type.replace("emoji_input_", "")
            text_val = (message.text or message.caption or "").strip()
            
            # Detect custom emoji ID
            detected_emoji_id = ""
            entities = message.entities or []
            caption_entities = message.caption_entities or []
            for entity in entities + caption_entities:
                if entity.type == MessageEntityType.CUSTOM_EMOJI:
                    detected_emoji_id = str(entity.custom_emoji_id)
                    break
            
            # Strip standard and custom emoji characters from the label text
            text_val = strip_emojis(text_val)
            
            await set_bot_setting(f"text_{btn_key}", text_val)
            await set_bot_setting(f"emoji_{btn_key}", detected_emoji_id)
            
            status_text = (
                f"✅ **Button Customization Saved!**\n\n"
                f"Button Label: `{text_val}`\n"
                f"Premium Emoji ID: `{detected_emoji_id or 'None'}`"
            )
            
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Customize Buttons", callback_data="admin_emoji_settings")]])
            await client.send_message(chat_id=user_id, text=status_text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
            del admin_states[user_id]
            return

        if msg_type.startswith("link_input_"):
            btn_key = msg_type.replace("link_input_", "")
            text_val = message.text.strip()
            
            # Normalize links starting with t.me/ or @
            normalized_link = text_val
            if normalized_link.startswith("@"):
                normalized_link = f"https://t.me/{normalized_link[1:]}"
            elif not normalized_link.startswith("http://") and not normalized_link.startswith("https://"):
                if normalized_link.startswith("t.me/"):
                    normalized_link = "https://" + normalized_link
                else:
                    normalized_link = f"https://t.me/{normalized_link}"
            
            await set_bot_setting(f"link_{btn_key}", normalized_link)
            status_text = f"✅ **Link for {btn_key.upper()} successfully set to:**\n`{normalized_link}`"
            
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Customize Buttons", callback_data="admin_emoji_settings")]])
            await client.send_message(chat_id=user_id, text=status_text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
            del admin_states[user_id]
            return

        friendly_name = msg_type.replace("_msg", "").capitalize()

        try:
            if prompt_msg_id:
                await client.delete_messages(user_id, prompt_msg_id)
        except Exception:
            pass

        text = message.text or message.caption or ""
        is_button = False
        
        if last_saved_msg_id and " - " in text and text.count("\n") == 0:
            parts = text.split(" - ", 1)
            btn_name = parts[0].strip()
            btn_url = parts[1].strip()
            
            if btn_url.startswith("http://") or btn_url.startswith("https://") or btn_url.startswith("t.me/"):
                if not btn_url.startswith("http"):
                    btn_url = "https://" + btn_url
                
                is_button = True
                current_keyboard.append([InlineKeyboardButton(btn_name, url=btn_url)])
                
                try:
                    await client.edit_message_reply_markup(
                        chat_id=TEMPLATE_CHANNEL_ID,
                        message_id=last_saved_msg_id,
                        reply_markup=InlineKeyboardMarkup(current_keyboard)
                    )
                    status_text = f"🔗 **Button Added!**\n\nYou can add another button (Format: `Name - URL`), send a new message, or click **Done**."
                except Exception as e:
                    status_text = f"❌ Failed to attach button. Error: {e}"
        
        if not is_button:
            try:
                logger.info("Processing new template message...")
                # Use Official Bot API to 100% preserve CUSTOM_EMOJI
                success, data = await copy_message_via_bot_api(
                    chat_id=TEMPLATE_CHANNEL_ID,
                    from_chat_id=message.chat.id,
                    message_id=message.id
                )
                if not success:
                    raise Exception(data.get("description", "Bot API copyMessage failed"))
                    
                new_msg_id = data["result"]["message_id"]
                await add_template_msg_id(msg_type, new_msg_id)
                last_saved_msg_id = new_msg_id
                current_keyboard = []
                status_text = (
                    f"✅ **Saved to {friendly_name} Message!**\n\n"
                    f"To add an Inline Button to this message, send: `Button Name - https://link.com`\n"
                    f"Or send another message to add to the sequence, or click **Done**."
                )
            except Exception as e:
                status_text = f"❌ Failed to save message. Ensure the bot is an admin in the Template Channel. Error: {e}"

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Done Adding Messages", callback_data="done_state")],
            [InlineKeyboardButton("« Cancel & Back", callback_data="admin_panel")]
        ])
        
        new_prompt = await client.send_message(
            chat_id=user_id,
            text=status_text,
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN
        )
        
        admin_states[user_id] = {
            "msg_type": msg_type,
            "prompt_msg_id": new_prompt.id,
            "last_saved_msg_id": last_saved_msg_id,
            "keyboard": current_keyboard
        }
        return

    raise ContinuePropagation

# ================= START COMMAND =================
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_obj = message.from_user
    
    if user_obj.id in ADMIN_IDS:
        await send_panel(message)
        return

    await add_user(user_obj, "started", "SELECTING_LANGUAGE")
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
            InlineKeyboardButton("🇮🇳 Hindi (हिंदी)", callback_data="lang_hi")
        ]
    ])
    
    try:
        await copy_message_via_bot_api(
            chat_id=user_obj.id,
            from_chat_id=TEMPLATE_CHANNEL_ID,
            message_id=159
        )
        await asyncio.sleep(0.3)
    except Exception as e:
        logger.warning(f"Could not send pre-intro msg 159 to {user_obj.id}: {e}")

    try:
        await message.reply_text(
            "👋 **Welcome! Please select your language / कृपया अपनी भाषा चुनें:**",
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Failed to send language selection to {user_obj.id}: {e}")

    cancel_user_jobs(user_obj.id)
    schedule_followups(user_obj.id)


# ================= ADMIN PANEL COMMANDS =================
@app.on_message(filters.command("panel") & filters.user(ADMIN_IDS))
async def panel_cmd(client, message):
    await send_panel(message)

async def send_panel(message):
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📝 Start Msg", callback_data="set_start_msg"),
            InlineKeyboardButton("👋 Welcome Msg", callback_data="set_welcome_msg")
        ],
        [
            InlineKeyboardButton("🎁 Promo Msg", callback_data="set_fulfillment_msg"),
            InlineKeyboardButton("✅ Approved Msg", callback_data="set_approved_msg")
        ],
        [
            InlineKeyboardButton("🚪 Leave Msg", callback_data="set_leave_msg"),
            InlineKeyboardButton("⚡ Hack Msg", callback_data="set_hack_msg")
        ],
        [
            InlineKeyboardButton("📊 Statistics", callback_data="admin_stats"),
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("⚙️ Settings (Auto)", callback_data="admin_settings"),
            InlineKeyboardButton("✅ Accept All Pending", callback_data="admin_accept_all")
        ]
    ])
    text = "⚙️ **Admin Dashboard**\n\nWelcome to your control panel. Select an option below to configure the bot."
    
    if hasattr(message, "edit_text"):
        try:
            await message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await message.reply(text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.reply(text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)

# ================= PEER CONNECTION =================
@app.on_message(filters.command("connect"))
async def connect_command(client, message):
    results = []
    
    for name, cid in [("Template Channel", TEMPLATE_CHANNEL_ID), ("Main Channel", CHANNEL_ID)]:
        try:
            await app.get_chat(cid)
            results.append(f"✅ Bot → {name}")
        except Exception as e:
            results.append(f"❌ Bot → {name}: {e}")
    
    if user_app:
        for name, cid in [("Template Channel", TEMPLATE_CHANNEL_ID), ("Main Channel", CHANNEL_ID)]:
            try:
                await user_app.get_chat(cid)
                results.append(f"✅ Userbot → {name}")
            except Exception as e:
                results.append(f"❌ Userbot → {name}: {e}")
        
        try:
            bot_me = await app.get_me()
            await user_app.get_users(bot_me.id)
            results.append(f"✅ Userbot → Bot DM")
        except Exception as e:
            results.append(f"❌ Userbot → Bot DM: {e}")
    else:
        results.append("⚠️ Userbot not active")
    
    status = "\n".join(results)
    reply = await message.reply(f"🔗 **Peer Connection Results:**\n\n{status}")
    
    await asyncio.sleep(5)
    try:
        await message.delete()
        await reply.delete()
    except Exception:
        pass

# ================= JOIN REQUEST LISTENER =================
@app.on_chat_join_request(filters.chat(CHANNEL_ID))
async def join_request(client, request: ChatJoinRequest):
    user_obj = request.from_user
    logger.info(f"JOIN REQUEST from {user_obj.first_name} ({user_obj.id})")
    
    await add_user(user_obj, "pending", "SELECTING_LANGUAGE")
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
            InlineKeyboardButton("🇮🇳 Hindi (हिंदी)", callback_data="lang_hi")
        ]
    ])
    
    try:
        await copy_message_via_bot_api(
            chat_id=user_obj.id,
            from_chat_id=TEMPLATE_CHANNEL_ID,
            message_id=159
        )
        await asyncio.sleep(0.3)
    except Exception as e:
        logger.warning(f"Could not send pre-intro msg 159 to {user_obj.id}: {e}")

    try:
        await app.send_message(
            chat_id=user_obj.id,
            text="👋 **Welcome! Please select your language / कृपया अपनी भाषा चुनें:**",
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.warning(f"Could not send language selection welcome to {user_obj.id}: {e}")

    cancel_user_jobs(user_obj.id)
    schedule_followups(user_obj.id)
    logger.info(f"Scheduled transitions & followups for {user_obj.id}")

if STRING_SESSION:
    @user_app.on_chat_join_request(filters.chat(CHANNEL_ID))
    async def userbot_join_request_warmup(client, request: ChatJoinRequest):
        pass

# ================= BROADCAST =================
@app.on_message(filters.command("broadcast") & filters.user(ADMIN_IDS))
async def broadcast_cmd(client, message):
    if not message.reply_to_message:
        return await message.reply("Reply to a message with `/broadcast` to send that exact message to all users.")

    source_message = message.reply_to_message
    users = users_col.find({}, {"user_id": 1})
    total = await users_col.count_documents({})
    success = 0
    failed = 0

    status_msg = await message.reply(f"⏳ **Broadcast Started**\n\nTotal Users: {total}\nSent: 0\nFailed: 0", parse_mode=ParseMode.MARKDOWN)

    i = -1
    async for saved_user in users:
        i += 1
        user_id = saved_user["user_id"]
        try:
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=source_message.chat.id,
                message_id=source_message.id,
            )
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

        if i > 0 and i % 50 == 0:
            try:
                await status_msg.edit_text(f"⏳ **Broadcast In Progress**\n\nTotal Users: {total}\nSent: {success}\nFailed: {failed}", parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass

    await status_msg.edit_text(f"✅ **Broadcast Completed**\n\nTotal Users: {total}\nSent: {success}\nFailed: {failed}", parse_mode=ParseMode.MARKDOWN)

# ================= USER LEFT =================
@app.on_chat_member_updated(filters.chat(CHANNEL_ID))
async def left_handler(client, update: ChatMemberUpdated):
    old = update.old_chat_member
    new = update.new_chat_member
    
    old_status = old.status if old else None
    new_status = new.status if new else None
    logger.info(f"Chat member updated: {update.from_user.first_name if update.from_user else 'Unknown'} | Old: {old_status} -> New: {new_status}")

    if (
        old and new and
        old.status in (ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR) and
        new.status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    ):
        user_obj = new.user
        logger.info(f"User {user_obj.first_name} left! Sending leave message...")
        await add_user(user_obj, "left")
        await send_dynamic_template(user_obj.id, "leave_msg")

# ================= FULFILLMENT MENU SENDER =================
# ================= BOT API DIRECT SEND HELPERS =================
async def send_message_via_bot_api(chat_id, text, reply_markup=None, parse_mode="Markdown"):
    def _send():
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        req = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"ok": False, "description": f"HTTP {exc.code}: {body}"}

    try:
        data = await asyncio.to_thread(_send)
        if not data.get("ok"):
            logger.error(f"Bot API sendMessage failed: {data.get('description')}")
        return data.get("ok"), data
    except Exception as e:
        logger.error(f"Failed to send message via Bot API: {e}")
        return False, str(e)

async def copy_message_via_bot_api(chat_id, from_chat_id, message_id, reply_markup=None):
    def _send():
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/copyMessage"
        payload = {
            "chat_id": chat_id,
            "from_chat_id": from_chat_id,
            "message_id": message_id
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        req = urllib_request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"ok": False, "description": f"HTTP {exc.code}: {body}"}

    try:
        data = await asyncio.to_thread(_send)
        return data.get("ok"), data
    except Exception as e:
        logger.error(f"Failed to copy message via Bot API: {e}")
        return False, str(e)

# ================= FULFILLMENT MENU SENDER =================
async def send_fulfillment_menu(user_id):
    vip_emoji = await get_bot_setting("emoji_vip", EMOJI_VIP)
    sureshot_emoji = await get_bot_setting("emoji_sureshot", EMOJI_SURESHOT)
    numbershot_emoji = await get_bot_setting("emoji_numbershot", EMOJI_NUMBERSHOT)
    hack_emoji = await get_bot_setting("emoji_hack", EMOJI_HACK)
    challenge_emoji = await get_bot_setting("emoji_challenge", EMOJI_CHALLENGE)

    vip_text = await get_bot_setting("text_vip", TEXT_VIP)
    sureshot_text = await get_bot_setting("text_sureshot", TEXT_SURESHOT)
    numbershot_text = await get_bot_setting("text_numbershot", TEXT_NUMBERSHOT)
    hack_text = await get_bot_setting("text_hack", TEXT_HACK)
    challenge_text = await get_bot_setting("text_challenge", TEXT_CHALLENGE)

    vip_style = await get_bot_setting("style_vip", "primary")
    sureshot_style = await get_bot_setting("style_sureshot", "danger")
    numbershot_style = await get_bot_setting("style_numbershot", "success")
    hack_style = await get_bot_setting("style_hack", "success")
    challenge_style = await get_bot_setting("style_challenge", "primary")

    def make_btn(text, callback_data, emoji_id, style=None):
        btn = {"text": text, "callback_data": callback_data}
        if emoji_id and emoji_id.strip().isdigit():
            btn["icon_custom_emoji_id"] = emoji_id.strip()
        if style:
            btn["style"] = style
        return btn

    keyboard = {
        "inline_keyboard": [
            [
                make_btn(vip_text, "btn_vip_session", vip_emoji, vip_style),
                make_btn(sureshot_text, "btn_sureshot", sureshot_emoji, sureshot_style)
            ],
            [
                make_btn(numbershot_text, "btn_numbershot", numbershot_emoji, numbershot_style),
                make_btn(hack_text, "btn_hack", hack_emoji, hack_style)
            ],
            [
                make_btn(challenge_text, "btn_2k_challenge", challenge_emoji, challenge_style)
            ]
        ]
    }
    
    sent = await send_dynamic_template(user_id, "fulfillment_msg", extra_reply_markup=keyboard)
    if not sent:
        try:
            lang = await get_user_language(user_id)
            if lang == "hi":
                text = (
                    "✨ **VIP सिग्नल्स और कंपाउंडिंग मेनू** ✨\n\n"
                    "कमाना शुरू करने के लिए नीचे दिए गए हमारे प्रीमियम टूल्स या कंपाउंडिंग पैकेजों में से किसी एक को चुनें:"
                )
            else:
                text = (
                    "✨ **VIP Signals & Compounding Menu** ✨\n\n"
                    "Select one of our premium tools or compounding packages below to start earning:"
                )
            await send_message_via_bot_api(user_id, text, reply_markup=keyboard)
        except Exception as e:
            logger.error(f"Failed to send fallback fulfillment menu to {user_id}: {e}")



# ================= ADMIN CHAT PROXY SYSTEM =================
async def route_message_to_admin(client, message):
    user_id = message.from_user.id
    name = message.from_user.first_name or "User"
    username = f"@{message.from_user.username}" if message.from_user.username else "No Username"
    
    has_caption_support = (
        message.photo or message.video or message.voice or 
        message.audio or message.document or message.animation
    )
    
    for admin_id in ADMIN_CHAT_IDS:
        admin_msg = None
        try:
            if message.text:
                text = f"{message.text}\n\n👤 User: {name} ({username})\n🆔 #id{user_id}"
                admin_msg = await app.send_message(
                    chat_id=admin_id,
                    text=text
                )
            elif has_caption_support:
                caption = message.caption or ""
                new_caption = f"{caption}\n\n👤 User: {name} ({username})\n🆔 #id{user_id}"
                admin_msg = await message.copy(
                    chat_id=admin_id,
                    caption=new_caption
                )
            else:
                admin_msg = await message.copy(chat_id=admin_id)
                info_msg = await app.send_message(
                    chat_id=admin_id,
                    text=f"👤 Above message from: {name} ({username})\n🆔 #id{user_id}",
                    reply_to_message_id=admin_msg.id
                )
                await save_admin_message_mapping(info_msg.id, user_id)
                
            if admin_msg:
                await save_admin_message_mapping(admin_msg.id, user_id)
                logger.info(f"Routed user {user_id} message to admin chat {admin_id}. Admin Msg ID: {admin_msg.id}")
                
        except Exception as e:
            logger.error(f"Failed to route user {user_id} message to admin chat {admin_id}: {e}")

@app.on_message(filters.chat(ADMIN_CHAT_IDS) & filters.reply, group=1)
async def admin_reply_handler(client, message):
    if message.text and message.text.startswith("/"):
        raise ContinuePropagation
        
    replied_msg = message.reply_to_message
    if not replied_msg:
        return
        
    user_id = await get_user_id_from_admin_message(replied_msg.id)
    
    if not user_id:
        text_to_search = replied_msg.text or replied_msg.caption or ""
        match = re.search(r"#id(\d+)", text_to_search)
        if match:
            try:
                user_id = int(match.group(1))
            except ValueError:
                pass
                
    if not user_id:
        return
        
    try:
        await message.copy(chat_id=user_id)
        logger.info(f"Proxied admin reply to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to proxy reply to user {user_id}: {e}")
        await message.reply(f"❌ Failed to proxy reply to user #id{user_id}. Error: {e}")

# ================= USER PRIVATE MESSAGES FILTER =================
@app.on_message(filters.private & ~filters.user(ADMIN_IDS), group=2)
async def user_private_message_handler(client, message):
    if message.from_user and message.from_user.is_bot:
        return
        
    if message.text and message.text.startswith("/"):
        return

    user_id = message.from_user.id
    
    state = await get_user_state(user_id)
    if not state:
        await add_user(message.from_user, "started", "NEW_USER")
        state = "NEW_USER"
        
    logger.info(f"Message from user {user_id} in state {state}")
    
    if state == "WAITING_FOR_YES" or state == "NEW_USER":
        text = (message.text or "").strip().lower()
        affirmative_words = ["yes", "ready", "yep", "ok", "sure", "start", "agree", "y", "yeah", "indeed"]
        is_affirmative = False
        for word in affirmative_words:
            if word in text:
                is_affirmative = True
                break
                
        if is_affirmative:
            cancel_user_jobs(user_id)
            await update_user_state(user_id, "COMPLETED")
            await send_fulfillment_menu(user_id)
            
            auto_accept = await get_bot_setting("auto_accept", True)
            if auto_accept:
                approved, reason = await approve_join_request_via_bot_api(CHANNEL_ID, user_id)
                if approved or (reason and "USER_ALREADY_PARTICIPANT" in reason.upper()):
                    await update_status(user_id, "approved")
                    await send_dynamic_template(user_id, "approved_msg")
                else:
                    logger.error(f"Auto-accept failed on affirmative reply for {user_id}: {reason}")
        else:
            try:
                lang = await get_user_language(user_id)
                if lang == "hi":
                    prompt = "⚠️ कृपया आगे बढ़ने और अपनी पहुँच अनलॉक करने के लिए **'yes'** या **'ready'** लिखकर उत्तर दें!"
                else:
                    prompt = "⚠️ Please reply with **'yes'** or **'ready'** to unlock your access and proceed!"
                await message.reply(prompt)
            except Exception as e:
                logger.error(f"Failed to send confirmation prompt to {user_id}: {e}")
                
    elif state in ("COMPLETED", "LIVE_CHAT"):
        await route_message_to_admin(client, message)

async def show_admin_emoji_settings(query):
    vip = await get_bot_setting("emoji_vip", EMOJI_VIP) or "None"
    sureshot = await get_bot_setting("emoji_sureshot", EMOJI_SURESHOT) or "None"
    numbershot = await get_bot_setting("emoji_numbershot", EMOJI_NUMBERSHOT) or "None"
    hack = await get_bot_setting("emoji_hack", EMOJI_HACK) or "None"
    challenge = await get_bot_setting("emoji_challenge", EMOJI_CHALLENGE) or "None"

    vip_text = await get_bot_setting("text_vip", TEXT_VIP)
    sureshot_text = await get_bot_setting("text_sureshot", TEXT_SURESHOT)
    numbershot_text = await get_bot_setting("text_numbershot", TEXT_NUMBERSHOT)
    hack_text = await get_bot_setting("text_hack", TEXT_HACK)
    challenge_text = await get_bot_setting("text_challenge", TEXT_CHALLENGE)
    
    vip_style = await get_bot_setting("style_vip", "primary")
    sureshot_style = await get_bot_setting("style_sureshot", "danger")
    numbershot_style = await get_bot_setting("style_numbershot", "success")
    hack_style = await get_bot_setting("style_hack", "success")
    challenge_style = await get_bot_setting("style_challenge", "primary")

    vip_link = await get_bot_setting("link_vip", LINK_VIP)
    sureshot_link = await get_bot_setting("link_sureshot", LINK_SURESHOT)
    numbershot_link = await get_bot_setting("link_numbershot", LINK_NUMBERSHOT)
    challenge_link = await get_bot_setting("link_challenge", LINK_CHALLENGE)
    
    text = (
        "⭐ **Button Customization (Text, Colors & Links)** ⭐\n\n"
        "Configure button labels, premium custom emojis, color styles, and target redirect links.\n\n"
        f"👑 **VIP**: Label `{vip_text}` | Emoji `{vip}` | Color `{vip_style or 'default'}`\n"
        f"   🔗 Link: {vip_link}\n\n"
        f"🔥 **SureShot**: Label `{sureshot_text}` | Emoji `{sureshot}` | Color `{sureshot_style or 'default'}`\n"
        f"   🔗 Link: {sureshot_link}\n\n"
        f"🎯 **Number Shot**: Label `{numbershot_text}` | Emoji `{numbershot}` | Color `{numbershot_style or 'default'}`\n"
        f"   🔗 Link: {numbershot_link}\n\n"
        f"⚡ **Hack**: Label `{hack_text}` | Emoji `{hack}` | Color `{hack_style or 'default'}`\n"
        f"   *(Downloads APK locally)*\n\n"
        f"💎 **Challenge**: Label `{challenge_text}` | Emoji `{challenge}` | Color `{challenge_style or 'default'}`\n"
        f"   🔗 Link: {challenge_link}\n\n"
        "Select an option to update:"
    )
    
    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👑 VIP Label", callback_data="set_emoji_vip"),
            InlineKeyboardButton("🎨 VIP Color", callback_data="set_style_vip"),
            InlineKeyboardButton("🔗 VIP Link", callback_data="admin_set_link_vip")
        ],
        [
            InlineKeyboardButton("🔥 SureShot Label", callback_data="set_emoji_sureshot"),
            InlineKeyboardButton("🎨 SureShot Color", callback_data="set_style_sureshot"),
            InlineKeyboardButton("🔗 SureShot Link", callback_data="admin_set_link_sureshot")
        ],
        [
            InlineKeyboardButton("🎯 Number Shot Label", callback_data="set_emoji_numbershot"),
            InlineKeyboardButton("🎨 Number Shot Color", callback_data="set_style_numbershot"),
            InlineKeyboardButton("🔗 Number Shot Link", callback_data="admin_set_link_numbershot")
        ],
        [
            InlineKeyboardButton("⚡ Hack Label", callback_data="set_emoji_hack"),
            InlineKeyboardButton("🎨 Hack Color", callback_data="set_style_hack")
        ],
        [
            InlineKeyboardButton("💎 Challenge Label", callback_data="set_emoji_challenge"),
            InlineKeyboardButton("🎨 Challenge Color", callback_data="set_style_challenge"),
            InlineKeyboardButton("🔗 Challenge Link", callback_data="admin_set_link_challenge")
        ],
        [InlineKeyboardButton("« Back to Settings", callback_data="admin_settings")]
    ])
    await query.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)

# ================= CALLBACK QUERY HANDLER =================
@app.on_callback_query()
async def callbacks(client, query):
    user_id = query.from_user.id
    data = query.data

    # --- Instant ACK: stop the button spinner immediately ---
    try:
        await query.answer()
    except Exception:
        pass

    # --- Per-user lock: ignore duplicate taps while still processing ---
    if user_id in _active_callback_users:
        return
    _active_callback_users.add(user_id)
    
    try:
        await _handle_callback(client, query, user_id, data)
    finally:
        _active_callback_users.discard(user_id)


async def _handle_callback(client, query, user_id, data):

    # Handle user language selection callback
    if data.startswith("lang_"):
        # State check: ignore language selection if user is already completed
        state = await get_user_state(user_id)
        if state in ("COMPLETED", "LIVE_CHAT"):
            return
        lang = data.replace("lang_", "")
        await set_user_language(user_id, lang)
        await update_user_state(user_id, "WAITING_FOR_YES")
        
        # Determine template type based on user status
        status = "started"
        doc = await users_col.find_one({"user_id": user_id}, {"status": 1})
        if doc:
            status = doc.get("status", "started")
            
        tmpl_type = "start_msg" if status == "started" else "welcome_msg"
        
        lang_val = await get_user_language(user_id)
        btn_text = "✅ हाँ, मैं तैयार हूँ" if lang_val == "hi" else "✅ Yes, I'm Ready"
        extra_kb = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, callback_data="btn_yes_ready")]])
        
        sent = await send_dynamic_template(user_id, tmpl_type, extra_reply_markup=extra_kb)
        if not sent:
            first_name = query.from_user.first_name or "User"
            if lang == "hi":
                welcome_text = (
                    f"नमस्ते {first_name}! VIP Earnings Hub में आपका स्वागत है! 👋\n\n"
                    f"ℹ️ **हमारे बारे में**:\n"
                    f"हम एक प्रमुख वित्तीय और गेमिंग सिग्नल्स समुदाय हैं। हमारे विशेषज्ञ आपको लगातार दैनिक लाभ अर्जित करने में मदद करने के लिए 95%+ सटीकता दर के साथ दैनिक सिग्नल्स प्रदान करते हैं।\n\n"
                    f"🎁 **हमसे जुड़ने के लाभ**:\n"
                    f"🚀 दैनिक VIP सिग्नल्स और कंपाउंडिंग गाइड्स\n"
                    f"🎤 विशेषज्ञों के साथ लाइव वॉयस सेशन्स\n"
                    f"💻 विशेष गेम हैक्स और श्योरशॉट्स\n"
                    f"💰 2k को 55k में बदलने के लिए कंपाउंडिंग चुनौतियाँ!\n\n"
                    f"चैनल तक पहुँचने और सेवाओं को अनलॉक करने के लिए, कृपया नीचे दिए गए बटन पर क्लिक करें!"
                )
            else:
                welcome_text = (
                    f"Hello {first_name}! Welcome to the VIP Earnings Hub! 👋\n\n"
                    f"ℹ️ **About Us**:\n"
                    f"We are a leading financial and gaming signals community. Our experts provide daily signals with a 95%+ accuracy rate to help you earn consistent daily profits.\n\n"
                    f"🎁 **Benefits of Joining Us**:\n"
                    f"🚀 Daily VIP Signals & Compounding Guides\n"
                    f"🎤 Live Voice Sessions with Experts\n"
                    f"💻 Exclusive Game Hacks & SureShots\n"
                    f"💰 Compounding challenges to turn 2k into 55k!\n\n"
                    f"To unlock your channel access and services, please click the button below!"
                )
            await query.message.reply(welcome_text, reply_markup=extra_kb)
            

        try:
            await query.message.delete()
        except Exception:
            pass
        return

    if data == "btn_yes_ready":
        # State check: ignore if user is already completed
        state = await get_user_state(user_id)
        if state in ("COMPLETED", "LIVE_CHAT"):
            return
        cancel_user_jobs(user_id)
        await update_user_state(user_id, "COMPLETED")
        await send_fulfillment_menu(user_id)
        
        auto_accept = await get_bot_setting("auto_accept", True)
        if auto_accept:
            approved, reason = await approve_join_request_via_bot_api(CHANNEL_ID, user_id)
            if approved or (reason and "USER_ALREADY_PARTICIPANT" in reason.upper()):
                await update_status(user_id, "approved")
                await send_dynamic_template(user_id, "approved_msg")
            else:
                logger.error(f"Auto-accept failed on btn_yes_ready for {user_id}: {reason}")
                

        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    # Handle user interaction buttons
    if data.startswith("btn_"):


        button_name = data.replace("btn_", "").replace("_", " ").title()
        if "2K" in button_name.upper():
            button_name = "2k to 55k challenge"
        
        asyncio.ensure_future(log_interaction(user_id, button_name))
        
        if data == "btn_hack":
            # Handle hack option: send APK and transition to LIVE_CHAT directly
            await update_user_state(user_id, "LIVE_CHAT")
            cancel_user_jobs(user_id)

            
            # Try to send custom template messages first
            sent = await send_dynamic_template(user_id, "hack_msg")
            if sent and isinstance(sent, list) and len(sent) > 0:
                try:
                    await app.pin_chat_message(chat_id=user_id, message_id=sent[0], disable_notification=True, both_sides=True)
                except Exception as pin_err:
                    logger.error(f"Failed to pin custom hack message: {pin_err}")
            
            if not sent:
                # Find any APK file in the current directory (fallback)
                apk_file = None
                for file in os.listdir("."):
                    if file.lower().endswith(".apk"):
                        apk_file = file
                        break
                
                lang = await get_user_language(user_id)
                if lang == "hi":
                    caption = (
                        "⚡ **गेम हैक APK तैयार है!** ⚡\n\n"
                        "यहाँ आपकी प्रीमियम हैक APK फ़ाइल है। इसे अपने डिवाइस पर इंस्टॉल करें और भविष्यवाणी सुविधाओं का उपयोग शुरू करने के लिए इसे लॉन्च करें।\n\n"
                        "यदि आपको कोई समस्या आती है या कस्टम सिग्नल सेशन्स की आवश्यकता है, तो हमारे सपोर्ट एजेंटों से जुड़ने के लिए बेझिझक सीधे इस चैट में संदेश भेजें!"
                    )
                else:
                    caption = (
                        "⚡ **Game Hack APK ready!** ⚡\n\n"
                        "Here is your premium Hack APK file. Install it on your device and launch it to begin using the prediction features.\n\n"
                        "If you face any issues or need custom signal sessions, feel free to send a message directly here in this chat to connect with our support agents!"
                    )
                
                try:
                    msg = None
                    if apk_file and os.path.exists(apk_file):
                        msg = await app.send_document(
                            chat_id=user_id,
                            document=apk_file,
                            caption=caption
                        )
                    else:
                        # Fallback if no local APK file is found
                        msg = await app.send_message(
                            chat_id=user_id,
                            text=(
                                f"{caption}\n\n"
                                "*(Note: Premium Hack APK is currently being updated on our servers. An admin will send you the latest version directly here shortly.)*"
                            )
                        )
                    if msg:
                        try:
                            await app.pin_chat_message(chat_id=user_id, message_id=msg.id, disable_notification=True, both_sides=True)
                        except Exception as pin_err:
                            logger.error(f"Failed to pin fallback hack message: {pin_err}")
                except Exception as e:
                    logger.error(f"Failed to deliver Hack APK to {user_id}: {e}")
            return
        await update_user_state(user_id, "LIVE_CHAT")
        cancel_user_jobs(user_id)

        # Get service-specific contact link
        if data == "btn_vip_session":
            admin_link = await get_bot_setting("link_vip", LINK_VIP)
        elif data == "btn_sureshot":
            admin_link = await get_bot_setting("link_sureshot", LINK_SURESHOT)
        elif data == "btn_numbershot":
            admin_link = await get_bot_setting("link_numbershot", LINK_NUMBERSHOT)
        elif data == "btn_2k_challenge":
            admin_link = await get_bot_setting("link_challenge", LINK_CHALLENGE)
        else:
            admin_link = await get_bot_setting("admin_contact_link", "https://t.me/Pronyte")

        lang = await get_user_language(user_id)
        if lang == "hi":
            text = (
                f"🎯 **हमारे एडमिन से जुड़ें**\n\n"
                f"आपने चुना है: **{button_name}**.\n\n"
                f"इस सेवा को अनलॉक करने और कमाई शुरू करने के लिए, कृपया नीचे दिए गए बटन पर क्लिक करके सीधे हमारे आधिकारिक एडमिन को संदेश भेजें:\n\n"
                f"🔗 **एडमिन लिंक**: {admin_link}"
            )
        else:
            text = (
                f"🎯 **Connect with our Admin**\n\n"
                f"You selected: **{button_name}**.\n\n"
                f"To unlock this service and start earning, please message our official admin directly by clicking the button below:\n\n"
                f"🔗 **Admin Link**: {admin_link}"
            )

        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Message Admin Directly", url=admin_link)]
        ])


        try:
            await app.send_message(chat_id=user_id, text=text, reply_markup=buttons)
        except Exception as e:
            logger.error(f"Failed to send admin contact redirect to {user_id}: {e}")


        return

    # Check if admin (for other admin callbacks)
    if user_id not in ADMIN_IDS:
        return  # Not an admin, ignored

    if data == "admin_panel":
        if user_id in admin_states:
            del admin_states[user_id]
        await send_panel(query.message)
        return

    if data == "done_state":
        if user_id in admin_states:
            del admin_states[user_id]
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Panel", callback_data="admin_panel")]])
            await query.message.edit_text("✅ **Configuration saved successfully!**\nAll messages have been recorded.", reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return

    # Show language selection for template messages
    if data in ("set_start_msg", "set_welcome_msg", "set_fulfillment_msg", "set_approved_msg", "set_leave_msg", "set_hack_msg"):
        friendly_name = data.replace("set_", "").replace("_msg", "").capitalize()
        text = f"📝 **Configure Template: {friendly_name}**\n\nChoose the language version you want to edit:"
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🇺🇸 English / Default", callback_data=f"edit_tmpl_{data}_en"),
                InlineKeyboardButton("🇮🇳 Hindi (हिंदी)", callback_data=f"edit_tmpl_{data}_hi")
            ],
            [InlineKeyboardButton("« Back to Panel", callback_data="admin_panel")]
        ])
        await query.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return

    # Handle language-specific template input state
    if data.startswith("edit_tmpl_"):
        parts = data.replace("edit_tmpl_", "").replace("set_", "").split("_")
        msg_type_base = "_".join(parts[:-1]) # start_msg
        lang = parts[-1] # en or hi
        
        msg_type = f"{msg_type_base}_{lang}"
        await clear_template_msgs(msg_type)
        
        friendly_name = msg_type_base.replace("_msg", "").capitalize()
        lang_name = "English / Default" if lang == "en" else "Hindi"
        
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Cancel & Back", callback_data="admin_panel")]])
        prompt_msg = await query.message.edit_text(
            f"🛠 **Setting {friendly_name} ({lang_name}) Message**\n\n"
            f"Please send or forward the new message(s) now.\n\n"
            f"💡 *You can send multiple messages one by one.* I will send them in the exact order you provide.\n"
            f"💡 *Want buttons?* After sending a message, reply with `Button Name - https://link.com` to attach a button to it!\n\n"
            f"When you are finished, click **Done** on the confirmation.", 
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN
        )
        
        admin_states[user_id] = {
            "msg_type": msg_type,
            "prompt_msg_id": prompt_msg.id,
            "last_saved_msg_id": None,
            "keyboard": []
        }
        return

    if data.startswith("set_") and not data.startswith("set_style_") and not data.startswith("set_emoji_") and not data.startswith("set_admin_link_"):
        msg_type = data.replace("set_", "")
        await clear_template_msgs(msg_type)
        friendly_name = msg_type.replace("_msg", "").capitalize()
        
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Cancel & Back", callback_data="admin_panel")]])
        prompt_msg = await query.message.edit_text(
            f"🛠 **Setting {friendly_name} Message**\n\n"
            f"Please send or forward the new message(s) now.\n\n"
            f"💡 *You can send multiple messages one by one.* I will send them in the exact order you provide.\n"
            f"💡 *Want buttons?* After sending a message, reply with `Button Name - https://link.com` to attach a button to it!\n\n"
            f"When you are finished, click **Done** on the confirmation.", 
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN
        )
        
        admin_states[user_id] = {
            "msg_type": msg_type,
            "prompt_msg_id": prompt_msg.id,
            "last_saved_msg_id": None,
            "keyboard": []
        }
        return
        
    if data == "admin_stats":
        total = await users_col.count_documents({})
        approved = await users_col.count_documents({"status": "approved"})
        pending = await users_col.count_documents({"status": "pending"})
        rejected = await users_col.count_documents({"status": "rejected"})
        left = await users_col.count_documents({"status": "left"})
        started = await users_col.count_documents({"status": "started"})
        
        waiting_yes = await users_col.count_documents({"current_state": "WAITING_FOR_YES"})
        completed = await users_col.count_documents({"current_state": "COMPLETED"})
        live_chat = await users_col.count_documents({"current_state": "LIVE_CHAT"})
        
        stats_text = (
            f"📊 **Advanced Statistics**\n\n"
            f"👥 **Total Users**: `{total}`\n"
            f"✅ **Approved**: `{approved}`\n"
            f"⏳ **Pending Requests**: `{pending}`\n"
            f"🤖 **Started Bot**: `{started}`\n"
            f"🚪 **Left Channel**: `{left}`\n\n"
            f"⏳ **Waiting for Yes**: `{waiting_yes}`\n"
            f"✅ **Completed States**: `{completed}`\n"
            f"💬 **Live Chat States**: `{live_chat}`"
        )
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Panel", callback_data="admin_panel")]])
        await query.message.edit_text(stats_text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_broadcast":
        admin_states[user_id] = {
            "msg_type": "broadcast_input",
            "prompt_msg_id": None,
            "last_saved_msg_id": None,
            "keyboard": []
        }
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Cancel & Back", callback_data="admin_panel")]])
        await query.message.edit_text("📢 **Start Broadcast**\n\nPlease send the message you want to broadcast to all registered users.", reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_settings":
        auto_accept = await get_bot_setting("auto_accept", True)
        delay = await get_bot_setting("auto_accept_delay", 0)
        admin_link = await get_bot_setting("admin_contact_link", "https://t.me/Pronyte")
        
        aa_text = "🟢 Auto-Accept: Enabled" if auto_accept else "🔴 Auto-Accept: Disabled"
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(aa_text, callback_data="toggle_auto_accept")],
            [InlineKeyboardButton(f"⏱ Delay: {delay}s", callback_data="set_delay_input")],
            [InlineKeyboardButton(f"🔗 Admin Link: {admin_link[:20]}...", callback_data="set_admin_link_input")],
            [InlineKeyboardButton("🎛 Configure Service Buttons", callback_data="admin_emoji_settings")],
            [InlineKeyboardButton("« Back to Panel", callback_data="admin_panel")]
        ])
        await query.message.edit_text("⚙️ **Settings Dashboard**\n\nCustomize automated behaviors and button settings:", reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return

    if data == "toggle_auto_accept":
        current = await get_bot_setting("auto_accept", True)
        new_val = not current
        await set_bot_setting("auto_accept", new_val)
        
        delay = await get_bot_setting("auto_accept_delay", 0)
        admin_link = await get_bot_setting("admin_contact_link", "https://t.me/Pronyte")
        aa_text = "🟢 Auto-Accept: Enabled" if new_val else "🔴 Auto-Accept: Disabled"
        
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton(aa_text, callback_data="toggle_auto_accept")],
            [InlineKeyboardButton(f"⏱ Delay: {delay}s", callback_data="set_delay_input")],
            [InlineKeyboardButton(f"🔗 Admin Link: {admin_link[:20]}...", callback_data="set_admin_link_input")],
            [InlineKeyboardButton("🎛 Configure Service Buttons", callback_data="admin_emoji_settings")],
            [InlineKeyboardButton("« Back to Panel", callback_data="admin_panel")]
        ])
        await query.message.edit_reply_markup(reply_markup=buttons)
        return

    if data == "set_delay_input":
        admin_states[user_id] = {
            "msg_type": "delay_input",
            "prompt_msg_id": None,
            "last_saved_msg_id": None,
            "keyboard": []
        }
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Cancel & Back", callback_data="admin_settings")]])
        await query.message.edit_text("⏳ **Set Auto-Accept Delay**\n\nPlease send me a number (in seconds) for how long I should wait before accepting a user after they request to join.\n\nExample: Send `10` for a 10-second delay. Send `0` for instant.", reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return

    if data == "set_admin_link_input":
        admin_states[user_id] = {
            "msg_type": "admin_link_input",
            "prompt_msg_id": None,
            "last_saved_msg_id": None,
            "keyboard": []
        }
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Cancel & Back", callback_data="admin_settings")]])
        await query.message.edit_text("🔗 **Set Admin Contact Link**\n\nPlease send me the new Telegram contact link for the admin (starting with http:// or https:// or t.me/).\n\nExample: `https://t.me/your_admin_username`", reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return

    if data == "admin_emoji_settings":
        await show_admin_emoji_settings(query)
        return

    if data.startswith("set_emoji_"):
        emoji_key = data.replace("set_emoji_", "")
        admin_states[user_id] = {
            "msg_type": f"emoji_input_{emoji_key}",
            "prompt_msg_id": None,
            "last_saved_msg_id": None,
            "keyboard": []
        }
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Cancel & Back", callback_data="admin_emoji_settings")]])
        await query.message.edit_text(
            f"✏️ **Customize Button: {emoji_key.upper()}**\n\n"
            f"Please send the new button label. You can include standard emojis and premium custom emojis.\n\n"
            f"💡 **Example**: Send `💸 VIP 💸` containing a custom emoji. "
            f"The bot will set the button label to `💸 VIP 💸` and automatically extract any custom premium emoji ID!",
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if data.startswith("set_style_"):
        btn_key = data.replace("set_style_", "")
        current = await get_bot_setting(f"style_{btn_key}", "primary")
        
        text = (
            f"🎨 **Select Color Style for {btn_key.upper()}**\n\n"
            f"Current style: `{current or 'default (gray)'}`\n\n"
            f"Choose one of the colors below:"
        )
        
        buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔵 Primary (Blue)", callback_data=f"save_style_{btn_key}_primary"),
                InlineKeyboardButton("🟢 Success (Green)", callback_data=f"save_style_{btn_key}_success")
            ],
            [
                InlineKeyboardButton("🔴 Danger (Red)", callback_data=f"save_style_{btn_key}_danger"),
                InlineKeyboardButton("⚪ Default (Gray)", callback_data=f"save_style_{btn_key}_default")
            ],
            [InlineKeyboardButton("« Back", callback_data="admin_emoji_settings")]
        ])
        await query.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return

    if data.startswith("save_style_"):
        parts = data.replace("save_style_", "").split("_", 1)
        btn_key = parts[0]
        style_val = parts[1]
        
        if style_val == "default":
            style_val = ""
            
        await set_bot_setting(f"style_{btn_key}", style_val)

        await show_admin_emoji_settings(query)
        return

    if data.startswith("admin_set_link_"):
        link_key = data.replace("admin_set_link_", "")
        admin_states[user_id] = {
            "msg_type": f"link_input_{link_key}",
            "prompt_msg_id": None,
            "last_saved_msg_id": None,
            "keyboard": []
        }
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Cancel & Back", callback_data="admin_emoji_settings")]])
        await query.message.edit_text(
            f"🔗 **Set Redirect Link for {link_key.upper()}**\n\n"
            f"Please send the new Telegram message redirect link (starting with http://, https:// or t.me/).\n\n"
            f"Example: `https://t.me/m/zYHXmOTwZmRl`",
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if data == "admin_accept_all":

        await query.message.edit_text("⏳ Processing pending requests...")
        
        pending_ids = await get_pending_user_ids()
        if not pending_ids:
            buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Panel", callback_data="admin_panel")]])
            await query.message.edit_text("ℹ️ No pending requests found.", reply_markup=buttons)
            return
            
        success = 0
        failed = 0
        for uid in pending_ids:
            approved, reason = await approve_join_request_via_bot_api(CHANNEL_ID, uid)
            if approved or (reason and "USER_ALREADY_PARTICIPANT" in reason.upper()):
                await update_status(uid, "approved")
                await send_dynamic_template(uid, "approved_msg")
                success += 1
                await asyncio.sleep(0.05)
            else:
                failed += 1
                
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("« Back to Panel", callback_data="admin_panel")]])
        await query.message.edit_text(f"✅ **Accept All Finished**\n\nApproved: {success}\nFailed: {failed}", reply_markup=buttons, parse_mode=ParseMode.MARKDOWN)
        return
# ================= RUN =================
async def main():
    global user_app
    await app.start()
    
    me = await app.get_me()
    bot_username = me.username
    await init_db(bot_username)
    logger.info(f"Bot started as @{bot_username}")

    # Set default admin link if not configured yet
    current_link = await get_bot_setting("admin_contact_link", None)
    if not current_link:
        default_link = "https://t.me/Pronyte"
        try:
            admin_user = await app.get_users(ADMIN_IDS[0])
            if admin_user.username:
                default_link = f"https://t.me/{admin_user.username}"
        except Exception as e:
            logger.warning(f"Could not resolve admin username on startup: {e}")
        await set_bot_setting("admin_contact_link", default_link)
        logger.info(f"Initialized default admin contact link to: {default_link}")
    
    for cid in (TEMPLATE_CHANNEL_ID, CHANNEL_ID):
        try:
            await app.get_chat(cid)
        except Exception:
            pass
    logger.info("Bot peer cache warmed up.")
    
    if user_app:
        try:
            await user_app.start()
            logger.info("User session started successfully.")
        except Exception as e:
            logger.warning(f"Failed to start User session: {e}")
            logger.warning("The STRING_SESSION provided appears to be invalid or from an older version of Pyrogram (v1).")
            logger.warning("The bot will continue running using ONLY the regular Bot API.")
            user_app = None

    scheduler.start()
    await check_and_schedule_pending_transitions()
    logger.info("Scheduler started successfully.")

    from pyrogram import idle
    await idle()
    
    await app.stop()
    if user_app:
        await user_app.stop()

if __name__ == "__main__":
    logger.info("Starting Advanced Bot...")
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
