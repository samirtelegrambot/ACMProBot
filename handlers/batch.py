from telegram import Update
from telegram.ext import ContextTypes
from utils.keyboard import main_menu_keyboard
from constants.emoji import Emoji

async def batch_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{Emoji.BATCH} Batch Menu:\n- Collect messages\n- Clear batch\n- Show batch content", reply_markup=main_menu_keyboard())

async def collect_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Logic to collect messages into a batch
    if "batch_messages" not in context.user_data:
        context.user_data["batch_messages"] = []
    context.user_data["batch_messages"].append(update.message.text)
    await update.message.reply_text(f"{Emoji.SUCCESS} Message added to batch. Current batch size: {len(context.user_data["batch_messages"])}")

async def clear_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Logic to clear the batch
    if "batch_messages" in context.user_data:
        context.user_data["batch_messages"] = []
        await update.message.reply_text(f"{Emoji.SUCCESS} Batch cleared.")
    else:
        await update.message.reply_text(f"{Emoji.INFO} Batch is already empty.")

async def show_batch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Logic to show batch content
    if "batch_messages" in context.user_data and context.user_data["batch_messages"]:
        messages = "\n".join(context.user_data["batch_messages"])
        await update.message.reply_text(f"{Emoji.BATCH} Current batch messages:\n\n{messages}")
    else:
        await update.message.reply_text(f"{Emoji.INFO} Batch is empty.")


