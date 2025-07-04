from telegram import Update
from telegram.ext import ContextTypes
from utils.keyboard import schedule_options_keyboard, main_menu_keyboard
from utils.formatting import format_timestamp
from constants.emoji import Emoji

async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"{Emoji.SCHEDULE} Schedule Menu:", reply_markup=schedule_options_keyboard())

async def view_scheduled_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    jobs = context.job_queue.get_jobs_by_name("scheduled_post")
    if not jobs:
        await query.edit_message_text(f"{Emoji.INFO} No scheduled posts.")
        return

    message_text = f"{Emoji.SCHEDULE} Scheduled Posts:\n\n"
    for job in jobs:
        message_text += f"- At {format_timestamp(job.data["time"])}: {job.data["text"][:50]}...\n"
    await query.edit_message_text(message_text)

async def schedule_new_post_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Please send the message you want to schedule.")
    context.user_data["awaiting_scheduled_message"] = True

async def receive_scheduled_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_scheduled_message"):
        return
    context.user_data["scheduled_message_text"] = update.message.text
    await update.message.reply_text("Now, please send the time for scheduling in HH:MM format (e.g., 14:30).")
    context.user_data["awaiting_scheduled_time"] = True
    context.user_data["awaiting_scheduled_message"] = False

async def receive_scheduled_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_scheduled_time"):
        return

    from utils.validators import is_valid_time_format
    time_str = update.message.text

    if not is_valid_time_format(time_str):
        await update.message.reply_text(f"{Emoji.ERROR} Invalid time format. Please use HH:MM (e.g., 14:30).")
        return

    import datetime
    from pytz import timezone

    try:
        h, m = map(int, time_str.split(":"))
        now = datetime.datetime.now(timezone("Asia/Kolkata")) # Assuming IST for now
        schedule_time = now.replace(hour=h, minute=m, second=0, microsecond=0)

        if schedule_time < now:
            schedule_time += datetime.timedelta(days=1)

        message_text = context.user_data.get("scheduled_message_text")
        if not message_text:
            await update.message.reply_text(f"{Emoji.ERROR} No message found to schedule. Please start over.", reply_markup=main_menu_keyboard())
            return

        context.job_queue.run_once(send_scheduled_post, schedule_time, data={
            "text": message_text,
            "time": schedule_time.timestamp(),
            "chat_id": update.message.chat_id
        }, name="scheduled_post")

        await update.message.reply_text(f"{Emoji.SUCCESS} Post scheduled for {schedule_time.strftime("%Y-%m-%d %H:%M:%S")}", reply_markup=main_menu_keyboard())

    except Exception as e:
        await update.message.reply_text(f"{Emoji.ERROR} An error occurred: {e}", reply_markup=main_menu_keyboard())

    context.user_data["awaiting_scheduled_message"] = False
    context.user_data["awaiting_scheduled_time"] = False
    context.user_data.pop("scheduled_message_text", None)

async def send_scheduled_post(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    message_text = job_data["text"]
    # In a real scenario, you'd send this to a channel
    # For now, we'll just log it or send it back to the user who scheduled it
    await context.bot.send_message(chat_id=context.job.chat_id, text=f"{Emoji.POST} Scheduled post: {message_text}")


