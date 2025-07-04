from telegram import Update
from telegram.ext import ContextTypes
from utils.keyboard import settings_keyboard, main_menu_keyboard
from constants.emoji import Emoji

# In a real application, these would be stored persistently (e.g., in a database)
# For this example, we'll use a simple dictionary in context.bot_data

async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{Emoji.SETTINGS} Settings Menu:", reply_markup=settings_keyboard())

async def set_delay_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send the desired delay in seconds for posting (e.g., 5).")
    context.user_data["awaiting_delay_input"] = True

async def receive_delay_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_delay_input"):
        return

    try:
        delay = int(update.message.text)
        if delay < 0:
            raise ValueError
        context.bot_data["post_delay"] = delay
        await update.message.reply_text(f"{Emoji.SUCCESS} Post delay set to {delay} seconds.", reply_markup=main_menu_keyboard())
    except ValueError:
        await update.message.reply_text(f"{Emoji.ERROR} Invalid input. Please enter a non-negative integer for delay.")
    finally:
        context.user_data["awaiting_delay_input"] = False

async def set_retry_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send the desired number of retry attempts (e.g., 3).")
    context.user_data["awaiting_retry_input"] = True

async def receive_retry_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_retry_input"):
        return

    try:
        retries = int(update.message.text)
        if retries < 0:
            raise ValueError
        context.bot_data["retry_attempts"] = retries
        await update.message.reply_text(f"{Emoji.SUCCESS} Retry attempts set to {retries}.", reply_markup=main_menu_keyboard())
    except ValueError:
        await update.message.reply_text(f"{Emoji.ERROR} Invalid input. Please enter a non-negative integer for retry attempts.")
    finally:
        context.user_data["awaiting_retry_input"] = False

async def set_footer_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send the text for the post footer. Send /clear_footer to remove it.")
    context.user_data["awaiting_footer_input"] = True

async def receive_footer_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_footer_input"):
        return

    footer_text = update.message.text
    if footer_text == "/clear_footer":
        context.bot_data["post_footer"] = ""
        await update.message.reply_text(f"{Emoji.SUCCESS} Post footer cleared.", reply_markup=main_menu_keyboard())
    else:
        context.bot_data["post_footer"] = footer_text
        await update.message.reply_text(f"{Emoji.SUCCESS} Post footer set.", reply_markup=main_menu_keyboard())
    context.user_data["awaiting_footer_input"] = False


