import logging
import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions.bad_request_400 import ChannelInvalid, ChatAdminRequired, UsernameInvalid, UsernameNotModified
from info import ADMINS
from info import INDEX_REQ_CHANNEL as LOG_CHANNEL
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    if query.data.startswith('index_cancel'):
        temp.CANCEL = True
        return await query.answer("Cancelling...")
    _, raju, chat, lst_msg_id, from_user = query.data.split("#")
    if raju == 'reject':
        await query.message.delete()
        await bot.send_message(int(from_user), f'Your Submission Has Been Rejected.', reply_to_message_id=int(lst_msg_id))
        return

    if lock.locked():
        return await query.answer('Wait until previous process completes.', show_alert=True)
    msg = query.message

    await query.answer('Processing... ⏳', show_alert=True)
    if int(from_user) not in ADMINS:
        await bot.send_message(int(from_user), f'Your Submission Has Been Accepted.', reply_to_message_id=int(lst_msg_id))
    await msg.edit(
        "Starting Indexing",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton('Cancel', callback_data='index_cancel')]]
        )
    )
    try:
        chat = int(chat)
    except:
        chat = chat
    await index_files_to_db(int(lst_msg_id), chat, msg, bot)


@Client.on_message((filters.forwarded | filters.regex(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z0-9_]+)/(\d+)")) & filters.private & filters.incoming)
async def send_for_index(bot, message):
    if message.text:
        regex = re.compile(r"(https://)?(t\.me/|telegram\.me/|telegram\.dog/)(c/)?(\d+|[a-zA-Z0-9_]+)/(\d+)")
        match = regex.match(message.text)
        if not match:
            return await message.reply('Invalid Link')
        chat_id = match.group(4)
        last_msg_id = int(match.group(5))
        if chat_id.isnumeric():
            chat_id = int("-100" + chat_id)
    elif message.forward_from_chat and message.forward_from_chat.type in [enums.ChatType.CHANNEL, enums.ChatType.SUPERGROUP, enums.ChatType.GROUP]:
        last_msg_id = message.forward_from_message_id
        chat_id = message.forward_from_chat.username or message.forward_from_chat.id
    else:
        return

    try:
        await bot.get_chat(chat_id)
    except ChannelInvalid:
        return await message.reply('This may be a private channel/group or I am not an admin there.')
    except Exception as e:
        logger.exception(e)
        return await message.reply(f'Error - {e}')

    try:
        k = await bot.get_messages(chat_id, last_msg_id)
    except:
        return await message.reply('Make Sure I am an Admin in the Channel/Group.')
    if k.empty:
        return await message.reply('This may be a private channel or I am not an admin there.')

    if message.from_user.id in ADMINS:
        buttons = [
            [
                InlineKeyboardButton('Yes', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')
            ],
            [
                InlineKeyboardButton('Close', callback_data='close_data')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        return await message.reply(
            f'Do you Want To Index This Channel/Group?\n\nChat ID/Username: `{chat_id}`\nLast Message ID: `{last_msg_id}`',
            reply_markup=reply_markup
        )
    else:
        buttons = [
            [
                InlineKeyboardButton('Accept Index', callback_data=f'index#accept#{chat_id}#{last_msg_id}#{message.from_user.id}')
            ],
            [
                InlineKeyboardButton('Reject Index', callback_data=f'index#reject#{chat_id}#{last_msg_id}#{message.from_user.id}')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await bot.send_message(
            LOG_CHANNEL,
            f'#IndexRequest\n\nBy: {message.from_user.mention}\nChat ID/Username: `{chat_id}`\nLast Message ID: `{last_msg_id}`',
            reply_markup=reply_markup
        )
        await message.reply('Thank You For the Contribution, Wait For Admins To Approve!')


@Client.on_message(filters.command('setskip') & filters.private)

async def set_skip_number(bot, message):
    if ' ' in message.text:
        _, skip = message.text.split(" ")
        try:
            skip = int(skip)
        except:
            return await message.reply("Skip number should be an integer.")
        await message.reply(f"Successfully set SKIP number to {skip}")
        temp.CURRENT = int(skip)
    else:
        await message.reply("Give me a skip number")


async def index_files_to_db(lst_msg_id, chat, msg, bot):
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    async for message in bot.iter_messages(chat, lst_msg_id, temp.CURRENT):
        if temp.CANCEL:
            await msg.edit(f"Successfully Cancelled Indexing.")
            break
        if message.empty:
            deleted += 1
            continue
        elif not message.media:
            no_media += 1
            continue
        elif message.media.value not in [enums.MediaType.DOCUMENT, enums.MediaType.VIDEO, enums.MediaType.AUDIO]:
            unsupported += 1
            continue
        media = getattr(message, message.media.value, None)
        if not media:
            unsupported += 1
            continue
        media.file_type = message.media.value
        media.caption = message.caption
        aynav, vnay = await save_file(media)
        if aynav:
            total_files += 1
        elif vnay == 0:
            duplicate += 1
        elif vnay == 2:
            errors += 1
    await msg.edit(f"Total files fetched: {total_files}\nDuplicates: {duplicate}\nErrors: {errors}\nDeleted: {deleted}\nNo Media: {no_media}\nUnsupported: {unsupported}")

