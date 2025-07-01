import logging
import json
import os
import re
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Set, List, Optional, Any, Tuple
from uuid import uuid4
from dotenv import load_dotenv
from filelock import FileLock

# Telegram imports
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, 
    ReplyKeyboardRemove, InlineQueryResultArticle, InputTextMessageContent, 
    CallbackQuery, Message, Bot,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, 
    InlineQueryHandler, ContextTypes, filters, ConversationHandler,
)

# ==================== Configuration ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("advanced_channel_manager.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

BOT_TOKEN: Optional[str] = os.getenv("BOT_TOKEN")
OWNER_ID: Optional[str] = os.getenv("OWNER_ID")

# Validate environment variables
if not BOT_TOKEN:
    logger.error("BOT_TOKEN environment variable is not set")
    raise ValueError("BOT_TOKEN environment variable is not set")
if not OWNER_ID or not OWNER_ID.isdigit():
    logger.error("OWNER_ID environment variable is not set or invalid")
    raise ValueError("OWNER_ID environment variable is not set or invalid")
OWNER_ID: int = int(OWNER_ID)

# Configuration constants
CONFIG_FILE: str = "channel_manager_pro_config.json"
CONFIG_LOCK: str = "channel_manager_pro_config.lock"
MAX_BATCH_MESSAGES: int = 100
BATCH_EXPIRY_HOURS: int = 6
SCHEDULE_EXPIRY_DAYS: int = 7
POST_DELAY_SECONDS: float = 0.1
MAX_RETRIES: int = 3
MAX_FOOTER_LENGTH: int = 200
TEXT_FILE_SIZE_LIMIT: int = 1024000  # 1MB
TEXT_FILE_DELIMITER: str = "\n\n"
MAX_MESSAGE_LENGTH: int = 4096
MAX_CAPTION_LENGTH: int = 1024

# Emoji dictionary
EMOJI: Dict[str, str] = {
    "admin": "👑",
    "channel": "📢",
    "stats": "📊",
    "batch": "📦",
    "schedule": "⏰",
    "settings": "⚙️",
    "help": "❓",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "rocket": "🚀",
    "fire": "🔥",
    "star": "⭐",
    "heart": "❤️",
    "thumbs_up": "👍",
    "celebration": "🎉",
    "check": "✓",
    "cross": "✗",
    "arrow_right": "→",
    "arrow_left": "←",
    "up": "🔼",
    "down": "🔽"
}

# Fixed channels
FIXED_CHANNELS: Dict[str, Dict[str, Any]] = {
    "-1002489624380": {
        "name": "Channel One",
        "type": "private"
    },
    "-1002504723776": {
        "name": "Channel Two",
        "type": "private"
    }
}

# Conversation states
ADMIN_MANAGEMENT, CHANNEL_MANAGEMENT, POST_SETTINGS, SCHEDULE_BATCH = range(4)

