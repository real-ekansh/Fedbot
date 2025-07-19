# ping_uptime.py - Telegram Bot Module

import time
from datetime import datetime

class PingUptime:
    def __init__(self):
        self.start_time = time.time()
    
    def ping_command(self, update, context):
        """Handle /ping command with bot response ping"""
        # Calculate bot response time
        start_time = time.time()
        
        # Send initial message
        message = update.message.reply_text("*Checking ping...*", parse_mode='Markdown')
        
        # Calculate response time
        end_time = time.time()
        bot_ping = round((end_time - start_time) * 1000)
        
        # Calculate uptime
        uptime_seconds = int(time.time() - self.start_time)
        uptime_str = self.format_uptime(uptime_seconds)
        
        # Format response
        response = f"*Pong!*\n\n"
        response += f"*Bot Ping:* `{bot_ping}ms`\n"
        response += f"*Uptime:* `{uptime_str}`"
        response += f"\n*Last Check:* `{datetime.now().strftime('%H:%M:%S')}`"
        
        # Edit the message with results
        message.edit_text(response, parse_mode='Markdown')

    
    def format_uptime(self, seconds):
        """Format uptime seconds into readable string"""
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m {seconds}s"
        elif hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

# Create module instance
ping_uptime = PingUptime()

# Export the handler function
def setup_ping_handler(application):
    """Setup ping command handler"""
    from telegram.ext import CommandHandler
    application.add_handler(CommandHandler("ping", ping_uptime.ping_command))

def ping_handler(update, context):
    """Direct ping handler function"""
    ping_uptime.ping_command(update, context)
