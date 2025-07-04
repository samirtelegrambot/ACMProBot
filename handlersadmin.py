from telegram import Update
from telegram.ext import ContextTypes
from config.manager import ConfigManager
from utils.keyboard import main_menu_keyboard
from constants.emoji import Emoji

config = ConfigManager()

async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in config.get_admin_ids():
        await update.message.reply_text(f"{Emoji.WARNING} You are not authorized to access this menu.")
        return
    await update.message.reply_text("Admin Menu:\n- Add/Remove Admins\n- View Bot Stats", reply_markup=main_menu_keyboard())

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in config.get_admin_ids():
        await update.message.reply_text(f"{Emoji.WARNING} You are not authorized to access this function.")
        return
    # Logic to add admin
    await update.message.reply_text("Send me the user ID to add as admin.")

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in config.get_admin_ids():
        await update.message.reply_text(f"{Emoji.WARNING} You are not authorized to access this function.")
        return
    # Logic to remove admin
    await update.message.reply_text("Send me the user ID to remove from admins.")

async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in config.get_admin_ids():
        await update.message.reply_text(f"{Emoji.WARNING} You are not authorized to access this function.")
        return
    # Logic to show bot stats
    await update.message.reply_text("Bot Stats: (Not implemented yet)")


