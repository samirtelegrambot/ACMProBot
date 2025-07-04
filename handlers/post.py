from telegram import Update
from telegram.ext import ContextTypes
from utils.keyboard import confirm_post_keyboard, main_menu_keyboard
from config.manager import ConfigManager
from constants.emoji import Emoji

config = ConfigManager()

async def post_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{Emoji.POST} Post Menu:\n- Preview batch\n- Post batch to channels", reply_markup=main_menu_keyboard())

async def preview_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "batch_messages" not in context.user_data or not context.user_data["batch_messages"]:
        await update.message.reply_text(f"{Emoji.INFO} No messages in batch to preview. Add messages using the Batch menu.")
        return

    messages = "\n".join(context.user_data["batch_messages"])
    await update.message.reply_text(f"{Emoji.POST} Preview of your post:\n\n{messages}\n\nDo you want to post this?", reply_markup=confirm_post_keyboard())

async def execute_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_post":
        if "batch_messages" not in context.user_data or not context.user_data["batch_messages"]:
            await query.edit_message_text(f"{Emoji.ERROR} No messages in batch to post.")
            return

        messages = context.user_data["batch_messages"]
        channels = config.get_fixed_channels()

        if not channels:
            await query.edit_message_text(f"{Emoji.WARNING} No channels configured. Please add channels first.")
            return

        success_count = 0
        for channel in channels:
            try:
                for message in messages:
                    await context.bot.send_message(chat_id=channel["id"], text=message)
                success_count += 1
            except Exception as e:
                await query.message.reply_text(f"{Emoji.ERROR} Failed to send to {channel["name"]} ({channel["id"]}): {e}")

        if success_count > 0:
            await query.edit_message_text(f"{Emoji.SUCCESS} Successfully posted to {success_count} channel(s).")
            context.user_data["batch_messages"] = [] # Clear batch after successful post
        else:
            await query.edit_message_text(f"{Emoji.ERROR} No posts were successful.")

    elif query.data == "cancel_post":
        await query.edit_message_text(f"{Emoji.INFO} Post cancelled.")

    await query.message.reply_text("Returning to main menu.", reply_markup=main_menu_keyboard())


