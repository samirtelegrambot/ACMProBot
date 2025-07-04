import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config.manager import ConfigManager
from handlers.admin import admin_menu, add_admin, remove_admin, bot_stats
from handlers.channel import channel_menu, add_channel_prompt, handle_channel_input, manage_channel, remove_channel, back_to_channels
from handlers.batch import batch_menu, collect_message, clear_batch, show_batch
from handlers.schedule import schedule_menu, view_scheduled_posts, schedule_new_post_prompt, receive_scheduled_message, receive_scheduled_time
from handlers.post import post_menu, preview_post, execute_post
from handlers.menu import start, help_command, back_to_main_menu
from handlers.settings import settings_menu, set_delay_prompt, receive_delay_input, set_retry_prompt, receive_retry_input, set_footer_prompt, receive_footer_input

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    config = ConfigManager()
    bot_token = config.get_bot_token()

    if not bot_token:
        logger.error("BOT_TOKEN not found in .env file. Please set it.")
        return

    application = Application.builder().token(bot_token).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Message Handlers
    application.add_handler(MessageHandler(filters.Regex("^Admin$"), admin_menu))
    application.add_handler(MessageHandler(filters.Regex("^Channels$"), channel_menu))
    application.add_handler(MessageHandler(filters.Regex("^Batch$"), batch_menu))
    application.add_handler(MessageHandler(filters.Regex("^Schedule$"), schedule_menu))
    application.add_handler(MessageHandler(filters.Regex("^Post$"), post_menu))
    application.add_handler(MessageHandler(filters.Regex("^Settings$"), settings_menu))
    application.add_handler(MessageHandler(filters.Regex("^Back to Main Menu$"), back_to_main_menu))

    # Channel Management Handlers
    application.add_handler(CallbackQueryHandler(add_channel_prompt, pattern="^add_channel$"))
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL | filters.TEXT & filters.User(config.get_admin_ids()), handle_channel_input))
    application.add_handler(CallbackQueryHandler(manage_channel, pattern="^channel_\\d+$"))
    application.add_handler(CallbackQueryHandler(remove_channel, pattern="^remove_channel_\\d+$"))
    application.add_handler(CallbackQueryHandler(back_to_channels, pattern="^back_to_channels$"))

    # Batch Management Handlers
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(config.get_admin_ids()) & filters.Context(lambda ctx: ctx.user_data.get("awaiting_batch_message")), collect_message))
    application.add_handler(CommandHandler("clear_batch", clear_batch))
    application.add_handler(CommandHandler("show_batch", show_batch))

    # Schedule Management Handlers
    application.add_handler(CallbackQueryHandler(view_scheduled_posts, pattern="^view_scheduled$"))
    application.add_handler(CallbackQueryHandler(schedule_new_post_prompt, pattern="^schedule_new$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(config.get_admin_ids()) & filters.Context(lambda ctx: ctx.user_data.get("awaiting_scheduled_message")), receive_scheduled_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(config.get_admin_ids()) & filters.Context(lambda ctx: ctx.user_data.get("awaiting_scheduled_time")), receive_scheduled_time))

    # Post Management Handlers
    application.add_handler(CommandHandler("preview_post", preview_post))
    application.add_handler(CallbackQueryHandler(execute_post, pattern="^(confirm_post|cancel_post)$



    # Settings Handlers
    application.add_handler(CallbackQueryHandler(set_delay_prompt, pattern="^set_delay$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(config.get_admin_ids()) & filters.Context(lambda ctx: ctx.user_data.get("awaiting_delay_input")), receive_delay_input))
    application.add_handler(CallbackQueryHandler(set_retry_prompt, pattern="^set_retry$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(config.get_admin_ids()) & filters.Context(lambda ctx: ctx.user_data.get("awaiting_retry_input")), receive_retry_input))
    application.add_handler(CallbackQueryHandler(set_footer_prompt, pattern="^set_footer$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.User(config.get_admin_ids()) & filters.Context(lambda ctx: ctx.user_data.get("awaiting_footer_input")), receive_footer_input))

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()


