import os
import asyncio
import nest_asyncio
import subprocess
import requests
import re
import time
import math
import shutil
import signal
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from pyrogram.errors import FloodWait
# --- KEEP ALIVE IMPORTS ---
from flask import Flask
from threading import Thread

# Flask Server for Render
flask_app = Flask('')
@flask_app.route('/')
def home():
    return "Bot is Running 24/7"

def run_flask():
    flask_app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

nest_asyncio.apply()

# --- CONFIG ---
API_ID = 32799376
API_HASH = "e193a0d9f0d2e422658a18447fa94d34" 
BOT_TOKEN = "8673149752:AAGdxrH3CKeqLLONJPdOcZY_TFKPcJrU0CY"

# YAHAN APNI ID DALO
OWNER_ID = 8538043097
SUDO_USERS = [OWNER_ID, 987654321] 

# Workers set to 300 for extreme concurrency
app = Client("VividUploaderPremium", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=300)
users = {}
running_tasks = {}
active_processes = {} # Strictly for cancelling background tasks

# ================= AUTH CHECK =================

def is_auth(message):
    user = message.from_user
    if user:
        return user.id in SUDO_USERS
    return False

# ================= UTILITIES =================

async def progress_bar(current, total, status_msg, topic, start_time, file_count_info, chat_id):
    # Strictly stop uploading progress if cancelled
    if not running_tasks.get(chat_id):
        raise Exception("Task Cancelled")
        
    now = time.time()
    diff = now - start_time
    if round(diff % 5.0) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = round((total - current) / speed) * 1000 if speed > 0 else 0
        bar_length = 15
        filled_length = int(bar_length * current / total)
        bar = '⚡' * filled_length + '░' * (bar_length - filled_length)
        progress_str = (
            f"📡 **𝗨𝗣𝗟𝗢𝗔𝗗𝗜𝗡𝗚 𝗜𝗡 𝗣𝗥𝗢𝗚𝗥𝗘𝗦𝗦...**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📂 **𝗙𝗶𝗹𝗲:** `{topic}`\n"
            f"🔢 **𝗜𝗻𝗱𝗲𝘅:** `{file_count_info}`\n\n"
            f"📊 **𝗕𝗮𝗿:** {bar} {percentage:.2f}%\n"
            f"🚀 **𝗦𝗽𝗲𝗲𝗱:** `{humanbytes(speed)}/s`\n"
            f"📦 **𝗦𝗶𝘇𝗲:** `{humanbytes(current)}` / `{humanbytes(total)}`\n"
            f"⏳ **𝗘𝗧𝗔:** `{time_formatter(eta)}`"
        )
        try: await status_msg.edit_text(progress_str)
        except: pass

def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0: return f"{size:.2f} {unit}"
        size /= 1024.0

def time_formatter(milliseconds: int) -> str:
    seconds, milliseconds = divmod(int(milliseconds), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    tmp = ((str(hours) + "h ") if hours else "") + \
          ((str(minutes) + "m ") if minutes else "") + \
          ((str(seconds) + "s") if seconds else "")
    return tmp if tmp else "0s"

async def update_status(status_msg, text):
    try: await status_msg.edit_text(text)
    except FloodWait as e: await asyncio.sleep(e.value)
    except: pass

def get_video_info(file_path):
    try:
        dur_cmd = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{file_path}"'
        duration = int(float(subprocess.check_output(dur_cmd, shell=True).decode().strip()))
        thumb_path = f"{file_path}.jpg"
        thumb_cmd = f'ffmpeg -y -i "{file_path}" -ss 00:00:05 -vframes 1 "{thumb_path}"'
        subprocess.run(thumb_cmd, shell=True, capture_output=True)
        return duration, thumb_path
    except: return 0, None

def clean_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name).replace(" ", "_")

# ================= COMMANDS =================

@app.on_message(filters.command("start"))
async def start_cmd(_, message):
    if not is_auth(message):
        return await message.reply_text("❌ **Access Denied.**")
    
    desc = (
        "⚡ **𝗩𝗜𝗩𝗜𝗗 𝗧𝗫𝗧 𝗨𝗣𝗟𝗢𝗔𝗗𝗘𝗥 𝘃𝟯.𝟱**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "◈ **Mode:** Turbo Multi-Tasking\n"
        "◈ **Downloader:** Aria2c Turbo\n"
        "◈ **Status:** Authorized ✅\n\n"
        "📥 **Send me a .txt file.**"
    )
    await message.reply_text(desc)

@app.on_message(filters.command("id"))
async def get_id(_, message):
    await message.reply_text(f"🆔 **ID:** `{message.chat.id}`")

