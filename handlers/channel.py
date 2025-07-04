import os
from telegram import Update
from telegram.ext import ContextTypes
from config.manager import ConfigManager
from utils.keyboard import channel_list_keyboard, channel_manage_keyboard, main_menu_keyboard
from utils.validators import is_valid_channel_id
from constants.emoji import Emoji

config = ConfigManager()

async def channel_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = config.get_fixed_channels()
    if not channels:
        await update.message.reply_text(f"{Emoji.INFO} No channels added yet. Use 'Add Channel' to add one.", reply_markup=channel_list_keyboard(channels))
    else:
        await update.message.reply_text(f"{Emoji.CHANNEL} Your channels:", reply_markup=channel_list_keyboard(channels))

async def add_channel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Please forward a message from the channel or send the channel ID.")
    context.user_data["awaiting_channel_id"] = True

async def handle_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_channel_id"):
        return

    channel_id = None
    channel_name = ""

    if update.channel_post:
        channel_id = update.channel_post.chat.id
        channel_name = update.channel_post.chat.title
    elif update.message and update.message.text:
        try:
            channel_id = int(update.message.text)
            # Attempt to get channel name if possible, otherwise leave empty
            try:
                chat = await context.bot.get_chat(channel_id)
                channel_name = chat.title
            except Exception:
                channel_name = f"Unknown Channel ({channel_id})"
        except ValueError:
            await update.message.reply_text(f"{Emoji.ERROR} Invalid channel ID. Please send a valid integer ID or forward a message from the channel.")
            return

    if channel_id and is_valid_channel_id(channel_id):
        config.add_fixed_channel(channel_id, channel_name)
        await update.message.reply_text(f"{Emoji.SUCCESS} Channel \'{channel_name}\' ({channel_id}) added successfully!", reply_markup=main_menu_keyboard())
        context.user_data["awaiting_channel_id"] = False
    else:
        await update.message.reply_text(f"{Emoji.ERROR} Invalid channel. Please ensure it's a supergroup or channel and the bot is an administrator.")

async def manage_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channel_id = int(query.data.split("_")[1])
    channels = config.get_fixed_channels()
    channel_info = next((c for c in channels if c["id"] == channel_id), None)
    if channel_info:
        await query.edit_message_text(f"Managing channel: {channel_info["name"]} ({channel_info["id"]})", reply_markup=channel_manage_keyboard(channel_id))
    else:
        await query.edit_message_text(f"{Emoji.ERROR} Channel not found.", reply_markup=main_menu_keyboard())

async def remove_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    channel_id = int(query.data.split("_")[1])
    config.remove_fixed_channel(channel_id)
    await query.edit_message_text(f"{Emoji.SUCCESS} Channel ({channel_id}) removed.", reply_markup=main_menu_keyboard())
    await channel_menu(update, context)

async def back_to_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await channel_menu(update, context)


