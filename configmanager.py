import os
import json
from dotenv import load_dotenv

class ConfigManager:
    def __init__(self):
        load_dotenv()
        self.bot_token = os.getenv('BOT_TOKEN')
        self.admin_ids = self._load_admin_ids()
        self.fixed_channels_file = 'config/fixed_channels.json'

    def _load_admin_ids(self):
        admin_ids_str = os.getenv('ADMIN_IDS')
        if admin_ids_str:
            return [int(uid.strip()) for uid in admin_ids_str.split(',')]
        return []

    def get_bot_token(self):
        return self.bot_token

    def get_admin_ids(self):
        return self.admin_ids

    def get_fixed_channels(self):
        if os.path.exists(self.fixed_channels_file):
            with open(self.fixed_channels_file, 'r') as f:
                return json.load(f)
        return []

    def add_fixed_channel(self, channel_id, channel_name):
        channels = self.get_fixed_channels()
        channels.append({'id': channel_id, 'name': channel_name})
        with open(self.fixed_channels_file, 'w') as f:
            json.dump(channels, f, indent=4)

    def remove_fixed_channel(self, channel_id):
        channels = self.get_fixed_channels()
        channels = [c for c in channels if c['id'] != channel_id]
        with open(self.fixed_channels_file, 'w') as f:
            json.dump(channels, f, indent=4)


