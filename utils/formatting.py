import datetime

def format_timestamp(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

def escape_markdown_v2(text):
    escape_chars = "._*-[]()~`>#+-=|{}!"
    return "".join([f"\\{char}" if char in escape_chars else char for char in text])


