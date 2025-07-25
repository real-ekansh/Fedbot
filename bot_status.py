import platform
import psutil
import subprocess
import sys
import sqlite3
import time
import os
import asyncio
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    try:
        from importlib_metadata import version, PackageNotFoundError
    except ImportError:
        def version(package_name): return "Unknown"
        PackageNotFoundError = Exception

class BotStatusMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.bot_state = "Online and operational"
    
    def get_bot_uptime(self):
        uptime_seconds = time.time() - self.start_time
        return str(timedelta(seconds=int(uptime_seconds)))
    
    def get_system_uptime(self):
        try:
            return str(timedelta(seconds=int(time.time() - psutil.boot_time())))
        except Exception:
            return "Unknown"
    
    def get_os_info(self):
        return f"{platform.system()} {platform.release()}"
    
    def get_hostname(self):
        return platform.node()
        
    def get_kernel_version(self):
        return platform.version()

    def get_package_count(self):
        try:
            if platform.system() == "Linux":
                managers = [(['dpkg', '--get-selections'], "dpkg"), (['rpm', '-qa'], "rpm"), (['pacman', '-Q'], "pacman")]
                for cmd, name in managers:
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            return f"{len(result.stdout.strip().splitlines())} ({name})"
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        continue
            result = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return f"{max(0, len(result.stdout.strip().splitlines()) - 2)} (pip)"
            return "Unknown"
        except Exception:
            return "Unknown"

    def get_shell_info(self):
        return os.path.basename(os.environ.get('SHELL', 'Unknown'))
    
    def get_memory_info(self):
        try:
            mem = psutil.virtual_memory()
            return f"{mem.used / (1024**3):.1f}GB / {mem.total / (1024**3):.1f}GB ({mem.percent}%)"
        except Exception:
            return "Unknown"

    def get_python_version(self):
        return sys.version.split()[0]
    
    def get_package_version(self, package_name):
        try:
            return version(package_name)
        except PackageNotFoundError:
            return "Not installed"
        except Exception:
            return "Unknown"
    
    def get_sqlite_version(self):
        return sqlite3.sqlite_version
    
    def set_bot_state(self, state):
        self.bot_state = state
    
    def escape_markdown(self, text):
        special_chars = r'_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in special_chars else char for char in str(text))
    
    async def get_status_report_async(self, use_markdown=True):
        # Run blocking I/O in a separate thread
        package_count = await asyncio.to_thread(self.get_package_count)
        
        if use_markdown:
            esc = self.escape_markdown
            return (f"*Bot Status:*\n"
                    f"• State: {esc(self.bot_state)}\n"
                    f"• Uptime: {esc(self.get_bot_uptime())}\n\n"
                    f"*System Info:*\n"
                    f"OS: {esc(self.get_os_info())}\n"
                    f"Host: {esc(self.get_hostname())}\n"
                    f"Kernel: {esc(self.get_kernel_version())}\n"
                    f"Uptime: {esc(self.get_system_uptime())}\n"
                    f"Packages: {esc(package_count)}\n"
                    f"Shell: {esc(self.get_shell_info())}\n"
                    f"Memory: {esc(self.get_memory_info())}\n\n"
                    f"*Software Info:*\n"
                    f"• Python: {esc(self.get_python_version())}\n"
                    f"• python\\-telegram\\-bot: {esc(self.get_package_version('python-telegram-bot'))}\n"
                    f"• SQLite: {esc(self.get_sqlite_version())}")
        else:
            return (f"Bot Status:\n"
                    f"• State: {self.bot_state}\n"
                    f"• Uptime: {self.get_bot_uptime()}\n\n"
                    f"System Info:\n"
                    f"OS: {self.get_os_info()}\n..."
                   ) # Plain text version is simplified as it's a fallback

_global_status_monitor = BotStatusMonitor()

async def async_status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        status_report = await _global_status_monitor.get_status_report_async(use_markdown=True)
        await update.message.reply_text(status_report, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        try:
            status_report = await _global_status_monitor.get_status_report_async(use_markdown=False)
            await update.message.reply_text(status_report)
        except Exception as e2:
            await update.message.reply_text(f"Error getting status: {str(e2)}")

if __name__ == "__main__":
    async def run_test():
        print(await _global_status_monitor.get_status_report_async())
    asyncio.run(run_test())