@app.on_message(filters.command("cancel"))
async def cancel_cmd(_, message):
    if not is_auth(message): return
    chat_id = message.chat.id
    if chat_id in running_tasks:
        running_tasks[chat_id] = False
        # STRICT KILL: Kill the background yt-dlp/aria2c process
        if chat_id in active_processes:
            try:
                active_processes[chat_id].terminate()
                active_processes[chat_id].kill()
            except: pass
        await message.reply_text("🛑 **𝗣𝗥𝗢𝗖𝗘𝗦𝗦 𝗧𝗘𝗥𝗠𝗜𝗡𝗔𝗧𝗘𝗗.**")
    else:
        await message.reply_text("⚠️ **No active task here.**")

# ================= TXT HANDLING =================

@app.on_message(filters.document)
async def handle_txt(_, message):
    if not is_auth(message): return
    if not message.document.file_name.endswith(".txt"): return
    
    chat_id = message.chat.id
    path = await message.download()
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    links = [l.strip() for l in content.splitlines() if "http" in l]
    vids = len([l for l in links if any(x in l.lower() for x in [".m3u8", ".mp4", "youtu"])])
    pdfs = len([l for l in links if ".pdf" in l.lower()])
    users[chat_id] = {"links": links, "step": "index", "total_v": vids, "total_p": pdfs, "trash": [message.id, path]}
    msg = await message.reply_text(f"📊 **𝗗𝗔𝗧𝗔 𝗔𝗡𝗔𝗟𝗬𝗦𝗜𝗦**\n━━━━━━━━━━━━━━━━━━━━━━\n✅ **𝗧𝗼𝘁𝗮𝗹:** `{len(links)}` \n📹 **𝗩𝗶𝗱𝗲𝗼𝘀:** `{vids}` \n📄 **𝗣𝗗𝗙𝘀:** `{pdfs}`\n\n🔢 **𝗘𝗻𝘁𝗲𝗿 𝘀𝘁𝗮𝗿𝘁𝗶𝗻𝗴 𝗶𝗻𝗱𝗲𝘅:**")
    users[chat_id]["trash"].append(msg.id)

# ================= INPUT STEPS =================

@app.on_message((filters.text | filters.photo) & ~filters.command(["start", "cancel", "id"]))
async def steps_handler(_, message):
    if not is_auth(message): return
    chat_id = message.chat.id
    if chat_id not in users: return
    state = users[chat_id]
    state["trash"].append(message.id)
    
    if state["step"] == "index":
        try:
            state["index"] = int(message.text)
            state["step"] = "batch"; msg = await message.reply_text("📚 **𝗘𝗻𝘁𝗲𝗿 𝗖𝗼𝘂𝗿𝘀𝗲 𝗡𝗮𝗺𝗲:**")
            state["trash"].append(msg.id)
        except: await message.reply_text("❌ **Send an integer.**")
    elif state["step"] == "batch":
        state["batch"] = message.text; state["step"] = "extracted"
        msg = await message.reply_text("📤 **𝗘𝗻𝘁𝗲𝗿 '𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗲𝗱 𝗕𝘆' 𝗡𝗮𝗺𝗲:**")
        state["trash"].append(msg.id)
    elif state["step"] == "extracted":
        state["extracted"] = message.text; state["step"] = "quality"
        kb = ReplyKeyboardMarkup([["360p", "480p"], ["720p", "1080p"]], resize_keyboard=True)
        msg = await message.reply_text("⚙️ **𝗦𝗲𝗹𝗲𝗰𝘁 𝗥𝗲𝘀𝗼𝗹𝘂𝘁𝗶𝗼𝘁𝗻:**", reply_markup=kb)
        state["trash"].append(msg.id)
    elif state["step"] == "quality":
        state["quality"] = message.text.replace("p", ""); state["step"] = "thumb"
        msg = await message.reply_text("🖼 **𝗨𝗽𝗹𝗼𝗮𝗱 𝗖𝘂𝘀𝘁𝗼𝗺 𝗧𝗵𝘂𝗺𝗯𝗻𝗮𝗶𝗹** or 'no':", reply_markup=ReplyKeyboardRemove())
        state["trash"].append(msg.id)
    elif state["step"] == "thumb":
        if message.photo: state["thumb"] = await message.download(file_name=f"thumb_{chat_id}.jpg")
        else: state["thumb"] = None
        for m_id in state["trash"]:
            try: 
                if isinstance(m_id, int): await app.delete_messages(chat_id, m_id)
                else: os.remove(m_id)
            except: pass
        running_tasks[chat_id] = True
        asyncio.create_task(process_files(chat_id))

# ================= CORE ENGINE =================

