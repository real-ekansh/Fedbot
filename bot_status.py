import platform
import psutil
import subprocess
import sys
import sqlite3
import time
import os
from datetime import datetime, timedelta

try:
    from importlib.metadata import version, PackageNotFoundError
except ImportError:
    # Fallback for Python < 3.8
    try:
        from importlib_metadata import version, PackageNotFoundError
    except ImportError:
        # If importlib_metadata is not available, create dummy functions
        def version(package_name):
            return "Unknown"
        PackageNotFoundError = Exception


class BotStatusMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.bot_state = "Online and operational"
    
    def get_bot_uptime(self):
        """Calculate bot uptime since initialization"""
        uptime_seconds = time.time() - self.start_time
        uptime_delta = timedelta(seconds=int(uptime_seconds))
        return str(uptime_delta)
    
    def get_system_uptime(self):
        """Get system uptime"""
        try:
            uptime_seconds = time.time() - psutil.boot_time()
            uptime_delta = timedelta(seconds=int(uptime_seconds))
            return str(uptime_delta)
        except Exception:
            return "Unknown"
    
    def get_os_info(self):
        """Get operating system information"""
        try:
            return f"{platform.system()} {platform.release()}"
        except Exception:
            return "Unknown"
    
    def get_hostname(self):
        """Get system hostname"""
        try:
            return platform.node()
        except Exception:
            return "Unknown"
    
    def get_kernel_version(self):
        """Get kernel version"""
        try:
            return platform.version()
        except Exception:
            return "Unknown"
    
    def get_package_count(self):
        """Get number of installed packages (varies by OS)"""
        try:
            if platform.system() == "Linux":
                # Try different package managers
                package_managers = [
                    (['dpkg', '--get-selections'], "dpkg"),
                    (['rpm', '-qa'], "rpm"),
                    (['pacman', '-Q'], "pacman")
                ]
                
                for cmd, manager in package_managers:
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            count = len(result.stdout.strip().split('\n'))
                            return f"{count} ({manager})"
                    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
                        continue
            
            # Fallback to Python packages
            try:
                result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                                      capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    return f"{max(0, len(lines) - 2)} (Python packages)"
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
            
            return "Unknown"
        except Exception:
            return "Unknown"
    
    def get_shell_info(self):
        """Get shell information"""
        try:
            shell = os.environ.get('SHELL', 'Unknown')
            if shell != 'Unknown':
                return os.path.basename(shell)
            return shell
        except Exception:
            return "Unknown"
    
    def get_memory_info(self):
        """Get memory usage information"""
        try:
            memory = psutil.virtual_memory()
            used_gb = memory.used / (1024**3)
            total_gb = memory.total / (1024**3)
            percentage = memory.percent
            return f"{used_gb:.1f}GB / {total_gb:.1f}GB ({percentage}%)"
        except Exception:
            return "Unknown"
    
    def get_python_version(self):
        """Get Python version"""
        try:
            return f"{sys.version.split()[0]}"
        except Exception:
            return "Unknown"
    
    def get_package_version(self, package_name):
        """Get version of a specific package"""
        try:
            return version(package_name)
        except PackageNotFoundError:
            return "Not installed"
        except Exception:
            return "Unknown"
    
    def get_sqlite_version(self):
        """Get SQLite version"""
        try:
            return sqlite3.sqlite_version
        except Exception:
            return "Unknown"
    
    def set_bot_state(self, state):
        """Update bot state"""
        self.bot_state = state
    
    def get_status_report(self):
        """Generate complete status report in the exact format requested"""
        report = f"""**Bot Status:**
• State: {self.bot_state}
• Uptime: {self.get_bot_uptime()}

**System Info:**
OS: {self.get_os_info()}
Host: {self.get_hostname()}
Kernel: {self.get_kernel_version()}
Uptime: {self.get_system_uptime()}
Packages: {self.get_package_count()}
Shell: {self.get_shell_info()}
Memory: {self.get_memory_info()}

**Software Info:**
• Python: {self.get_python_version()}
• python-telegram-bot: {self.get_package_version('python-telegram-bot')}
• SQLite: {self.get_sqlite_version()}"""
        return report
    
    def get_status_dict(self):
        """Return status as dictionary for programmatic use"""
        return {
            'bot_status': {
                'state': self.bot_state,
                'uptime': self.get_bot_uptime()
            },
            'system_info': {
                'os': self.get_os_info(),
                'host': self.get_hostname(),
                'kernel': self.get_kernel_version(),
                'uptime': self.get_system_uptime(),
                'packages': self.get_package_count(),
                'shell': self.get_shell_info(),
                'memory': self.get_memory_info()
            },
            'software_info': {
                'python': self.get_python_version(),
                'python_telegram_bot': self.get_package_version('python-telegram-bot'),
                'telethon': self.get_package_version('telethon'),
                'sqlite': self.get_sqlite_version()
            }
        }


