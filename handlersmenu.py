from telegram import Update
from telegram.ext import ContextTypes
from utils.keyboard import main_menu_keyboard

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome to the Telegram Bot! Use the menu below to navigate.", reply_markup=main_menu_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("This bot helps you manage channels, schedule posts, and more. Use the menu buttons to explore features.", reply_markup=main_menu_keyboard())

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Returning to main menu.", reply_markup=main_menu_keyboard())