async def process_files(chat_id):
    state = users[chat_id]; all_links = state["links"]; start_idx = state["index"]
    links_to_process = all_links[start_idx-1:]; total_to_process = len(links_to_process)
    curr_idx = start_idx; custom_thumb = state["thumb"]; chosen_quality = state["quality"]
    status = await app.send_message(chat_id, "⚙️ **𝗜𝗡𝗜𝗧𝗜𝗔𝗧𝗜𝗡𝗚 𝗦𝗘𝗤𝗨𝗘𝗡𝗖𝗘...**")

    for i, line in enumerate(links_to_process, start=1):
        if not running_tasks.get(chat_id): break
        
        if os.path.exists(f"downloads_{chat_id}"): shutil.rmtree(f"downloads_{chat_id}", ignore_errors=True)

        try:
            if ":" in line and "http" in line:
                parts = line.split(":", 1); topic = parts[0].strip()
                url = re.search(r'http\S+', parts[1]).group()
            else: topic = f"File_{curr_idx}"; url = re.search(r'http\S+', line).group()
        except: curr_idx += 1; continue

        file_count_info = f"{i}/{total_to_process}"
        await update_status(status, f"🛰 **𝗗𝗢𝗪𝗡𝗟𝗢𝗔𝗗𝗜𝗡𝗚 ({file_count_info})**\n📂 `{topic}`")
        
        safe_topic = clean_filename(topic)
        video_filename = f"{safe_topic}_vivid.mp4"
        pdf_filename = f"{safe_topic}_vivid.pdf"
        cap = (f"📙 **Index :** `{curr_idx}`\n\n📝 **Topic :** `{topic}`\n\n📚 **COURSE :-** `{state['batch']}`\n\n📤 **𝐄𝐗𝐓𝐑𝐀𝐂𝐓𝐄𝐃 𝐁𝐘 : {state['extracted']}**")

        try:
            if any(x in url.lower() for x in [".jpg", ".png", ".jpeg"]):
                r = requests.get(url, timeout=30); img_path = f"{safe_topic}_vivid.jpg"
                with open(img_path, "wb") as f: f.write(r.content)
                await app.send_photo(chat_id, img_path, caption=cap); os.remove(img_path)
            elif ".pdf" in url.lower():
                r = requests.get(url, timeout=30)
                with open(pdf_filename, "wb") as f: f.write(r.content)
                await app.send_document(chat_id, pdf_filename, caption=cap, thumb=custom_thumb)
                if os.path.exists(pdf_filename): os.remove(pdf_filename)
            else:
                cmd = f'yt-dlp -f "bestvideo[height<={chosen_quality}]+bestaudio/best" --external-downloader aria2c --external-downloader-args "aria2c:-x 16 -s 16 -j 32 -k 1M --min-split-size=1M" --merge-output-format mp4 --no-check-certificate "{url}" -o "{video_filename}"'
                
                # Registering process for Strict Cancel
                process = await asyncio.create_subprocess_shell(cmd)
                active_processes[chat_id] = process
                await process.communicate()
                active_processes.pop(chat_id, None)
                
                if not running_tasks.get(chat_id): break # Double check after download

                if os.path.exists(video_filename):
                    dur, auto_thumb = get_video_info(video_filename)
                    final_thumb = custom_thumb if custom_thumb else auto_thumb
                    start_time = time.time()
                    
                    while True:
                        try:
                            # Pass chat_id to progress_bar for cancel check
                            await app.send_video(chat_id, video=video_filename, caption=cap, duration=dur, thumb=final_thumb, supports_streaming=True, progress=progress_bar, progress_args=(status, topic, start_time, file_count_info, chat_id))
                            break
                        except Exception as e:
                            if "Task Cancelled" in str(e): break
                            if isinstance(e, FloodWait): await asyncio.sleep(e.value)
                            else: break
                    
                    if os.path.exists(video_filename): os.remove(video_filename)
                    if auto_thumb and os.path.exists(auto_thumb): os.remove(auto_thumb)
                else: 
                    if running_tasks.get(chat_id): await app.send_message(chat_id, f"❌ **Failed:** {topic}")
        except Exception as e: 
            if running_tasks.get(chat_id): await app.send_message(chat_id, f"⚠️ **Error:** `{str(e)[:100]}`")
        
        curr_idx += 1

    if custom_thumb and os.path.exists(custom_thumb): os.remove(custom_thumb)
    try: await status.delete()
    except: pass
    if running_tasks.get(chat_id):
        await app.send_message(chat_id, "𝗧𝗵𝗮𝘁'𝘀 𝗶𝘁 ❤️")
    running_tasks.pop(chat_id, None)

async def main():
    keep_alive()
    await app.start()
    print("💎 VIVID TURBO CORE IS ONLINE (CANCEL FIXED)")
    await idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