# Global status monitor instance
_global_status_monitor = None


def get_global_monitor():
    """Get or create global status monitor"""
    global _global_status_monitor
    if _global_status_monitor is None:
        _global_status_monitor = BotStatusMonitor()
    return _global_status_monitor


def set_bot_state(state):
    """Set bot state globally"""
    monitor = get_global_monitor()
    monitor.set_bot_state(state)


def get_bot_uptime():
    """Get bot uptime"""
    monitor = get_global_monitor()
    return monitor.get_bot_uptime()


def get_bot_status():
    """Simple function to get bot status - uses global monitor"""
    monitor = get_global_monitor()
    return monitor.get_status_report()


# Telegram bot integration class
class TelegramBotWithStatus:
    def __init__(self):
        self.status_monitor = BotStatusMonitor()
    
    def status_command(self, update, context):
        """Handler for /status command (sync version)"""
        try:
            status_report = self.status_monitor.get_status_report()
            update.message.reply_text(status_report, parse_mode='Markdown')
        except Exception as e:
            update.message.reply_text(f"Error getting status: {str(e)}")
    
    async def async_status_command(self, update, context):
        """Handler for /status command (async version)"""
        try:
            status_report = self.status_monitor.get_status_report()
            await update.message.reply_text(status_report, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"Error getting status: {str(e)}")
    
    def update_bot_state(self, new_state):
        """Update bot state"""
        self.status_monitor.set_bot_state(new_state)
    
    def get_quick_status(self):
        """Get quick status for logging"""
        return f"Bot: {self.status_monitor.bot_state} | Uptime: {self.status_monitor.get_bot_uptime()}"


# Standalone handler functions
def status_handler(update, context):
    """Status handler function that can be imported directly (sync version)"""
    try:
        status_report = get_bot_status()
        update.message.reply_text(status_report, parse_mode='Markdown')
    except Exception as e:
        update.message.reply_text(f"Error getting status: {str(e)}")


async def async_status_handler(update, context):
    """Async status handler function for newer python-telegram-bot versions"""
    try:
        status_report = get_bot_status()
        await update.message.reply_text(status_report, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"Error getting status: {str(e)}")


# Example usage
if __name__ == "__main__":
    # Initialize the status monitor
    status_monitor = BotStatusMonitor()
    
    # Print the complete status report
    print(status_monitor.get_status_report())
    
    # Example of using global functions
    print("\nUsing global functions:")
    print(get_bot_status())


# Usage examples:
# 1. Direct usage:
# print(get_bot_status())

# 2. Class-based usage:
# status = BotStatusMonitor()
# print(status.get_status_report())

# 3. Telegram bot integration:
# bot = TelegramBotWithStatus()
# application.add_handler(CommandHandler("status", bot.status_command))

# 4. Using standalone handlers:
# application.add_handler(CommandHandler("status", status_handler))  # sync
# application.add_handler(CommandHandler("status", async_status_handler))  # async
