import time
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

class PingUptime:
    def __init__(self):
        self.start_time = time.time()
    
    async def ping_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        start_ts = time.time()
        message = await update.message.reply_text("*Checking ping...*", parse_mode=ParseMode.MARKDOWN)
        end_ts = time.time()
        
        bot_ping = round((end_ts - start_ts) * 1000)
        
        uptime_seconds = int(time.time() - self.start_time)
        uptime_str = self.format_uptime(uptime_seconds)
        
        response = (f"*Pong!*\n\n"
                    f"*Bot Ping:* `{bot_ping}ms`\n"
                    f"*Uptime:* `{uptime_str}`"
                    f"\n*Last Check:* `{datetime.now().strftime('%H:%M:%S')}`")
        
        await message.edit_text(response, parse_mode=ParseMode.MARKDOWN)

    def format_uptime(self, seconds: int) -> str:
        days, rem = divmod(seconds, 86400)
        hours, rem = divmod(rem, 3600)
        minutes, secs = divmod(rem, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m {secs}s"
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        if minutes > 0:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

_ping_uptime_instance = PingUptime()

# Expose the async command function directly
ping_command = _ping_uptime_instance.ping_command
