def is_valid_channel_id(channel_id):
    return isinstance(channel_id, (int, str)) and str(channel_id).startswith("-100")

def is_valid_user_id(user_id):
    return isinstance(user_id, int) and user_id > 0

def is_valid_time_format(time_str):
    # Basic validation for HH:MM format
    try:
        h, m = map(int, time_str.split(":"))
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