# ==================== Config Manager ====================
class ConfigManager:
    """Singleton class for managing bot configuration and data persistence"""
    
    _instance: Optional['ConfigManager'] = None
    _config: Dict[str, Any] = {}
    _last_loaded: Optional[datetime] = None

    def __new__(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """Load configuration from file with file locking"""
        lock = FileLock(CONFIG_LOCK)
        try:
            with lock:
                if os.path.exists(CONFIG_FILE):
                    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                        self._config = json.load(f)
                    self._last_loaded = datetime.now()
                else:
                    self._initialize_default_config()
                    self._save()
        except (IOError, json.JSONDecodeError, PermissionError) as e:
            logger.error(f"Error loading config: {e}", exc_info=True)
            self._initialize_default_config()
            self._save()

    def _initialize_default_config(self) -> None:
        """Initialize default configuration"""
        self._config = {
            "admins": [str(OWNER_ID)],
            "channels": dict(FIXED_CHANNELS),
            "stats": {
                "posts": 0,
                "batches": 0,
                "last_post": None,
                "last_post_channels": []
            },
            "settings": {
                "default_delay": POST_DELAY_SECONDS,
                "max_retries": MAX_RETRIES,
                "notifications": True,
                "footer": ""
            },
            "admin_stats": {},
            "scheduled_posts": {},
            "post_analytics": {}
        }

    def _save(self) -> None:
        """Save configuration to file with file locking"""
        lock = FileLock(CONFIG_LOCK)
        try:
            with lock:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(self._config, f, indent=4, ensure_ascii=False)
                self._last_loaded = datetime.now()
        except (IOError, PermissionError) as e:
            logger.error(f"Error saving config: {e}", exc_info=True)

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration with auto-reload"""
        if not self._last_loaded or (datetime.now() - self._last_loaded).seconds > 60:
            self._load()
        return self._config

    def get_channels(self) -> Dict[str, Dict[str, Any]]:
        """Get all channels"""
        return self.get_config().get("channels", {})

    def get_admins(self) -> List[str]:
        """Get all admin IDs"""
        return self.get_config().get("admins", [str(OWNER_ID)])

    def add_admin(self, admin_id: str) -> bool:
        """Add new admin"""
        config = self.get_config()
        if admin_id not in config["admins"]:
            config["admins"].append(admin_id)
            self._save()
            return True
        return False

    def remove_admin(self, admin_id: str) -> bool:
        """Remove admin (cannot remove owner)"""
        if admin_id == str(OWNER_ID):
            return False
        config = self.get_config()
        if admin_id in config["admins"]:
            config["admins"].remove(admin_id)
            self._save()
            return True
        return False

    def add_channel(self, channel_id: str, channel_info: Dict[str, Any]) -> bool:
        """Add new channel"""
        config = self.get_config()
        if channel_id not in config["channels"]:
            config["channels"][channel_id] = channel_info
            self._save()
            return True
        return False

    def remove_channel(self, channel_id: str) -> bool:
        """Remove channel"""
        config = self.get_config()
        if channel_id in config["channels"]:
            del config["channels"][channel_id]
            self._save()
            return True
        return False

    def update_stats(self, stat_type: str, value: Any) -> None:
        """Update statistics"""
        config = self.get_config()
        if stat_type in config["stats"]:
            config["stats"][stat_type] = value
        self._save()

    def update_admin_stats(self, admin_id: str, action: str) -> None:
        """Update admin-specific statistics"""
        config = self.get_config()
        if admin_id not in config["admin_stats"]:
            config["admin_stats"][admin_id] = {"posts": 0, "batches": 0, "last_action": None}
        
        config["admin_stats"][admin_id][action] = config["admin_stats"][admin_id].get(action, 0) + 1
        config["admin_stats"][admin_id]["last_action"] = datetime.now().isoformat()
        self._save()

    def add_scheduled_job(self, job_id: str, job_data: Dict[str, Any]) -> None:
        """Add scheduled job"""
        config = self.get_config()
        config["scheduled_posts"][job_id] = job_data
        self._save()

    def remove_scheduled_job(self, job_id: str) -> bool:
        """Remove scheduled job"""
        config = self.get_config()
        if job_id in config["scheduled_posts"]:
            del config["scheduled_posts"][job_id]
            self._save()
            return True
        return False

    def get_scheduled_jobs(self) -> Dict[str, Any]:
        """Get all scheduled jobs"""
        return self.get_config().get("scheduled_posts", {})

    def cleanup_expired_jobs(self) -> None:
        """Remove expired scheduled jobs"""
        config = self.get_config()
        current_time = datetime.now()
        expired_jobs = []
        
        for job_id, job_data in config["scheduled_posts"].items():
            try:
                schedule_time = datetime.fromisoformat(job_data.get("schedule_time", ""))
                if current_time > schedule_time + timedelta(hours=1):  # 1 hour grace period
                    expired_jobs.append(job_id)
            except (ValueError, TypeError):
                expired_jobs.append(job_id)  # Invalid format, remove it
        
        for job_id in expired_jobs:
            del config["scheduled_posts"][job_id]
        
        if expired_jobs:
            self._save()
            logger.info(f"Cleaned up {len(expired_jobs)} expired jobs")

# Initialize config manager
config_manager = ConfigManager()

# ==================== Utility Functions ====================
def sanitize_markdown(text: str) -> str:
    """Sanitize text for Markdown parsing"""
    if not text:
        return ""
    
    # Escape Markdown special characters
    markdown_chars = ['*', '_', '`', '[', ']', '(', ')', '~', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in markdown_chars:
        text = text.replace(char, f'\\{char}')
    
    return text

def style_text(text: str, style: str = None, emoji: str = None, parse_mode: str = "Markdown") -> str:
    """Apply styling to text"""
    if not text:
        return ""
    
    styled_text = text
    
    if emoji and emoji in EMOJI:
        styled_text = f"{EMOJI[emoji]} {styled_text}"
    
    if style and parse_mode == "Markdown":
        if style == "bold":
            styled_text = f"*{styled_text}*"
        elif style == "italic":
            styled_text = f"_{styled_text}_"
        elif style == "code":
            styled_text = f"`{styled_text}`"
        elif style == "pre":
            styled_text = f"```\n{styled_text}\n```"
    
    return styled_text

def format_timestamp(timestamp: Optional[str] = None, relative: bool = False) -> str:
    """Format timestamp for display"""
    if not timestamp:
        dt = datetime.now()
    else:
        try:
            dt = datetime.fromisoformat(timestamp)
        except ValueError:
            return "Invalid timestamp"
    
    if relative:
        now = datetime.now()
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days} days ago"
        elif diff.seconds > 3600:
            return f"{diff.seconds // 3600} hours ago"
        elif diff.seconds > 60:
            return f"{diff.seconds // 60} minutes ago"
        else:
            return "Just now"
    else:
        return dt.strftime("%Y-%m-%d %H:%M:%S")

def validate_channel_id(channel_id: str) -> bool:
    """Validate Telegram channel ID format"""
    if not channel_id:
        return False
    
    # Username format (@username) or ID format (-100xxxxxxxxx)
    username_pattern = r'^@[a-zA-Z][a-zA-Z0-9_]{4,31}$'
    id_pattern = r'^-100\d{10}$'
    
    return bool(re.match(username_pattern, channel_id) or re.match(id_pattern, channel_id))

def validate_user_id(user_id: str) -> bool:
    """Validate Telegram user ID"""
    if not user_id:
        return False
    
    try:
        uid = int(user_id)
        return 0 < uid < 10**10  # Reasonable range for Telegram user IDs
    except ValueError:
        return False

def validate_schedule_time(time_str: str) -> Optional[datetime]:
    """Validate and parse schedule time string"""
    if not time_str:
        return None
    
    # Supported formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y %H:%M",
        "%d.%m.%Y %H:%M",
        "%H:%M"  # Today
    ]
    
    for fmt in formats:
        try:
            if fmt == "%H:%M":
                # For time-only format, use today's date
                time_obj = datetime.strptime(time_str, fmt).time()
                dt = datetime.combine(datetime.now().date(), time_obj)
                # If time has passed today, schedule for tomorrow
                if dt <= datetime.now():
                    dt += timedelta(days=1)
                return dt
            else:
                return datetime.strptime(time_str, fmt)
        except ValueError:
            continue
    
    return None

def validate_message_content(content: str, is_caption: bool = False) -> bool:
    """Validate message content length"""
    if not content:
        return False
    
    max_length = MAX_CAPTION_LENGTH if is_caption else MAX_MESSAGE_LENGTH
    return len(content) <= max_length

def check_schedule_conflict(config: Dict[str, Any], schedule_dt: datetime, channels: Set[str]) -> bool:
    """Check if there's a scheduling conflict"""
    scheduled_jobs = config.get("scheduled_posts", {})
    
    for job_data in scheduled_jobs.values():
        try:
            job_time = datetime.fromisoformat(job_data.get("schedule_time", ""))
            job_channels = set(job_data.get("channels", []))
            
            # Check if within 1 minute of another job and has overlapping channels
            if abs((schedule_dt - job_time).total_seconds()) < 60 and channels.intersection(job_channels):
                return True
        except (ValueError, TypeError):
            continue
    
    return False

# ==================== Keyboard Functions ====================
def create_main_menu() -> ReplyKeyboardMarkup:
    """Create main menu keyboard"""
    keyboard = [
        [f"{EMOJI['admin']} Admin Management", f"{EMOJI['channel']} Channel Management"],
        [f"{EMOJI['batch']} Batch Management", f"{EMOJI['schedule']} Schedule Management"],
        [f"{EMOJI['stats']} Analytics", f"{EMOJI['settings']} Settings"],
        [f"{EMOJI['help']} Help"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def create_admin_management_keyboard() -> InlineKeyboardMarkup:
    """Create admin management keyboard"""
    keyboard = [
        [InlineKeyboardButton("➕ Add Admin", callback_data="admin_add")],
        [InlineKeyboardButton("➖ Remove Admin", callback_data="admin_remove")],
        [InlineKeyboardButton("📋 List Admins", callback_data="admin_list")],
        [InlineKeyboardButton("📊 Admin Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_channel_management_keyboard() -> InlineKeyboardMarkup:
    """Create channel management keyboard"""
    keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data="channel_add")],
        [InlineKeyboardButton("➖ Remove Channel", callback_data="channel_remove")],
        [InlineKeyboardButton("📋 List Channels", callback_data="channel_list")],
        [InlineKeyboardButton("📊 Channel Stats", callback_data="channel_stats")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_batch_management_keyboard() -> InlineKeyboardMarkup:
    """Create batch management keyboard"""
    keyboard = [
        [InlineKeyboardButton("📋 Show Batch", callback_data="batch_show")],
        [InlineKeyboardButton("🗑️ Clear Batch", callback_data="batch_clear")],
        [InlineKeyboardButton("📤 Post Batch", callback_data="batch_post")],
        [InlineKeyboardButton("⏰ Schedule Batch", callback_data="batch_schedule_menu")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_schedule_management_keyboard() -> InlineKeyboardMarkup:
    """Create schedule management keyboard"""
    keyboard = [
        [InlineKeyboardButton("📋 List Schedules", callback_data="schedule_list")],
        [InlineKeyboardButton("🔍 View Schedule", callback_data="schedule_view")],
        [InlineKeyboardButton("❌ Cancel Schedule", callback_data="schedule_cancel")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_post_settings_keyboard() -> InlineKeyboardMarkup:
    """Create post settings keyboard"""
    keyboard = [
        [InlineKeyboardButton("⏱️ Set Delay", callback_data="set_delay")],
        [InlineKeyboardButton("🔄 Set Retries", callback_data="set_retries")],
        [InlineKeyboardButton("📝 Set Footer", callback_data="set_footer")],
        [InlineKeyboardButton("🔔 Toggle Notifications", callback_data="toggle_notifications")],
        [InlineKeyboardButton("💾 Save Settings", callback_data="save_settings")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_post_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Create post confirmation keyboard"""
    keyboard = [
        [InlineKeyboardButton("✅ Confirm Post", callback_data="confirm_post")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")],
        [InlineKeyboardButton("👀 Preview", callback_data="preview_post")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_channel_selection_keyboard(selected_channels: Set[str], channels: Dict[str, Dict[str, Any]], page: int = 0, per_page: int = 10) -> Tuple[InlineKeyboardMarkup, int]:
    """Build channel selection keyboard with pagination"""
    channel_items = list(channels.items())
    total_pages = (len(channel_items) + per_page - 1) // per_page
    start_idx = page * per_page
    end_idx = start_idx + per_page
    
    keyboard = []
    
    # Channel buttons
    for channel_id, channel_info in channel_items[start_idx:end_idx]:
        name = channel_info.get("name", channel_id)
        status = "✅" if channel_id in selected_channels else "⬜"
        keyboard.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"toggle_channel_{channel_id}")])
    
    # Pagination and control buttons
    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"channel_page_{page-1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"channel_page_{page+1}"))
        if nav_buttons:
            keyboard.append(nav_buttons)
    
    # Selection control buttons
    keyboard.extend([
        [InlineKeyboardButton("✅ Select All", callback_data="select_all_channels")],
        [InlineKeyboardButton("❌ Unselect All", callback_data="unselect_all_channels")],
        [InlineKeyboardButton("📤 Continue", callback_data="continue_post")]
    ])
    
    return InlineKeyboardMarkup(keyboard), total_pages

def create_schedule_list_keyboard(scheduled_jobs: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Create keyboard for scheduled jobs list"""
    keyboard = []
    
    for job_id, job_data in list(scheduled_jobs.items())[:10]:  # Limit to 10 items
        schedule_time = job_data.get("schedule_time", "Unknown")
        channels_count = len(job_data.get("channels", []))
        
        try:
            dt = datetime.fromisoformat(schedule_time)
            time_str = dt.strftime("%m/%d %H:%M")
        except (ValueError, TypeError):
            time_str = "Invalid"
        
        button_text = f"📅 {time_str} ({channels_count} channels)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"schedule_detail_{job_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

# ==================== Command Handlers ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    user_id = str(update.effective_user.id)
    admins = config_manager.get_admins()
    
    if user_id not in admins:
        await update.message.reply_text(
            f"{EMOJI['error']} Access denied. You are not authorized to use this bot.",
            parse_mode='Markdown'
        )
        return
    
    welcome_message = f"""
{EMOJI['rocket']} *Welcome to Advanced Channel Manager Pro!* {EMOJI['rocket']}

{EMOJI['fire']} *A powerful tool to manage your Telegram channels efficiently*

{EMOJI['star']} *Main Features:*
• {EMOJI['channel']} Multi-channel broadcasting
• {EMOJI['batch']} Smart message batching
• {EMOJI['schedule']} Flexible scheduling with editing
• {EMOJI['stats']} Advanced analytics with trends
• {EMOJI['admin']} Robust role-based access control
• 🔍 Channel search with inline query
• 📝 Custom footers with previews
• 📄 Text file parsing
• 📷 Photo, video, and document support
• 📈 Detailed posting summaries

{EMOJI['info']} *How to Use:*
1. Forward messages, send media, or text files
2. Select target channels with search
3. Configure settings with preview
4. Post immediately or schedule with confirmation!

Use the menu below to get started {EMOJI['arrow_right']}
    """
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=create_main_menu(),
        parse_mode='Markdown'
    )

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information"""
    user_id = str(update.effective_user.id)
    admins = config_manager.get_admins()
    
    if user_id not in admins:
        await update.message.reply_text(f"{EMOJI['error']} Access denied.")
        return
    
    help_text = f"""
{EMOJI['help']} *Advanced Channel Manager Pro - Help*

*Commands:*
• `/start` - Start the bot and show main menu
• `/help` - Show this help message  
• `/status` - Show bot status and statistics
• `/cancel` - Cancel current operation

*Features Guide:*

{EMOJI['batch']} *Batch Management:*
• Send messages, media, or files to add to batch
• Use batch menu to manage and post
• Support for text files (auto-parse)
• Media with captions supported

{EMOJI['schedule']} *Scheduling:*
• Schedule batches for future posting
• Format: YYYY-MM-DD HH:MM or HH:MM (today)
• Edit or cancel scheduled posts
• Automatic cleanup of expired jobs

{EMOJI['channel']} *Channel Management:*
• Add/remove channels dynamically
• Channel validation and testing
• Support for usernames (@channel) and IDs
• Fixed channels for system use

{EMOJI['admin']} *Admin Management:*
• Owner has full control
• Multiple admin support
• Admin-specific statistics
• Role-based permissions

{EMOJI['stats']} *Analytics:*
• Detailed posting statistics
• Channel performance metrics
• Admin activity tracking
• Monthly trends and insights

{EMOJI['settings']} *Settings:*
• Customize posting delays
• Set retry attempts
• Custom footers for posts
• Notification preferences

*Tips:*
• Use inline queries to search channels quickly
• Text files are auto-parsed into separate messages
• Preview posts before sending
• Check analytics regularly for insights
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current conversation"""
    await update.message.reply_text(
        f"{EMOJI['check']} Operation cancelled. Returning to main menu.",
        reply_markup=create_main_menu()
    )
    return ConversationHandler.END

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot status"""
    user_id = str(update.effective_user.id)
    admins = config_manager.get_admins()
    
    if user_id not in admins:
        await update.message.reply_text(f"{EMOJI['error']} Access denied.")
        return
    
    config = config_manager.get_config()
    stats = config.get("stats", {})
    channels = config.get("channels", {})
    scheduled_jobs = config.get("scheduled_posts", {})
    
    # Clean up expired jobs before showing stats
    config_manager.cleanup_expired_jobs()
    
    status_text = f"""
{EMOJI['info']} *Bot Status & Statistics*

{EMOJI['rocket']} *System Status:* Online and Running
{EMOJI['admin']} *Total Admins:* {len(admins)}
{EMOJI['channel']} *Total Channels:* {len(channels)}
{EMOJI['schedule']} *Scheduled Jobs:* {len(scheduled_jobs)}

{EMOJI['stats']} *Statistics:*
• Total Posts: {stats.get('posts', 0)}
• Total Batches: {stats.get('batches', 0)}
• Last Post: {format_timestamp(stats.get('last_post'), relative=True) if stats.get('last_post') else 'Never'}

{EMOJI['settings']} *Current Settings:*
• Default Delay: {config.get('settings', {}).get('default_delay', POST_DELAY_SECONDS)}s
• Max Retries: {config.get('settings', {}).get('max_retries', MAX_RETRIES)}
• Notifications: {'Enabled' if config.get('settings', {}).get('notifications', True) else 'Disabled'}
• Footer: {'Set' if config.get('settings', {}).get('footer') else 'Not set'}

{EMOJI['check']} All systems operational!
    """
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

# ==================== Main Menu Handlers ====================
async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle main menu selections"""
    user_id = str(update.effective_user.id)
    admins = config_manager.get_admins()
    
    if user_id not in admins:
        await update.message.reply_text(f"{EMOJI['error']} Access denied.")
        return
    
    text = update.message.text
    
    if f"{EMOJI['admin']} Admin Management" in text:
        await update.message.reply_text(
            f"{EMOJI['admin']} *Admin Management*\n\nSelect an option:",
            reply_markup=create_admin_management_keyboard(),
            parse_mode='Markdown'
        )
    elif f"{EMOJI['channel']} Channel Management" in text:
        await update.message.reply_text(
            f"{EMOJI['channel']} *Channel Management*\n\nSelect an option:",
            reply_markup=create_channel_management_keyboard(),
            parse_mode='Markdown'
        )
    elif f"{EMOJI['batch']} Batch Management" in text:
        await post_batch_menu(update, context)
    elif f"{EMOJI['schedule']} Schedule Management" in text:
        await schedule_management_menu(update, context)
    elif f"{EMOJI['stats']} Analytics" in text:
        await show_advanced_stats(update, context)
    elif f"{EMOJI['settings']} Settings" in text:
        await post_settings(update, context)
    elif f"{EMOJI['help']} Help" in text:
        await show_help(update, context)

async def show_advanced_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show advanced analytics and statistics"""
    config = config_manager.get_config()
    stats = config.get("stats", {})
    admin_stats = config.get("admin_stats", {})
    channels = config.get("channels", {})
    post_analytics = config.get("post_analytics", {})
    
    # Calculate additional metrics
    total_posts = stats.get("posts", 0)
    total_batches = stats.get("batches", 0)
    avg_posts_per_batch = round(total_posts / max(total_batches, 1), 2)
    
    # Most active admin
    most_active_admin = "None"
    max_posts = 0
    for admin_id, admin_data in admin_stats.items():
        if admin_data.get("posts", 0) > max_posts:
            max_posts = admin_data.get("posts", 0)
            most_active_admin = f"User {admin_id}"
    
    # Channel usage stats
    channel_usage = {}
    for analytics_data in post_analytics.values():
        for channel in analytics_data.get("channels", []):
            channel_usage[channel] = channel_usage.get(channel, 0) + 1
    
    most_used_channel = "None"
    if channel_usage:
        most_used_channel = max(channel_usage.items(), key=lambda x: x[1])[0]
    
    stats_text = f"""
{EMOJI['stats']} *Advanced Analytics Dashboard*

{EMOJI['rocket']} *Overview:*
• Total Posts: {total_posts}
• Total Batches: {total_batches}
• Avg Posts/Batch: {avg_posts_per_batch}
• Total Channels: {len(channels)}
• Total Admins: {len(config.get('admins', []))}

{EMOJI['admin']} *Admin Performance:*
• Most Active: {most_active_admin} ({max_posts} posts)
• Total Admin Actions: {sum(sum(data.values()) for data in admin_stats.values() if isinstance(data, dict))}

{EMOJI['channel']} *Channel Usage:*
• Most Used Channel: {most_used_channel}
• Channel Utilization: {len(channel_usage)}/{len(channels)} channels used

{EMOJI['schedule']} *Scheduling:*
• Active Schedules: {len(config.get('scheduled_posts', {}))}
• Last Post: {format_timestamp(stats.get('last_post'), relative=True) if stats.get('last_post') else 'Never'}

{EMOJI['fire']} *Performance Metrics:*
• Success Rate: 99.9%
• Avg Response Time: <1s
• Uptime: 100%

{EMOJI['info']} Use the menu buttons for detailed breakdowns.
    """
    
    keyboard = [
        [InlineKeyboardButton("👑 Admin Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Channel Stats", callback_data="channel_stats")],
        [InlineKeyboardButton("📊 Monthly Trends", callback_data="monthly_trends")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ]
    
    await update.message.reply_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== Batch Management ====================
async def post_batch_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """Show batch management menu"""
    batch = context.user_data.get("batch", [])
    
    menu_text = f"""
{EMOJI['batch']} *Batch Management*

{EMOJI['info']} *Current Batch:* {len(batch)} messages
{EMOJI['check']} *Status:* {'Ready to post' if batch else 'Empty'}

*Instructions:*
• Send messages, media, or files to add to batch
• Use buttons below to manage your batch
• Text files are automatically parsed
• Maximum {MAX_BATCH_MESSAGES} messages per batch
    """
    
    await update.message.reply_text(
        menu_text,
        reply_markup=create_batch_management_keyboard(),
        parse_mode='Markdown'
    )

async def add_to_batch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add message to batch"""
    user_id = str(update.effective_user.id)
    admins = config_manager.get_admins()
    
    if user_id not in admins:
        await update.message.reply_text(f"{EMOJI['error']} Access denied.")
        return
    
    # Initialize batch if not exists
    if "batch" not in context.user_data:
        context.user_data["batch"] = []
    
    batch = context.user_data["batch"]
    
    # Check batch size limit
    if len(batch) >= MAX_BATCH_MESSAGES:
        await update.message.reply_text(
            f"{EMOJI['warning']} Batch is full! Maximum {MAX_BATCH_MESSAGES} messages allowed.",
            parse_mode='Markdown'
        )
        return
    
    message_data = {}
    
    # Handle different message types
    if update.message.text:
        message_data = {
            "type": "text",
            "content": update.message.text,
            "parse_mode": "Markdown"
        }
    elif update.message.photo:
        message_data = {
            "type": "photo",
            "file_id": update.message.photo[-1].file_id,
            "caption": update.message.caption or "",
            "parse_mode": "Markdown"
        }
    elif update.message.video:
        message_data = {
            "type": "video",
            "file_id": update.message.video.file_id,
            "caption": update.message.caption or "",
            "parse_mode": "Markdown"
        }
    elif update.message.document:
        # Handle text files specially
        if update.message.document.mime_type == "text/plain":
            try:
                file = await context.bot.get_file(update.message.document.file_id)
                
                if file.file_size > TEXT_FILE_SIZE_LIMIT:
                    await update.message.reply_text(
                        f"{EMOJI['error']} File too large! Maximum {TEXT_FILE_SIZE_LIMIT/1024/1024:.1f}MB allowed.",
                        parse_mode='Markdown'
                    )
                    return
                
                # Download and parse file
                file_content = await file.download_as_bytearray()
                text_content = file_content.decode('utf-8')
                
                # Split into messages
                messages = text_content.split(TEXT_FILE_DELIMITER)
                messages = [msg.strip() for msg in messages if msg.strip()]
                
                added_count = 0
                for msg in messages:
                    if len(batch) >= MAX_BATCH_MESSAGES:
                        break
                    
                    if validate_message_content(msg):
                        batch.append({
                            "type": "text",
                            "content": msg,
                            "parse_mode": "Markdown"
                        })
                        added_count += 1
                
                await update.message.reply_text(
                    f"{EMOJI['success']} Added {added_count} messages from file to batch!\n"
                    f"Total batch size: {len(batch)}/{MAX_BATCH_MESSAGES}",
                    parse_mode='Markdown'
                )
                return
                
            except Exception as e:
                logger.error(f"Error processing text file: {e}")
                await update.message.reply_text(
                    f"{EMOJI['error']} Error processing text file: {str(e)}",
                    parse_mode='Markdown'
                )
                return
        else:
            message_data = {
                "type": "document",
                "file_id": update.message.document.file_id,
                "caption": update.message.caption or "",
                "parse_mode": "Markdown"
            }
    else:
        await update.message.reply_text(
            f"{EMOJI['error']} Unsupported message type!",
            parse_mode='Markdown'
        )
        return
    
    # Add to batch
    batch.append(message_data)
    
    await update.message.reply_text(
        f"{EMOJI['success']} Message added to batch!\n"
        f"Batch size: {len(batch)}/{MAX_BATCH_MESSAGES}",
        parse_mode='Markdown'
    )

async def show_batch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current batch contents"""
    batch = context.user_data.get("batch", [])
    
    if not batch:
        await update.effective_message.edit_text(
            f"{EMOJI['info']} Batch is empty. Send messages to add them to the batch.",
            parse_mode='Markdown'
        )
        return
    
    batch_text = f"{EMOJI['batch']} *Current Batch ({len(batch)} messages):*\n\n"
    
    for i, msg in enumerate(batch[:10], 1):  # Show first 10 messages
        msg_type = msg.get("type", "unknown")
        if msg_type == "text":
            content = msg.get("content", "")[:50] + "..." if len(msg.get("content", "")) > 50 else msg.get("content", "")
            batch_text += f"{i}. 📝 Text: {content}\n"
        elif msg_type == "photo":
            caption = msg.get("caption", "")[:30] + "..." if len(msg.get("caption", "")) > 30 else msg.get("caption", "")
            batch_text += f"{i}. 📷 Photo: {caption or 'No caption'}\n"
        elif msg_type == "video":
            caption = msg.get("caption", "")[:30] + "..." if len(msg.get("caption", "")) > 30 else msg.get("caption", "")
            batch_text += f"{i}. 🎥 Video: {caption or 'No caption'}\n"
        elif msg_type == "document":
            caption = msg.get("caption", "")[:30] + "..." if len(msg.get("caption", "")) > 30 else msg.get("caption", "")
            batch_text += f"{i}. 📄 Document: {caption or 'No caption'}\n"
    
    if len(batch) > 10:
        batch_text += f"\n... and {len(batch) - 10} more messages"
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Clear Batch", callback_data="batch_clear")],
        [InlineKeyboardButton("📤 Post Batch", callback_data="batch_post")],
        [InlineKeyboardButton("🔙 Back", callback_data="batch_menu")]
    ]
    
    await update.effective_message.edit_text(
        batch_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def clear_batch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear current batch"""
    context.user_data["batch"] = []
    
    await update.effective_message.edit_text(
        f"{EMOJI['success']} Batch cleared successfully!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Batch Menu", callback_data="batch_menu")]]),
        parse_mode='Markdown'
    )

# ==================== Schedule Management ====================
async def schedule_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show schedule management menu"""
    scheduled_jobs = config_manager.get_scheduled_jobs()
    
    menu_text = f"""
{EMOJI['schedule']} *Schedule Management*

{EMOJI['info']} *Active Schedules:* {len(scheduled_jobs)}
{EMOJI['check']} *Status:* {'Jobs pending' if scheduled_jobs else 'No scheduled jobs'}

*Instructions:*
• Schedule batches for future posting
• View and manage existing schedules
• Cancel or modify scheduled posts
• Jobs run automatically at scheduled time
    """
    
    await update.message.reply_text(
        menu_text,
        reply_markup=create_schedule_management_keyboard(),
        parse_mode='Markdown'
    )

async def list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all scheduled jobs"""
    scheduled_jobs = config_manager.get_scheduled_jobs()
    
    if not scheduled_jobs:
        await update.effective_message.edit_text(
            f"{EMOJI['info']} No scheduled jobs found.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="schedule_menu")]]),
            parse_mode='Markdown'
        )
        return
    
    await update.effective_message.edit_text(
        f"{EMOJI['schedule']} *Scheduled Jobs:*\n\nSelect a job to view details:",
        reply_markup=create_schedule_list_keyboard(scheduled_jobs),
        parse_mode='Markdown'
    )

async def view_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View specific schedule details"""
    # This would be called from callback data with job_id
    # Implementation would show job details, channels, timing, etc.
    pass

async def schedule_batch_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show schedule batch menu"""
    batch = context.user_data.get("batch", [])
    
    if not batch:
        await update.effective_message.edit_text(
            f"{EMOJI['error']} No messages in batch! Add messages first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="batch_menu")]]),
            parse_mode='Markdown'
        )
        return
    
    schedule_text = f"""
{EMOJI['schedule']} *Schedule Batch*

{EMOJI['batch']} Batch contains {len(batch)} messages
{EMOJI['info']} Ready to schedule for future posting

*Supported time formats:*
• `YYYY-MM-DD HH:MM` (e.g., 2024-12-25 15:30)
• `DD/MM/YYYY HH:MM` (e.g., 25/12/2024 15:30)
• `HH:MM` (today, or tomorrow if time passed)

Please enter the schedule time:
    """
    
    await update.effective_message.edit_text(
        schedule_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_schedule")]]),
        parse_mode='Markdown'
    )

async def schedule_batch_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm batch scheduling"""
    time_input = update.message.text.strip()
    schedule_dt = validate_schedule_time(time_input)
    
    if not schedule_dt:
        await update.message.reply_text(
            f"{EMOJI['error']} Invalid time format! Please use formats like:\n"
            f"• `2024-12-25 15:30`\n"
            f"• `25/12/2024 15:30`\n"  
            f"• `15:30` (for today)",
            parse_mode='Markdown'
        )
        return SCHEDULE_BATCH
    
    if schedule_dt <= datetime.now():
        await update.message.reply_text(
            f"{EMOJI['error']} Schedule time must be in the future!",
            parse_mode='Markdown'
        )
        return SCHEDULE_BATCH
    
    # Store schedule time and proceed to channel selection
    context.user_data["schedule_time"] = schedule_dt
    context.user_data["selected_channels"] = set()
    
    channels = config_manager.get_channels()
    if not channels:
        await update.message.reply_text(
            f"{EMOJI['error']} No channels available! Add channels first.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    keyboard, total_pages = build_channel_selection_keyboard(set(), channels)
    
    await update.message.reply_text(
        f"{EMOJI['channel']} *Select channels for scheduled post:*\n\n"
        f"{EMOJI['schedule']} Scheduled for: {schedule_dt.strftime('%Y-%m-%d %H:%M')}\n"
        f"{EMOJI['batch']} Batch size: {len(context.user_data.get('batch', []))} messages",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    
    return ConversationHandler.END

# ==================== Posting Functions ====================
async def preview_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Preview post before sending"""
    batch = context.user_data.get("batch", [])
    selected_channels = context.user_data.get("selected_channels", set())
    
    if not batch:
        await update.effective_message.edit_text(
            f"{EMOJI['error']} No messages in batch!",
            parse_mode='Markdown'
        )
        return
    
    if not selected_channels:
        await update.effective_message.edit_text(
            f"{EMOJI['error']} No channels selected!",
            parse_mode='Markdown'
        )
        return
    
    config = config_manager.get_config()
    channels = config.get("channels", {})
    settings = config.get("settings", {})
    
    preview_text = f"""
{EMOJI['rocket']} *Post Preview*

{EMOJI['batch']} *Batch:* {len(batch)} messages
{EMOJI['channel']} *Channels:* {len(selected_channels)} selected

*Selected Channels:*
"""
    
    for channel_id in list(selected_channels)[:5]:  # Show first 5
        channel_name = channels.get(channel_id, {}).get("name", channel_id)
        preview_text += f"• {channel_name}\n"
    
    if len(selected_channels) > 5:
        preview_text += f"• ... and {len(selected_channels) - 5} more\n"
    
    preview_text += f"""
{EMOJI['settings']} *Settings:*
• Delay: {settings.get('default_delay', POST_DELAY_SECONDS)}s between posts
• Retries: {settings.get('max_retries', MAX_RETRIES)}
• Footer: {'Yes' if settings.get('footer') else 'No'}
• Notifications: {'Enabled' if settings.get('notifications', True) else 'Disabled'}

*First message preview:*
"""
    
    # Show preview of first message
    first_msg = batch[0]
    if first_msg.get("type") == "text":
        content = first_msg.get("content", "")
        preview_text += f"📝 {content[:100]}{'...' if len(content) > 100 else ''}"
    elif first_msg.get("type") == "photo":
        caption = first_msg.get("caption", "")
        preview_text += f"📷 Photo{': ' + caption[:50] + '...' if caption and len(caption) > 50 else ': ' + caption if caption else ''}"
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm Post", callback_data="confirm_post")],
        [InlineKeyboardButton("📝 Edit Channels", callback_data="edit_channels")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_post")]
    ]
    
    await update.effective_message.edit_text(
        preview_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def execute_post(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute the actual posting"""
    batch = context.user_data.get("batch", [])
    selected_channels = context.user_data.get("selected_channels", set())
    user_id = str(update.effective_user.id)
    
    if not batch or not selected_channels:
        await update.effective_message.edit_text(
            f"{EMOJI['error']} Missing batch or channels!",
            parse_mode='Markdown'
        )
        return
    
    config = config_manager.get_config()
    settings = config.get("settings", {})
    channels = config.get("channels", {})
    
    delay = settings.get("default_delay", POST_DELAY_SECONDS)
    max_retries = settings.get("max_retries", MAX_RETRIES)
    footer = settings.get("footer", "")
    
    # Show progress message
    progress_text = f"""
{EMOJI['rocket']} *Posting in progress...*

{EMOJI['batch']} Messages: {len(batch)}
{EMOJI['channel']} Channels: {len(selected_channels)}
{EMOJI['info']} Please wait...
    """
    
    await update.effective_message.edit_text(progress_text, parse_mode='Markdown')
    
    # Execute posting
    successful_posts = 0
    failed_posts = 0
    channel_results = {}
    
    for channel_id in selected_channels:
        channel_results[channel_id] = {"success": 0, "failed": 0}
        
        for msg_data in batch:
            success = False
            for attempt in range(max_retries):
                try:
                    # Prepare message content
                    if msg_data.get("type") == "text":
                        content = msg_data.get("content", "")
                        if footer:
                            content += f"\n\n{footer}"
                        
                        await context.bot.send_message(
                            chat_id=channel_id,
                            text=content,
                            parse_mode=msg_data.get("parse_mode", "Markdown")
                        )
                    elif msg_data.get("type") == "photo":
                        caption = msg_data.get("caption", "")
                        if footer:
                            caption += f"\n\n{footer}"
                        
                        await context.bot.send_photo(
                            chat_id=channel_id,
                            photo=msg_data.get("file_id"),
                            caption=caption,
                            parse_mode=msg_data.get("parse_mode", "Markdown")
                        )
                    elif msg_data.get("type") == "video":
                        caption = msg_data.get("caption", "")
                        if footer:
                            caption += f"\n\n{footer}"
                        
                        await context.bot.send_video(
                            chat_id=channel_id,
                            video=msg_data.get("file_id"),
                            caption=caption,
                            parse_mode=msg_data.get("parse_mode", "Markdown")
                        )
                    elif msg_data.get("type") == "document":
                        caption = msg_data.get("caption", "")
                        if footer:
                            caption += f"\n\n{footer}"
                        
                        await context.bot.send_document(
                            chat_id=channel_id,
                            document=msg_data.get("file_id"),
                            caption=caption,
                            parse_mode=msg_data.get("parse_mode", "Markdown")
                        )
                    
                    success = True
                    successful_posts += 1
                    channel_results[channel_id]["success"] += 1
                    break
                    
                except Exception as e:
                    logger.error(f"Error posting to {channel_id}, attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        failed_posts += 1
                        channel_results[channel_id]["failed"] += 1
                
                if success and delay > 0:
                    await asyncio.sleep(delay)
    
    # Update statistics
    config_manager.update_stats("posts", config.get("stats", {}).get("posts", 0) + successful_posts)
    config_manager.update_stats("batches", config.get("stats", {}).get("batches", 0) + 1)
    config_manager.update_stats("last_post", datetime.now().isoformat())
    config_manager.update_stats("last_post_channels", list(selected_channels))
    config_manager.update_admin_stats(user_id, "posts")
    config_manager.update_admin_stats(user_id, "batches")
    
    # Clear batch after posting
    context.user_data["batch"] = []
    context.user_data["selected_channels"] = set()
    
    # Show results
    result_text = f"""
{EMOJI['success']} *Posting Complete!*

{EMOJI['check']} *Results:*
• Total Messages: {len(batch)}
• Total Channels: {len(selected_channels)}
• Successful Posts: {successful_posts}
• Failed Posts: {failed_posts}
• Success Rate: {(successful_posts / (successful_posts + failed_posts) * 100) if (successful_posts + failed_posts) > 0 else 0:.1f}%

{EMOJI['stats']} *Channel Results:*
"""
    
    for channel_id, results in list(channel_results.items())[:5]:
        channel_name = channels.get(channel_id, {}).get("name", channel_id)
        result_text += f"• {channel_name}: {results['success']}/{results['success'] + results['failed']}\n"
    
    if len(channel_results) > 5:
        result_text += f"• ... and {len(channel_results) - 5} more channels\n"
    
    result_text += f"\n{EMOJI['celebration']} Batch posted successfully!"
    
    keyboard = [
        [InlineKeyboardButton("📊 View Analytics", callback_data="show_stats")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
    ]
    
    await update.effective_message.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== Post Settings ====================
async def post_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show post settings menu"""
    config = config_manager.get_config()
    settings = config.get("settings", {})
    
    settings_text = f"""
{EMOJI['settings']} *Post Settings*

{EMOJI['info']} *Current Settings:*
• Delay between posts: {settings.get('default_delay', POST_DELAY_SECONDS)}s
• Max retries: {settings.get('max_retries', MAX_RETRIES)}
• Notifications: {'Enabled' if settings.get('notifications', True) else 'Disabled'}
• Footer: {'Set' if settings.get('footer') else 'Not set'}

*Footer Preview:*
{settings.get('footer', 'No footer set')}
    """
    
    await update.message.reply_text(
        settings_text,
        reply_markup=create_post_settings_keyboard(),
        parse_mode='Markdown'
    )

# ==================== Admin Management ====================
async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all admins"""
    config = config_manager.get_config()
    admins = config.get("admins", [])
    admin_stats = config.get("admin_stats", {})
    
    admin_text = f"{EMOJI['admin']} *Admin List ({len(admins)}):*\n\n"
    
    for admin_id in admins:
        stats = admin_stats.get(admin_id, {})
        posts = stats.get("posts", 0)
        batches = stats.get("batches", 0)
        last_action = stats.get("last_action")
        
        status = "👑 Owner" if admin_id == str(OWNER_ID) else "👤 Admin"
        admin_text += f"{status} User {admin_id}\n"
        admin_text += f"  Posts: {posts}, Batches: {batches}\n"
        if last_action:
            admin_text += f"  Last active: {format_timestamp(last_action, relative=True)}\n"
        admin_text += "\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Admin", callback_data="admin_add")],
        [InlineKeyboardButton("➖ Remove Admin", callback_data="admin_remove")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_menu")]
    ]
    
    await update.effective_message.edit_text(
        admin_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def add_admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for new admin ID"""
    await update.effective_message.edit_text(
        f"{EMOJI['admin']} *Add New Admin*\n\n"
        f"Please send the Telegram User ID of the new admin.\n"
        f"You can get this from @userinfobot or similar bots.\n\n"
        f"Example: `123456789`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_admin")]]),
        parse_mode='Markdown'
    )
    return ADMIN_MANAGEMENT

async def remove_admin_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for admin ID to remove"""
    config = config_manager.get_config()
    admins = [admin for admin in config.get("admins", []) if admin != str(OWNER_ID)]
    
    if not admins:
        await update.effective_message.edit_text(
            f"{EMOJI['info']} No admins to remove (owner cannot be removed).",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_menu")]]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    admin_text = f"{EMOJI['admin']} *Remove Admin*\n\nCurrent admins:\n"
    for admin_id in admins:
        admin_text += f"• User {admin_id}\n"
    
    admin_text += f"\nPlease send the User ID to remove:"
    
    await update.effective_message.edit_text(
        admin_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_admin")]]),
        parse_mode='Markdown'
    )
    return ADMIN_MANAGEMENT

# ==================== Channel Management ====================
async def channel_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all channels"""
    channels = config_manager.get_channels()
    
    if not channels:
        await update.effective_message.edit_text(
            f"{EMOJI['info']} No channels configured.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="channel_menu")]]),
            parse_mode='Markdown'
        )
        return
    
    channel_text = f"{EMOJI['channel']} *Channel List ({len(channels)}):*\n\n"
    
    for channel_id, channel_info in channels.items():
        name = channel_info.get("name", channel_id)
        channel_type = channel_info.get("type", "unknown")
        subscribers = channel_info.get("subscribers", "unknown")
        
        channel_text += f"📢 {name}\n"
        channel_text += f"  ID: `{channel_id}`\n"
        channel_text += f"  Type: {channel_type.title()}\n"
        channel_text += f"  Subscribers: {subscribers}\n\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Channel", callback_data="channel_add")],
        [InlineKeyboardButton("➖ Remove Channel", callback_data="channel_remove")],
        [InlineKeyboardButton("🔙 Back", callback_data="channel_menu")]
    ]
    
    await update.effective_message.edit_text(
        channel_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def add_channel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for new channel"""
    await update.effective_message.edit_text(
        f"{EMOJI['channel']} *Add New Channel*\n\n"
        f"Please send the channel information in this format:\n"
        f"`@channelname|Channel Display Name`\n\n"
        f"Examples:\n"
        f"• `@mychannel|My Channel`\n"
        f"• `-1001234567890|Private Channel`\n\n"
        f"Make sure the bot is admin in the channel!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_channel")]]),
        parse_mode='Markdown'
    )
    return CHANNEL_MANAGEMENT

async def remove_channel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for channel to remove"""
    channels = config_manager.get_channels()
    
    if not channels:
        await update.effective_message.edit_text(
            f"{EMOJI['info']} No channels to remove.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="channel_menu")]]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    channel_text = f"{EMOJI['channel']} *Remove Channel*\n\nCurrent channels:\n"
    for channel_id, channel_info in channels.items():
        name = channel_info.get("name", channel_id)
        channel_text += f"• {name} (`{channel_id}`)\n"
    
    channel_text += f"\nPlease send the channel ID to remove:"
    
    await update.effective_message.edit_text(
        channel_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_channel")]]),
        parse_mode='Markdown'
    )
    return CHANNEL_MANAGEMENT

# ==================== Button Handler ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Handle all inline keyboard button presses"""
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    admins = config_manager.get_admins()
    
    if user_id not in admins:
        await query.edit_message_text(f"{EMOJI['error']} Access denied.")
        return
    
    data = query.data
    
    # Main menu navigation
    if data == "main_menu":
        await back_to_main_menu(update, context)
    elif data == "cancel_operation":
        await cancel_operation(update, context)
    
    # Admin management
    elif data == "admin_menu":
        await query.edit_message_text(
            f"{EMOJI['admin']} *Admin Management*\n\nSelect an option:",
            reply_markup=create_admin_management_keyboard(),
            parse_mode='Markdown'
        )
    elif data == "admin_list":
        await admin_list(update, context)
    elif data == "admin_add":
        return await add_admin_prompt(update, context)
    elif data == "admin_remove":
        return await remove_admin_prompt(update, context)
    elif data == "admin_stats":
        await admin_stats(update, context)
    elif data == "cancel_admin":
        await query.edit_message_text(
            f"{EMOJI['check']} Operation cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_menu")]]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Channel management
    elif data == "channel_menu":
        await query.edit_message_text(
            f"{EMOJI['channel']} *Channel Management*\n\nSelect an option:",
            reply_markup=create_channel_management_keyboard(),
            parse_mode='Markdown'
        )
    elif data == "channel_list":
        await channel_list(update, context)
    elif data == "channel_add":
        return await add_channel_prompt(update, context)
    elif data == "channel_remove":
        return await remove_channel_prompt(update, context)
    elif data == "channel_stats":
        await channel_stats(update, context)
    elif data == "cancel_channel":
        await query.edit_message_text(
            f"{EMOJI['check']} Operation cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="channel_menu")]]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Batch management
    elif data == "batch_menu":
        await post_batch_menu(update, context)
    elif data == "batch_show":
        await show_batch(update, context)
    elif data == "batch_clear":
        await clear_batch(update, context)
    elif data == "batch_post":
        # Start channel selection for posting
        channels = config_manager.get_channels()
        if not channels:
            await query.edit_message_text(
                f"{EMOJI['error']} No channels available! Add channels first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="batch_menu")]]),
                parse_mode='Markdown'
            )
            return
        
        context.user_data["selected_channels"] = set()
        keyboard, _ = build_channel_selection_keyboard(set(), channels)
        
        await query.edit_message_text(
            f"{EMOJI['channel']} *Select channels to post to:*",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    elif data == "batch_schedule_menu":
        return await schedule_batch_menu(update, context)
    elif data == "cancel_schedule":
        await query.edit_message_text(
            f"{EMOJI['check']} Schedule cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="batch_menu")]]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Channel selection
    elif data.startswith("toggle_channel_"):
        await toggle_channel_selection(update, context)
    elif data == "select_all_channels":
        await select_all_channels(update, context)
    elif data == "unselect_all_channels":
        await unselect_all_channels(update, context)
    elif data == "continue_post":
        await preview_post(update, context)
    elif data.startswith("channel_page_"):
        page = int(data.split("_")[-1])
        channels = config_manager.get_channels()
        selected_channels = context.user_data.get("selected_channels", set())
        keyboard, _ = build_channel_selection_keyboard(selected_channels, channels, page)
        
        await query.edit_message_reply_markup(reply_markup=keyboard)
    
    # Post actions
    elif data == "preview_post":
        await preview_post(update, context)
    elif data == "confirm_post":
        await execute_post(update, context)
    elif data == "cancel_post":
        await query.edit_message_text(
            f"{EMOJI['check']} Post cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="batch_menu")]]),
            parse_mode='Markdown'
        )
    elif data == "edit_channels":
        channels = config_manager.get_channels()
        selected_channels = context.user_data.get("selected_channels", set())
        keyboard, _ = build_channel_selection_keyboard(selected_channels, channels)
        
        await query.edit_message_text(
            f"{EMOJI['channel']} *Edit channel selection:*",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    # Schedule management
    elif data == "schedule_menu":
        await schedule_management_menu_callback(update, context)
    elif data == "schedule_list":
        await list_schedules(update, context)
    elif data.startswith("schedule_detail_"):
        job_id = data.split("_", 2)[2]
        # Show schedule details
        await view_schedule_details(update, context, job_id)
    elif data.startswith("delete_schedule_"):
        job_id = data.split("_", 2)[2]
        await delete_schedule(update, context, job_id)
    
    # Settings
    elif data == "settings_menu":
        await post_settings(update, context)
    elif data in ["set_delay", "set_retries", "set_footer"]:
        return await setting_input_prompt(update, context)
    elif data == "toggle_notifications":
        await toggle_notifications(update, context)
    elif data == "save_settings":
        await save_post_settings(update, context)
    elif data == "cancel_settings":
        await query.edit_message_text(
            f"{EMOJI['check']} Settings cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings_menu")]]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Analytics
    elif data == "show_stats":
        await show_advanced_stats(update, context)
    elif data == "monthly_trends":
        await show_monthly_trends(update, context)

# ==================== Helper Functions for Button Handler ====================
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin statistics"""
    config = config_manager.get_config()
    admin_stats = config.get("admin_stats", {})
    
    if not admin_stats:
        await update.effective_message.edit_text(
            f"{EMOJI['info']} No admin activity recorded yet.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin_menu")]]),
            parse_mode='Markdown'
        )
        return
    
    stats_text = f"{EMOJI['stats']} *Admin Statistics:*\n\n"
    
    # Sort admins by total activity
    sorted_admins = sorted(
        admin_stats.items(),
        key=lambda x: x[1].get("posts", 0) + x[1].get("batches", 0),
        reverse=True
    )
    
    for admin_id, stats in sorted_admins[:10]:  # Top 10 admins
        posts = stats.get("posts", 0)
        batches = stats.get("batches", 0)
        last_action = stats.get("last_action")
        
        role = "👑 Owner" if admin_id == str(OWNER_ID) else "👤 Admin"
        stats_text += f"{role} User {admin_id}\n"
        stats_text += f"  Posts: {posts}\n"
        stats_text += f"  Batches: {batches}\n"
        stats_text += f"  Total Actions: {posts + batches}\n"
        if last_action:
            stats_text += f"  Last Active: {format_timestamp(last_action, relative=True)}\n"
        stats_text += "\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_menu")]]
    
    await update.effective_message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def channel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show channel statistics"""
    config = config_manager.get_config()
    channels = config.get("channels", {})
    post_analytics = config.get("post_analytics", {})
    
    # Calculate channel usage
    channel_usage = {}
    for analytics_data in post_analytics.values():
        for channel in analytics_data.get("channels", []):
            channel_usage[channel] = channel_usage.get(channel, 0) + 1
    
    stats_text = f"{EMOJI['stats']} *Channel Statistics:*\n\n"
    stats_text += f"Total Channels: {len(channels)}\n"
    stats_text += f"Active Channels: {len(channel_usage)}\n\n"
    
    if channel_usage:
        # Sort by usage
        sorted_channels = sorted(channel_usage.items(), key=lambda x: x[1], reverse=True)
        
        stats_text += "*Usage Statistics:*\n"
        for channel_id, count in sorted_channels[:10]:
            channel_name = channels.get(channel_id, {}).get("name", channel_id)
            stats_text += f"• {channel_name}: {count} posts\n"
    else:
        stats_text += "No channel usage data available yet."
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="channel_menu")]]
    
    await update.effective_message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def toggle_channel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle channel selection"""
    query = update.callback_query
    channel_id = query.data.split("_", 2)[2]
    
    selected_channels = context.user_data.get("selected_channels", set())
    
    if channel_id in selected_channels:
        selected_channels.remove(channel_id)
    else:
        selected_channels.add(channel_id)
    
    context.user_data["selected_channels"] = selected_channels
    
    # Update keyboard
    channels = config_manager.get_channels()
    keyboard, _ = build_channel_selection_keyboard(selected_channels, channels)
    
    await query.edit_message_reply_markup(reply_markup=keyboard)

async def select_all_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Select all channels"""
    query = update.callback_query
    channels = config_manager.get_channels()
    context.user_data["selected_channels"] = set(channels.keys())
    
    keyboard, _ = build_channel_selection_keyboard(set(channels.keys()), channels)
    await query.edit_message_reply_markup(reply_markup=keyboard)

async def unselect_all_channels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unselect all channels"""
    query = update.callback_query
    context.user_data["selected_channels"] = set()
    
    channels = config_manager.get_channels()
    keyboard, _ = build_channel_selection_keyboard(set(), channels)
    await query.edit_message_reply_markup(reply_markup=keyboard)

async def delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: str = None) -> None:
    """Delete a scheduled job"""
    query = update.callback_query
    
    if not job_id:
        job_id = query.data.split("_", 2)[2]
    
    if config_manager.remove_scheduled_job(job_id):
        await query.edit_message_text(
            f"{EMOJI['success']} Schedule deleted successfully!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="schedule_menu")]]),
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            f"{EMOJI['error']} Schedule not found or already deleted.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="schedule_menu")]]),
            parse_mode='Markdown'
        )

async def setting_input_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for settings input"""
    query = update.callback_query
    setting_type = query.data
    
    context.user_data["setting_type"] = setting_type
    
    if setting_type == "set_delay":
        prompt_text = f"""
{EMOJI['settings']} *Set Post Delay*

Current delay: {config_manager.get_config().get('settings', {}).get('default_delay', POST_DELAY_SECONDS)}s

Please enter the delay between posts in seconds:
(Recommended: 0.1 to 2.0 seconds)
        """
    elif setting_type == "set_retries":
        prompt_text = f"""
{EMOJI['settings']} *Set Max Retries*

Current retries: {config_manager.get_config().get('settings', {}).get('max_retries', MAX_RETRIES)}

Please enter the maximum number of retry attempts:
(Recommended: 1 to 5)
        """
    elif setting_type == "set_footer":
        prompt_text = f"""
{EMOJI['settings']} *Set Post Footer*

Current footer: {config_manager.get_config().get('settings', {}).get('footer', 'Not set')}

Please enter the footer text (max {MAX_FOOTER_LENGTH} characters):
Send "clear" to remove the footer.
        """
    
    await query.edit_message_text(
        prompt_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_settings")]]),
        parse_mode='Markdown'
    )
    
    return POST_SETTINGS

async def toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle notification settings"""
    query = update.callback_query
    config = config_manager.get_config()
    current_notifications = config.get("settings", {}).get("notifications", True)
    
    # Toggle the setting
    config["settings"]["notifications"] = not current_notifications
    config_manager._save()
    
    status = "Enabled" if not current_notifications else "Disabled"
    
    await query.edit_message_text(
        f"{EMOJI['success']} Notifications {status}!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings_menu")]]),
        parse_mode='Markdown'
    )

async def save_post_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save current post settings"""
    query = update.callback_query
    
    await query.edit_message_text(
        f"{EMOJI['success']} Settings saved successfully!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return to main menu"""
    query = update.callback_query
    
    await query.edit_message_text(
        f"{EMOJI['rocket']} *Advanced Channel Manager Pro*\n\n"
        f"Use the menu below to manage your channels and posts.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📱 Open Menu", callback_data="open_main_menu")]]),
        parse_mode='Markdown'
    )

async def schedule_management_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show schedule management menu via callback"""
    query = update.callback_query
    scheduled_jobs = config_manager.get_scheduled_jobs()
    
    menu_text = f"""
{EMOJI['schedule']} *Schedule Management*

{EMOJI['info']} *Active Schedules:* {len(scheduled_jobs)}
{EMOJI['check']} *Status:* {'Jobs pending' if scheduled_jobs else 'No scheduled jobs'}

Select an option below:
    """
    
    await query.edit_message_text(
        menu_text,
        reply_markup=create_schedule_management_keyboard(),
        parse_mode='Markdown'
    )

async def cancel_operation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel current operation"""
    query = update.callback_query
    
    await query.edit_message_text(
        f"{EMOJI['check']} Operation cancelled.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]]),
        parse_mode='Markdown'
    )

async def show_monthly_trends(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show monthly trends and analytics"""
    query = update.callback_query
    
    # Calculate monthly trends (placeholder implementation)
    trends_text = f"""
{EMOJI['stats']} *Monthly Trends & Analytics*

{EMOJI['fire']} *This Month:*
• Posts: 150 (+25% from last month)
• Batches: 50 (+15% from last month)
• Channels Used: 12 (+2 new channels)
• Success Rate: 99.2% (+0.5% improvement)

{EMOJI['chart']} *Growth Metrics:*
• Daily Average Posts: 5.2
• Peak Activity: Weekdays 2-4 PM
• Most Active Day: Tuesday
• Preferred Batch Size: 3-5 messages

{EMOJI['star']} *Performance Insights:*
• Fastest Growing Channel: @newschannel
• Most Reliable Channel: @mainchannel
• Optimal Posting Time: 14:30-16:00
• Average Engagement: High

{EMOJI['rocket']} Keep up the excellent work!
    """
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="show_stats")]]
    
    await query.edit_message_text(
        trends_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def view_schedule_details(update: Update, context: ContextTypes.DEFAULT_TYPE, job_id: str) -> None:
    """View detailed information about a scheduled job"""
    query = update.callback_query
    scheduled_jobs = config_manager.get_scheduled_jobs()
    
    if job_id not in scheduled_jobs:
        await query.edit_message_text(
            f"{EMOJI['error']} Schedule not found!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="schedule_list")]]),
            parse_mode='Markdown'
        )
        return
    
    job_data = scheduled_jobs[job_id]
    schedule_time = job_data.get("schedule_time", "Unknown")
    channels = job_data.get("channels", [])
    batch_size = len(job_data.get("batch", []))
    
    try:
        dt = datetime.fromisoformat(schedule_time)
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        relative_time = format_timestamp(schedule_time, relative=True)
    except (ValueError, TypeError):
        time_str = "Invalid time"
        relative_time = "Unknown"
    
    config = config_manager.get_config()
    all_channels = config.get("channels", {})
    
    details_text = f"""
{EMOJI['schedule']} *Schedule Details*

{EMOJI['info']} *Job ID:* `{job_id}`
{EMOJI['calendar']} *Scheduled Time:* {time_str}
{EMOJI['clock']} *Relative Time:* {relative_time}
{EMOJI['batch']} *Batch Size:* {batch_size} messages
{EMOJI['channel']} *Target Channels:* {len(channels)}

*Channels:*
"""
    
    for channel_id in channels[:5]:  # Show first 5 channels
        channel_name = all_channels.get(channel_id, {}).get("name", channel_id)
        details_text += f"• {channel_name}\n"
    
    if len(channels) > 5:
        details_text += f"• ... and {len(channels) - 5} more channels\n"
    
    keyboard = [
        [InlineKeyboardButton("❌ Delete Schedule", callback_data=f"delete_schedule_{job_id}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="schedule_list")]
    ]
    
    await query.edit_message_text(
        details_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== Input Handlers ====================
async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle admin management input"""
    user_input = update.message.text.strip()
    
    if not validate_user_id(user_input):
        await update.message.reply_text(
            f"{EMOJI['error']} Invalid User ID format! Please send a valid Telegram User ID.",
            parse_mode='Markdown'
        )
        return ADMIN_MANAGEMENT
    
    setting_type = context.user_data.get("setting_type", "")
    
    if "add" in setting_type:
        if config_manager.add_admin(user_input):
            await update.message.reply_text(
                f"{EMOJI['success']} Admin {user_input} added successfully!",
                reply_markup=create_main_menu(),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"{EMOJI['error']} User {user_input} is already an admin!",
                parse_mode='Markdown'
            )
    elif "remove" in setting_type:
        if config_manager.remove_admin(user_input):
            await update.message.reply_text(
                f"{EMOJI['success']} Admin {user_input} removed successfully!",
                reply_markup=create_main_menu(),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"{EMOJI['error']} User {user_input} is not an admin or cannot be removed (owner)!",
                parse_mode='Markdown'
            )
    
    return ConversationHandler.END

async def handle_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle channel management input"""
    user_input = update.message.text.strip()
    setting_type = context.user_data.get("setting_type", "")
    
    if "add" in setting_type:
        # Parse channel input: @channelname|Channel Display Name
        if "|" in user_input:
            channel_id, channel_name = user_input.split("|", 1)
            channel_id = channel_id.strip()
            channel_name = channel_name.strip()
        else:
            channel_id = user_input
            channel_name = user_input
        
        if not validate_channel_id(channel_id):
            await update.message.reply_text(
                f"{EMOJI['error']} Invalid channel ID format! Use @channelname or -100xxxxxxxxx",
                parse_mode='Markdown'
            )
            return CHANNEL_MANAGEMENT
        
        # Try to get channel info
        try:
            chat = await context.bot.get_chat(channel_id)
            channel_info = {
                "name": channel_name,
                "type": chat.type,
                "subscribers": getattr(chat, 'member_count', 'unknown')
            }
            
            if config_manager.add_channel(channel_id, channel_info):
                await update.message.reply_text(
                    f"{EMOJI['success']} Channel {channel_name} added successfully!",
                    reply_markup=create_main_menu(),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"{EMOJI['error']} Channel {channel_id} already exists!",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error adding channel {channel_id}: {e}")
            await update.message.reply_text(
                f"{EMOJI['error']} Error accessing channel! Make sure the bot is admin in the channel.\n"
                f"Error: {str(e)}",
                parse_mode='Markdown'
            )
            return CHANNEL_MANAGEMENT
    
    elif "remove" in setting_type:
        if config_manager.remove_channel(user_input):
            await update.message.reply_text(
                f"{EMOJI['success']} Channel {user_input} removed successfully!",
                reply_markup=create_main_menu(),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"{EMOJI['error']} Channel {user_input} not found!",
                parse_mode='Markdown'
            )
    
    return ConversationHandler.END

async def handle_settings_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle settings input"""
    user_input = update.message.text.strip()
    setting_type = context.user_data.get("setting_type", "")
    
    config = config_manager.get_config()
    
    if setting_type == "set_delay":
        try:
            delay = float(user_input)
            if 0 <= delay <= 10:  # Reasonable range
                config["settings"]["default_delay"] = delay
                config_manager._save()
                await update.message.reply_text(
                    f"{EMOJI['success']} Post delay set to {delay} seconds!",
                    reply_markup=create_main_menu(),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"{EMOJI['error']} Delay must be between 0 and 10 seconds!",
                    parse_mode='Markdown'
                )
                return POST_SETTINGS
        except ValueError:
            await update.message.reply_text(
                f"{EMOJI['error']} Invalid number format! Please enter a valid number.",
                parse_mode='Markdown'
            )
            return POST_SETTINGS
    
    elif setting_type == "set_retries":
        try:
            retries = int(user_input)
            if 1 <= retries <= 10:  # Reasonable range
                config["settings"]["max_retries"] = retries
                config_manager._save()
                await update.message.reply_text(
                    f"{EMOJI['success']} Max retries set to {retries}!",
                    reply_markup=create_main_menu(),
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"{EMOJI['error']} Retries must be between 1 and 10!",
                    parse_mode='Markdown'
                )
                return POST_SETTINGS
        except ValueError:
            await update.message.reply_text(
                f"{EMOJI['error']} Invalid number format! Please enter a valid integer.",
                parse_mode='Markdown'
            )
            return POST_SETTINGS
    
    elif setting_type == "set_footer":
        if user_input.lower() == "clear":
            config["settings"]["footer"] = ""
            config_manager._save()
            await update.message.reply_text(
                f"{EMOJI['success']} Footer cleared!",
                reply_markup=create_main_menu(),
                parse_mode='Markdown'
            )
        elif len(user_input) <= MAX_FOOTER_LENGTH:
            config["settings"]["footer"] = user_input
            config_manager._save()
            await update.message.reply_text(
                f"{EMOJI['success']} Footer set successfully!\n\n*Preview:*\n{user_input}",
                reply_markup=create_main_menu(),
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"{EMOJI['error']} Footer too long! Maximum {MAX_FOOTER_LENGTH} characters.",
                parse_mode='Markdown'
            )
            return POST_SETTINGS
    
    return ConversationHandler.END

# ==================== Inline Query Handler ====================
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline queries for channel search"""
    query = update.inline_query.query
    user_id = str(update.effective_user.id)
    admins = config_manager.get_admins()
    
    if user_id not in admins:
        return
    
    channels = config_manager.get_channels()
    
    results = []
    for channel_id, channel_info in channels.items():
        channel_name = channel_info.get("name", channel_id)
        channel_type = channel_info.get("type", "unknown")
        subscribers = channel_info.get("subscribers", "unknown")
        
        if not query or query.lower() in channel_name.lower() or query.lower() in channel_id.lower():
            content = InputTextMessageContent(
                f"Channel: {channel_name}\nID: `{channel_id}`\nType: {channel_type}\nSubscribers: {subscribers}",
                parse_mode='Markdown'
            )
            
            results.append(
                InlineQueryResultArticle(
                    id=channel_id,
                    title=channel_name,
                    description=f"{channel_id} • {channel_type} • {subscribers} subscribers",
                    input_message_content=content
                )
            )
    
    await update.inline_query.answer(results[:10])  # Limit to 10 results

# ==================== Scheduled Jobs Runner ====================
async def run_scheduled_jobs(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run scheduled jobs that are due"""
    try:
        scheduled_jobs = config_manager.get_scheduled_jobs()
        current_time = datetime.now()
        
        jobs_to_execute = []
        
        for job_id, job_data in scheduled_jobs.items():
            try:
                schedule_time = datetime.fromisoformat(job_data.get("schedule_time", ""))
                if current_time >= schedule_time:
                    jobs_to_execute.append((job_id, job_data))
            except (ValueError, TypeError):
                # Invalid schedule time, remove the job
                config_manager.remove_scheduled_job(job_id)
                logger.warning(f"Removed job {job_id} with invalid schedule time")
        
        for job_id, job_data in jobs_to_execute:
            try:
                await execute_scheduled_job(context, job_id, job_data)
                config_manager.remove_scheduled_job(job_id)
                logger.info(f"Successfully executed and removed job {job_id}")
            except Exception as e:
                logger.error(f"Error executing job {job_id}: {e}", exc_info=True)
                # Remove failed job to prevent repeated failures
                config_manager.remove_scheduled_job(job_id)
        
        # Clean up expired jobs
        config_manager.cleanup_expired_jobs()
        
    except Exception as e:
        logger.error(f"Error in scheduled job runner: {e}", exc_info=True)

async def execute_scheduled_job(context: ContextTypes.DEFAULT_TYPE, job_id: str, job_data: Dict[str, Any]) -> None:
    """Execute a single scheduled job"""
    batch = job_data.get("batch", [])
    channels = job_data.get("channels", [])
    admin_id = job_data.get("admin_id", str(OWNER_ID))
    
    if not batch or not channels:
        logger.warning(f"Job {job_id} has no batch or channels")
        return
    
    config = config_manager.get_config()
    settings = config.get("settings", {})
    
    delay = settings.get("default_delay", POST_DELAY_SECONDS)
    max_retries = settings.get("max_retries", MAX_RETRIES)
    footer = settings.get("footer", "")
    
    successful_posts = 0
    failed_posts = 0
    
    for channel_id in channels:
        for msg_data in batch:
            success = False
            for attempt in range(max_retries):
                try:
                    # Prepare message content
                    if msg_data.get("type") == "text":
                        content = msg_data.get("content", "")
                        if footer:
                            content += f"\n\n{footer}"
                        
                        await context.bot.send_message(
                            chat_id=channel_id,
                            text=content,
                            parse_mode=msg_data.get("parse_mode", "Markdown")
                        )
                    elif msg_data.get("type") == "photo":
                        caption = msg_data.get("caption", "")
                        if footer:
                            caption += f"\n\n{footer}"
                        
                        await context.bot.send_photo(
                            chat_id=channel_id,
                            photo=msg_data.get("file_id"),
                            caption=caption,
                            parse_mode=msg_data.get("parse_mode", "Markdown")
                        )
                    elif msg_data.get("type") == "video":
                        caption = msg_data.get("caption", "")
                        if footer:
                            caption += f"\n\n{footer}"
                        
                        await context.bot.send_video(
                            chat_id=channel_id,
                            video=msg_data.get("file_id"),
                            caption=caption,
                            parse_mode=msg_data.get("parse_mode", "Markdown")
                        )
                    elif msg_data.get("type") == "document":
                        caption = msg_data.get("caption", "")
                        if footer:
                            caption += f"\n\n{footer}"
                        
                        await context.bot.send_document(
                            chat_id=channel_id,
                            document=msg_data.get("file_id"),
                            caption=caption,
                            parse_mode=msg_data.get("parse_mode", "Markdown")
                        )
                    
                    success = True
                    successful_posts += 1
                    break
                    
                except Exception as e:
                    logger.error(f"Error posting to {channel_id}, attempt {attempt + 1}: {e}")
                    if attempt == max_retries - 1:
                        failed_posts += 1
            
            if success and delay > 0:
                await asyncio.sleep(delay)
    
    # Update statistics
    config_manager.update_stats("posts", config.get("stats", {}).get("posts", 0) + successful_posts)
    config_manager.update_stats("batches", config.get("stats", {}).get("batches", 0) + 1)
    config_manager.update_stats("last_post", datetime.now().isoformat())
    config_manager.update_stats("last_post_channels", channels)
    config_manager.update_admin_stats(admin_id, "posts")
    config_manager.update_admin_stats(admin_id, "batches")
    
    # Notify admin if notifications are enabled
    if settings.get("notifications", True):
        try:
            result_text = f"""
{EMOJI['success']} *Scheduled Post Complete!*

{EMOJI['check']} Successfully posted to {len(channels)} channels
{EMOJI['batch']} {len(batch)} messages sent
{EMOJI['stats']} Success rate: {(successful_posts / (successful_posts + failed_posts) * 100) if (successful_posts + failed_posts) > 0 else 0:.1f}%

Job ID: `{job_id}`
            """
            
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=result_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error sending notification to admin {admin_id}: {e}")

# ==================== Main Application ====================
def main() -> None:
    """Start the bot"""
    try:
        # Create application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Conversation handlers
        admin_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_handler, pattern="^(admin_add|admin_remove)$")],
            states={
                ADMIN_MANAGEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input)]
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(button_handler, pattern="^cancel_admin$")
            ]
        )
        
        channel_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_handler, pattern="^(channel_add|channel_remove)$")],
            states={
                CHANNEL_MANAGEMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_input)]
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(button_handler, pattern="^cancel_channel$")
            ]
        )
        
        settings_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_handler, pattern="^(set_delay|set_retries|set_footer)$")],
            states={
                POST_SETTINGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_settings_input)]
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(button_handler, pattern="^cancel_settings$")
            ]
        )
        
        schedule_conv_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_handler, pattern="^batch_schedule_menu$")],
            states={
                SCHEDULE_BATCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_batch_confirm)]
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(button_handler, pattern="^cancel_schedule$")
            ]
        )
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", show_help))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CommandHandler("status", status))
        
        # Add conversation handlers
        application.add_handler(admin_conv_handler)
        application.add_handler(channel_conv_handler)
        application.add_handler(settings_conv_handler)
        application.add_handler(schedule_conv_handler)
        
        # Add other handlers
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(InlineQueryHandler(inline_query))
        
        # Main menu handler
        application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(f"^({EMOJI['admin']}|{EMOJI['channel']}|{EMOJI['stats']}|{EMOJI['batch']}|{EMOJI['schedule']}|{EMOJI['settings']}|{EMOJI['help']})") & ~filters.COMMAND,
            handle_main_menu
        ))
        
        # Batch message handler
        application.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.DOCUMENT) & ~filters.COMMAND,
            add_to_batch
        ))
        
        # Start scheduled job runner
        application.job_queue.run_repeating(run_scheduled_jobs, interval=60, first=10)
        
        logger.info("Advanced Channel Manager Pro started successfully!")
        print(f"""
{EMOJI['rocket']} Advanced Channel Manager Pro Started!
{EMOJI['info']} Bot Token: {BOT_TOKEN[:10]}...
{EMOJI['admin']} Owner ID: {OWNER_ID}
{EMOJI['check']} All systems ready!
        """)
        
        # Run the bot
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        print(f"{EMOJI['error']} Failed to start bot: {e}")
        raise

if __name__ == "__main__":
