import os
import logging
import random
import asyncio
from validators import domain
from Script import script
from plugins.dbusers import db
from pyrogram import Client, filters, enums
from plugins.users_api import get_user, update_user_info
from plugins.database import get_file_details
from pyrogram.errors import *
from pyrogram.types import *
from utils import verify_user, check_token, check_verification, get_token
from config import *
import re
import json
import base64
from urllib.parse import quote_plus
from TechVJ.utils.file_properties import get_name, get_hash, get_media_file_size

logger = logging.getLogger(__name__)

BATCH_FILES = {}

async def is_subscribed(bot, query, channel):
    btn = []
    for id in channel:
        chat = await bot.get_chat(int(id))
        try:
            await bot.get_chat_member(id, query.from_user.id)
        except UserNotParticipant:
            btn.append([InlineKeyboardButton(f'Join {chat.title}', url=chat.invite_link)])
        except Exception as e:
            pass
    return btn

def get_size(size):
    """Get size in readable format"""
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units):
        i += 1
        size /= 1024.0
    return "%.2f %s" % (size, units[i])

@Client.on_message(filters.command("start") & filters.incoming)
async def start(client, message):
    if AUTH_CHANNEL:
        try:
            btn = await is_subscribed(client, message, AUTH_CHANNEL)
            if btn:
                username = (await client.get_me()).username
                if message.command[1]:
                    btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start={message.command[1]}")])
                else:
                    btn.append([InlineKeyboardButton("♻️ Try Again ♻️", url=f"https://t.me/{username}?start=true")])
                await message.reply_text(
                    text=f"<b>👋 Hello {message.from_user.mention},\n\nPlease join the channel then click on try again button. 😇</b>", 
                    reply_markup=InlineKeyboardMarkup(btn)
                )
                return
        except Exception as e:
            print(e)
    
    username = (await client.get_me()).username
    if not await db.is_user_exist(message.from_user.id):
        await db.add_user(message.from_user.id, message.from_user.first_name)
        await client.send_message(LOG_CHANNEL, script.LOG_TEXT.format(message.from_user.id, message.from_user.mention))

    if len(message.command) != 2:
        return  # Ignore if command doesn't have a file ID
    
    data = message.command[1]
    try:
        pre, file_id = data.split('_', 1)
    except:
        file_id = data
        pre = ""

    # 🔥 Single File Delivery Fix (Auto-Delete & Proper Sending)
    file_data = await get_file_details(file_id)
    if file_data:
        caption = file_data.get("caption", "")

        # Replace Old Link with New Link in Caption
        caption = caption.replace("https://t.me/Excellerators", "https://t.me/dramebaazbatman")

        sent_message = await client.send_cached_media(
            chat_id=message.from_user.id,
            file_id=file_data["file_id"],
            caption=caption,
            protect_content=True if pre == 'filep' else False,
        )

        # 🔥 Auto-Delete Single File After 2 Minutes (With Warning Message)
        if AUTO_DELETE_MODE:
            warning_message = await client.send_message(
                chat_id=message.from_user.id,
                text=f"<b>⚠️ This file will be deleted in {AUTO_DELETE} minutes. You Are Requested to Forward The File to Saved Messages.</b>"
            )
            await asyncio.sleep(AUTO_DELETE_TIME)
            try:
                await sent_message.delete()
                await warning_message.edit_text("<b>🗑 File deleted successfully! You are Always welcomed to Request Again</b>")
            except:
                pass
        return

    # 🔥 Batch File Handling (Fix Auto-Delete Message)
    if data.split("-", 1)[0] == "BATCH":
        sts = await message.reply("**🔺 Please wait...**")
        file_id = data.split("-", 1)[1]
        msgs = BATCH_FILES.get(file_id)
        if not msgs:
            file = await client.download_media(file_id)
            try: 
                with open(file) as file_data:
                    msgs=json.loads(file_data.read())
            except:
                await sts.edit("FAILED")
                return await client.send_message(LOG_CHANNEL, "UNABLE TO OPEN FILE.")
            os.remove(file)
            BATCH_FILES[file_id] = msgs
            
        filesarr = []
        for msg in msgs:
            title = msg.get("title")
            size = get_size(int(msg.get("size", 0)))
            f_caption = msg.get("caption", "")

            # Replace Old Link with New Link in Caption
            f_caption = f_caption.replace("https://t.me/Excellerators", "https://t.me/dramebaazbatman")

            if f_caption is None:
                f_caption = f"{title}"
            
            try:
                msg = await client.send_cached_media(
                    chat_id=message.from_user.id,
                    file_id=msg.get("file_id"),
                    caption=f_caption,
                    protect_content=msg.get('protect', False),
                )
                filesarr.append(msg)
                
            except FloodWait as e:
                await asyncio.sleep(e.x)
                msg = await client.send_cached_media(
                    chat_id=message.from_user.id,
                    file_id=msg.get("file_id"),
                    caption=f_caption,
                    protect_content=msg.get('protect', False),
                )
                filesarr.append(msg)
            except Exception as e:
                logger.warning(e, exc_info=True)
                continue
            await asyncio.sleep(1) 
        await sts.delete()

        # 🔥 Auto-Delete Batch Files After 2 Minutes (With Warning Message)
        if AUTO_DELETE_MODE:
            warning_message = await client.send_message(
                chat_id=message.from_user.id,
                text=f"<b>⚠️ These files will be deleted in {AUTO_DELETE} minutes. Please save them or send them to some other chat.</b>"
            )
            await asyncio.sleep(AUTO_DELETE_TIME)
            for x in filesarr:
                try:
                    await x.delete()
                except:
                    pass
            await warning_message.edit_text("<b>🗑 Files deleted successfully!</b>")
        return
