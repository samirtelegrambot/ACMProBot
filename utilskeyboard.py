from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("Channels"), KeyboardButton("Batch")],
        [KeyboardButton("Schedule"), KeyboardButton("Post")],
        [KeyboardButton("Settings"), KeyboardButton("Admin")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def back_button_keyboard():
    keyboard = [[KeyboardButton("Back to Main Menu")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def confirm_post_keyboard():
    keyboard = [
        [InlineKeyboardButton("Confirm Post", callback_data="confirm_post")],
        [InlineKeyboardButton("Cancel", callback_data="cancel_post")]
    ]
    return InlineKeyboardMarkup(keyboard)

def channel_list_keyboard(channels):
    buttons = []
    for channel in channels:
        buttons.append([InlineKeyboardButton(channel["name"], callback_data=f"channel_{channel["id"]}")])
    buttons.append([InlineKeyboardButton("Add Channel", callback_data="add_channel")])
    return InlineKeyboardMarkup(buttons)

def channel_manage_keyboard(channel_id):
    keyboard = [
        [InlineKeyboardButton("Remove Channel", callback_data=f"remove_channel_{channel_id}")],
        [InlineKeyboardButton("Back to Channels", callback_data="back_to_channels")]
    ]
    return InlineKeyboardMarkup(keyboard)

def schedule_options_keyboard():
    keyboard = [
        [InlineKeyboardButton("View Scheduled Posts", callback_data="view_scheduled")],
        [InlineKeyboardButton("Schedule New Post", callback_data="schedule_new")]
    ]
    return InlineKeyboardMarkup(keyboard)

def settings_keyboard():
    keyboard = [
        [InlineKeyboardButton("Set Delay", callback_data="set_delay")],
        [InlineKeyboardButton("Set Retry Attempts", callback_data="set_retry")],
        [InlineKeyboardButton("Set Footer", callback_data="set_footer")]
    ]
    return InlineKeyboardMarkup(keyboard)


