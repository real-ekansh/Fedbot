import logging
import os
import sqlite3
import subprocess
import html
import io
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, MessageHandler, Filters
from telegram.error import TelegramError
from dotenv import load_dotenv
import sys

# from botlog import PTBLogger
from bot_status import status_handler
from ping_module import ping_uptime

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIG ---
try:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    # Parse multiple admin IDs from environment
    ADMIN_IDS = []
    admin_ids_str = os.getenv('ADMIN_IDS', '')
    if admin_ids_str:
        ADMIN_IDS = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip().isdigit()]
    
    # Legacy support for single ADMIN_ID
    legacy_admin_id = os.getenv('ADMIN_ID', '')
    if legacy_admin_id and legacy_admin_id.isdigit():
        legacy_admin_id = int(legacy_admin_id)
        if legacy_admin_id not in ADMIN_IDS:
            ADMIN_IDS.append(legacy_admin_id)
    
    OWNER_ID = int(os.getenv('OWNER_ID', 0))  # Added OWNER_ID for shell access
    DB_PATH = os.getenv('DB_PATH', 'appeals.db')
    
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is required")
    if not ADMIN_IDS:
        raise ValueError("ADMIN_IDS or ADMIN_ID environment variable is required")
    if not OWNER_ID:
        logger.warning("OWNER_ID not set, shell commands will be disabled")
        
    logger.info(f"Configured with {len(ADMIN_IDS)} admin(s): {ADMIN_IDS}")
    if OWNER_ID:
        logger.info(f"Owner ID: {OWNER_ID}")
        
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"Unexpected configuration error: {e}")
    sys.exit(1)

# --- Database Setup ---
def init_db():
    """Initialize the database with proper error handling"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS appeals
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER NOT NULL,
                     username TEXT,
                     appeal_type TEXT NOT NULL,
                     appeal_text TEXT,
                     status TEXT DEFAULT "pending",
                     timestamp TEXT NOT NULL,
                     created_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected database error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

def get_db_connection():
    """Get database connection with error handling"""
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        return None

# --- Admin Management Commands ---
def add_admin(update: Update, context: CallbackContext):
    """Add a new admin (owner only)"""
    try:
        if not OWNER_ID or update.effective_user.id != OWNER_ID:
            update.message.reply_text("❌ Access denied. Only the bot owner can use this command.")
            return
            
        if not context.args:
            update.message.reply_text("❌ Usage: /addadmin <user_id>")
            return
            
        try:
            new_admin_id = int(context.args[0])
        except ValueError:
            update.message.reply_text("❌ Invalid user ID. Please provide a valid number.")
            return
            
        if new_admin_id in ADMIN_IDS:
            update.message.reply_text(f"❌ User {new_admin_id} is already an admin.")
            return
            
        ADMIN_IDS.append(new_admin_id)
        update.message.reply_text(f"✅ User {new_admin_id} has been added as an admin.")
        logger.info(f"Owner {update.effective_user.id} added {new_admin_id} as admin")
        
        # Notify the new admin
        try:
            context.bot.send_message(
                new_admin_id,
                "🎉 You have been granted admin access to the Appeals Bot!\n\n"
                "Available admin commands:\n"
                "• /pending - View pending appeals\n"
                "• /view <appeal_id> - View full appeal details\n"
                "• /approve <appeal_id> - Approve an appeal\n"
                "• /reject <appeal_id> - Reject an appeal\n"
                "• /stats - View appeal statistics\n"
                "• /admins - List all admins"
            )
        except TelegramError as e:
            logger.error(f"Failed to notify new admin {new_admin_id}: {e}")
            update.message.reply_text(f"Admin added but failed to notify them.")
            
    except TelegramError as e:
        logger.error(f"Telegram error in add_admin: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in add_admin: {e}")

def remove_admin(update: Update, context: CallbackContext):
    """Remove an admin (owner only)"""
    try:
        if not OWNER_ID or update.effective_user.id != OWNER_ID:
            update.message.reply_text("❌ Access denied. Only the bot owner can use this command.")
            return
            
        if not context.args:
            update.message.reply_text("❌ Usage: /removeadmin <user_id>")
            return
            
        try:
            admin_id = int(context.args[0])
        except ValueError:
            update.message.reply_text("❌ Invalid user ID. Please provide a valid number.")
            return
            
        if admin_id not in ADMIN_IDS:
            update.message.reply_text(f"❌ User {admin_id} is not an admin.")
            return
            
        ADMIN_IDS.remove(admin_id)
        update.message.reply_text(f"✅ User {admin_id} has been removed from admin list.")
        logger.info(f"Owner {update.effective_user.id} removed {admin_id} from admin list")
        
        # Notify the removed admin
        try:
            context.bot.send_message(
                admin_id,
                "🚫 Your admin access to the Appeals Bot has been revoked."
            )
        except TelegramError as e:
            logger.error(f"Failed to notify removed admin {admin_id}: {e}")
            
    except TelegramError as e:
        logger.error(f"Telegram error in remove_admin: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in remove_admin: {e}")

def list_admins(update: Update, context: CallbackContext):
    """List all admins (admin/owner only)"""
    try:
        if not is_admin_or_owner(update.effective_user.id):
            update.message.reply_text("❌ Access denied.")
            return
            
        admin_list = "\n".join([f"• {admin_id}" for admin_id in ADMIN_IDS])
        owner_info = f"\n👑 Owner: {OWNER_ID}" if OWNER_ID else ""
        
        response = (
            f"👥 <b>Admin List ({len(ADMIN_IDS)} admins)</b>\n\n"
            f"{admin_list}"
            f"{owner_info}\n\n"
            f"Total authorized users: {len(ADMIN_IDS) + (1 if OWNER_ID else 0)}"
        )
        
        update.message.reply_text(response, parse_mode=ParseMode.HTML)
        logger.info(f"Admin list viewed by {update.effective_user.id}")
        
    except TelegramError as e:
        logger.error(f"Telegram error in list_admins: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in list_admins: {e}")

# --- Shell Command Support ---
def shell_command(update: Update, context: CallbackContext):
    """Execute shell commands (owner only)"""
    try:
        # Check if OWNER_ID is set and user is owner
        if not OWNER_ID or update.effective_user.id != OWNER_ID:
            update.message.reply_text("❌ Access denied. Only the bot owner can use this command.")
            return
            
        if not context.args:
            update.message.reply_text(
                "❌ Usage: /shell <command>\n"
                "Example: /shell ls -la\n"
                "⚠️ Use with caution - this executes system commands!"
            )
            return
            
        command = ' '.join(context.args)
        
        # Log the command execution
        logger.info(f"Owner {update.effective_user.id} executing shell command: {command}")
        
        # Show "typing" status
        context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        try:
            # Execute command with timeout
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
                cwd=os.getcwd()
            )
            
            # Prepare output
            output = ""
            if result.stdout:
                output += f"📤 <b>STDOUT:</b>\n<pre>{html.escape(result.stdout)}</pre>\n"
            if result.stderr:
                output += f"🚨 <b>STDERR:</b>\n<pre>{html.escape(result.stderr)}</pre>\n"
                
            output += f"\n📊 <b>Return code:</b> {result.returncode}"
            output += f"\n🕐 <b>Command:</b> <code>{html.escape(command)}</code>"
            
            # Handle long outputs
            if len(output) > 4000:
                # Send as file if output is too long
                output_file = io.BytesIO(
                    f"Command: {command}\n"
                    f"Return code: {result.returncode}\n"
                    f"STDOUT:\n{result.stdout}\n"
                    f"STDERR:\n{result.stderr}".encode()
                )
                output_file.name = f"shell_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                
                update.message.reply_document(
                    document=output_file,
                    caption=f"📁 Output too long, sent as file\n"
                           f"Command: <code>{html.escape(command)}</code>\n"
                           f"Return code: {result.returncode}",
                    parse_mode=ParseMode.HTML
                )
            else:
                update.message.reply_text(output, parse_mode=ParseMode.HTML)
                
        except subprocess.TimeoutExpired:
            update.message.reply_text(
                f"⏰ <b>Command timed out after 30 seconds</b>\n"
                f"Command: <code>{html.escape(command)}</code>",
                parse_mode=ParseMode.HTML
            )
        except subprocess.SubprocessError as e:
            update.message.reply_text(
                f"❌ <b>Subprocess error:</b>\n<pre>{html.escape(str(e))}</pre>\n"
                f"Command: <code>{html.escape(command)}</code>",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            update.message.reply_text(
                f"❌ <b>Execution error:</b>\n<pre>{html.escape(str(e))}</pre>\n"
                f"Command: <code>{html.escape(command)}</code>",
                parse_mode=ParseMode.HTML
            )
            
    except TelegramError as e:
        logger.error(f"Telegram error in shell command: {e}")
        try:
            update.message.reply_text("❌ Failed to send command output due to Telegram error.")
        except:
            pass
    except Exception as e:
        logger.error(f"Unexpected error in shell command: {e}")
        try:
            update.message.reply_text(f"❌ Unexpected error: {str(e)}")
        except:
            pass

# --- User Commands ---
def start(update: Update, context: CallbackContext):
    """Start command handler"""
    try:
        update.message.reply_text(
            "📝 Welcome to the Appeals Bot!\n\n"
            "Use /appeal to submit a FedBan appeal or request Fed Admin status"
        )
        logger.info(f"User {update.effective_user.id} started the bot")
    except TelegramError as e:
        logger.error(f"Error in start command: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in start command: {e}")

def appeal(update: Update, context: CallbackContext):
    """Appeal command handler"""
    try:
        keyboard = [
            [InlineKeyboardButton("🔓 Fed Unban Appeal", callback_data="unban")],
            [InlineKeyboardButton("👑 Fed Admin Request", callback_data="admin")]
        ]
        update.message.reply_text(
            "Select appeal type:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"User {update.effective_user.id} requested appeal menu")
    except TelegramError as e:
        logger.error(f"Error in appeal command: {e}")
        update.message.reply_text("❌ An error occurred. Please try again later.")
    except Exception as e:
        logger.error(f"Unexpected error in appeal command: {e}")

# Store temporary data for users writing appeals
user_appeals = {}

def handle_appeal_type(update: Update, context: CallbackContext):
    """Handle appeal type selection"""
    try:
        query = update.callback_query
        query.answer()
        user = query.from_user
        
        # Validate appeal type
        if query.data not in ['unban', 'admin']:
            query.edit_message_text("❌ Invalid appeal type")
            return
        
        # Store appeal type temporarily
        user_appeals[user.id] = {'type': query.data}
        
        # Ask for appeal text with template
        appeal_type = "unban" if query.data == "unban" else "admin request"
        template = ""
        
        if query.data == "unban":
            template = (
                "\n\n📝 Please write your appeal in detail. Example:\n"
                "1. Why were you banned?\n"
                "2. What have you learned from this experience?\n"
                "3. Why should we unban you?\n"
                "4. Any additional information?"
            )
        else:
            template = (
                "\n\n📝 Please write your admin request. Example:\n"
                "1. Why do you want to be an admin?\n"
                "2. What experience do you have?\n"
                "3. How will you help the community?\n"
                "4. Any additional information?"
            )
            
        query.edit_message_text(
            f"✍️ Please write and submit your {appeal_type} appeal.{template}\n\n"
            "Type your appeal now:"
        )
        
        # Set next step to handle appeal text
        context.user_data['expecting_appeal_text'] = True
        context.user_data['appeal_type'] = query.data
        
        logger.info(f"User {user.id} selected {query.data} appeal type")
            
    except TelegramError as e:
        logger.error(f"Telegram error in handle_appeal_type: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_appeal_type: {e}")

def handle_appeal_text(update: Update, context: CallbackContext):
    """Handle user's appeal text submission"""
    try:
        if not context.user_data.get('expecting_appeal_text'):
            return
            
        user = update.message.from_user
        appeal_text = update.message.text
        appeal_type = context.user_data['appeal_type']
        
        # Save to database
        conn = get_db_connection()
        if not conn:
            update.message.reply_text("❌ Database error. Please try again later.")
            return
            
        try:
            c = conn.cursor()
            c.execute('''INSERT INTO appeals 
                        (user_id, username, appeal_type, appeal_text, timestamp)
                        VALUES (?, ?, ?, ?, ?)''',
                     (user.id, user.username or 'No username', appeal_type, appeal_text,
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            appeal_id = c.lastrowid
            
            update.message.reply_text(
                f"✅ {appeal_type.capitalize()} appeal submitted successfully!\n"
                f"Appeal ID: #{appeal_id}\n\n"
                "Your appeal will be reviewed by an admin."
            )
            
            # Prepare notification message
            notification_message = (
                f"🚨 New Appeal #{appeal_id}\n"
                f"User: @{user.username or 'No username'} (ID: {user.id})\n"
                f"Type: {appeal_type.capitalize()}\n"
                f"Time: {datetime.now().strftime('%H:%M %d-%m-%Y')}\n\n"
                f"📝 Appeal Text:\n{appeal_text}\n\n"
                f"Use /approve {appeal_id} to approve\n"
                f"Use /reject {appeal_id} to reject\n\n"
                f"Use /pending to view all pending appeals"
            )
            
            # Notify all admins and owner
            notification_recipients = []
            notification_recipients.extend(ADMIN_IDS)  # Add all admin IDs
            if OWNER_ID and OWNER_ID not in ADMIN_IDS:  # Add owner if not already in admin list
                notification_recipients.append(OWNER_ID)
            
            # Remove duplicates
            notification_recipients = list(set(notification_recipients))
            
            successful_notifications = 0
            for recipient_id in notification_recipients:
                try:
                    context.bot.send_message(recipient_id, notification_message)
                    logger.info(f"Notified {recipient_id} about appeal #{appeal_id}")
                    successful_notifications += 1
                except TelegramError as e:
                    logger.error(f"Failed to notify {recipient_id}: {e}")
                    
            logger.info(f"Appeal #{appeal_id} submitted by user {user.id}. Notified {successful_notifications}/{len(notification_recipients)} admins.")
            
            # Clean up user data
            del context.user_data['expecting_appeal_text']
            del context.user_data['appeal_type']
            if user.id in user_appeals:
                del user_appeals[user.id]
                
        except sqlite3.Error as e:
            logger.error(f"Database error in handle_appeal_text: {e}")
            update.message.reply_text("❌ Database error. Please try again later.")
        finally:
            conn.close()
            
    except TelegramError as e:
        logger.error(f"Telegram error in handle_appeal_text: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_appeal_text: {e}")

# --- Helper function for admin access ---
def is_admin_or_owner(user_id):
    """Check if user is admin or owner"""
    return user_id in ADMIN_IDS or (OWNER_ID and user_id == OWNER_ID)

# --- Admin Commands ---
def pending(update: Update, context: CallbackContext):
    """Show pending appeals (admin/owner only)"""
    try:
        if not is_admin_or_owner(update.effective_user.id):
            update.message.reply_text("❌ Access denied.")
            return
            
        conn = get_db_connection()
        if not conn:
            update.message.reply_text("❌ Database error. Please try again later.")
            return
            
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM appeals WHERE status='pending' ORDER BY id DESC")
            appeals = c.fetchall()
            
            if not appeals:
                update.message.reply_text("📋 No pending appeals!")
                return
            
            response = "📋 Pending Appeals:\n\n"
            for appeal in appeals:
                response += (
                    f"ID: #{appeal[0]}\n"
                    f"User: @{appeal[2]} (ID: {appeal[1]})\n"
                    f"Type: {appeal[3].capitalize()}\n"
                    f"Time: {appeal[6]}\n"
                    f"Status: {appeal[5]}\n"
                    f"Text: {appeal[4][:100]}...\n"
                    "───────────────\n"
                )
            
            # Split long messages if needed
            if len(response) > 4096:
                for i in range(0, len(response), 4096):
                    update.message.reply_text(response[i:i+4096])
            else:
                update.message.reply_text(response)
                
            logger.info(f"Admin {update.effective_user.id} viewed pending appeals")
            
        except sqlite3.Error as e:
            logger.error(f"Database error in pending: {e}")
            update.message.reply_text("❌ Database error. Please try again later.")
        finally:
            conn.close()
            
    except TelegramError as e:
        logger.error(f"Telegram error in pending: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in pending: {e}")

def view_appeal(update: Update, context: CallbackContext):
    """View full appeal details (admin/owner only)"""
    try:
        if not is_admin_or_owner(update.effective_user.id):
            update.message.reply_text("❌ Access denied.")
            return
            
        if not context.args:
            update.message.reply_text("❌ Usage: /view <appeal_id>")
            return
            
        try:
            appeal_id = int(context.args[0])
        except ValueError:
            update.message.reply_text("❌ Invalid appeal ID. Please provide a number.")
            return
            
        conn = get_db_connection()
        if not conn:
            update.message.reply_text("❌ Database error. Please try again later.")
            return
            
        try:
            c = conn.cursor()
            c.execute("SELECT * FROM appeals WHERE id=?", (appeal_id,))
            appeal = c.fetchone()
            
            if not appeal:
                update.message.reply_text(f"❌ Appeal #{appeal_id} not found.")
                return
                
            response = (
                f"📄 Appeal Details #{appeal[0]}\n"
                f"User: @{appeal[2]} (ID: {appeal[1]})\n"
                f"Type: {appeal[3].capitalize()}\n"
                f"Status: {appeal[5]}\n"
                f"Time: {appeal[6]}\n\n"
                f"📝 Appeal Text:\n{appeal[4]}\n\n"
                f"Use /approve {appeal[0]} to approve\n"
                f"Use /reject {appeal[0]} to reject"
            )
            
            update.message.reply_text(response)
            logger.info(f"Admin {update.effective_user.id} viewed appeal #{appeal_id}")
            
        except sqlite3.Error as e:
            logger.error(f"Database error in view_appeal: {e}")
            update.message.reply_text("❌ Database error. Please try again later.")
        finally:
            conn.close()
            
    except TelegramError as e:
        logger.error(f"Telegram error in view_appeal: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in view_appeal: {e}")

def approve(update: Update, context: CallbackContext):
    """Approve appeal (admin/owner only)"""
    try:
        if not is_admin_or_owner(update.effective_user.id):
            update.message.reply_text("❌ Access denied.")
            return
            
        if not context.args:
            update.message.reply_text("❌ Usage: /approve <appeal_id>")
            return
            
        try:
            appeal_id = int(context.args[0])
        except ValueError:
            update.message.reply_text("❌ Invalid appeal ID. Please provide a number.")
            return
            
        conn = get_db_connection()
        if not conn:
            update.message.reply_text("❌ Database error. Please try again later.")
            return
            
        try:
            c = conn.cursor()
            
            # Check if appeal exists
            c.execute("SELECT user_id, appeal_type, appeal_text FROM appeals WHERE id=? AND status='pending'", (appeal_id,))
            result = c.fetchone()
            
            if not result:
                update.message.reply_text(f"❌ Appeal #{appeal_id} not found or already processed.")
                return
                
            user_id, appeal_type, appeal_text = result
            
            # Update database
            c.execute("UPDATE appeals SET status='approved' WHERE id=?", (appeal_id,))
            conn.commit()
            
            update.message.reply_text(f"✅ Appeal #{appeal_id} approved successfully!")
            
            # Notify user
            try:
                context.bot.send_message(
                    user_id, 
                    f"🎉 Your {appeal_type} appeal has been approved!\n"
                    f"Appeal ID: #{appeal_id}\n\n"
                    f"Your appeal text:\n{appeal_text}"
                )
                logger.info(f"User {user_id} notified about approved appeal #{appeal_id}")
            except TelegramError as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
                update.message.reply_text(f"Appeal approved but failed to notify user.")
                
            logger.info(f"Appeal #{appeal_id} approved by admin {update.effective_user.id}")
            
        except sqlite3.Error as e:
            logger.error(f"Database error in approve: {e}")
            update.message.reply_text("❌ Database error. Please try again later.")
        finally:
            conn.close()
            
    except TelegramError as e:
        logger.error(f"Telegram error in approve: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in approve: {e}")

def reject(update: Update, context: CallbackContext):
    """Reject appeal (admin/owner only)"""
    try:
        if not is_admin_or_owner(update.effective_user.id):
            update.message.reply_text("❌ Access denied.")
            return
            
        if not context.args:
            update.message.reply_text("❌ Usage: /reject <appeal_id>")
            return
            
        try:
            appeal_id = int(context.args[0])
        except ValueError:
            update.message.reply_text("❌ Invalid appeal ID. Please provide a number.")
            return
            
        conn = get_db_connection()
        if not conn:
            update.message.reply_text("❌ Database error. Please try again later.")
            return
            
        try:
            c = conn.cursor()
            
            # Check if appeal exists
            c.execute("SELECT user_id, appeal_type, appeal_text FROM appeals WHERE id=? AND status='pending'", (appeal_id,))
            result = c.fetchone()
            
            if not result:
                update.message.reply_text(f"❌ Appeal #{appeal_id} not found or already processed.")
                return
                
            user_id, appeal_type, appeal_text = result
            
            # Update database
            c.execute("UPDATE appeals SET status='rejected' WHERE id=?", (appeal_id,))
            conn.commit()
            
            update.message.reply_text(f"❌ Appeal #{appeal_id} rejected.")
            
            # Notify user
            try:
                context.bot.send_message(
                    user_id, 
                    f"❌ Your {appeal_type} appeal has been rejected.\n"
                    f"Appeal ID: #{appeal_id}\n\n"
                    f"Your appeal text:\n{appeal_text}\n\n"
                    "You may submit a new appeal if you wish."
                )
                logger.info(f"User {user_id} notified about rejected appeal #{appeal_id}")
            except TelegramError as e:
                logger.error(f"Failed to notify user {user_id}: {e}")
                update.message.reply_text(f"Appeal rejected but failed to notify user.")
                
            logger.info(f"Appeal #{appeal_id} rejected by admin {update.effective_user.id}")
            
        except sqlite3.Error as e:
            logger.error(f"Database error in reject: {e}")
            update.message.reply_text("❌ Database error. Please try again later.")
        finally:
            conn.close()
            
    except TelegramError as e:
        logger.error(f"Telegram error in reject: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in reject: {e}")

def stats(update: Update, context: CallbackContext):
    """Show appeal statistics (admin/owner only)"""
    try:
        if not is_admin_or_owner(update.effective_user.id):
            update.message.reply_text("❌ Access denied.")
            return
            
        conn = get_db_connection()
        if not conn:
            update.message.reply_text("❌ Database error. Please try again later.")
            return
            
        try:
            c = conn.cursor()
            
            # Get basic stats
            c.execute("SELECT COUNT(*) FROM appeals")
            total = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM appeals WHERE status='pending'")
            pending = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM appeals WHERE status='approved'")
            approved = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM appeals WHERE status='rejected'")
            rejected = c.fetchone()[0]
            
            # Get appeal type distribution
            c.execute("SELECT appeal_type, COUNT(*) FROM appeals GROUP BY appeal_type")
            type_stats = "\n".join([f"• {row[0].capitalize()}: {row[1]}" for row in c.fetchall()])
            
            # Get recent activity
            c.execute("SELECT COUNT(*) FROM appeals WHERE created_at >= datetime('now', '-1 day')")
            last_24h = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM appeals WHERE created_at >= datetime('now', '-7 days')")
            last_7d = c.fetchone()[0]
            
            response = (
                "📊 <b>Appeal Statistics</b>\n\n"
                f"<b>Total Appeals:</b> {total}\n"
                f"<b>Pending:</b> {pending}\n"
                f"<b>Approved:</b> {approved}\n"
                f"<b>Rejected:</b> {rejected}\n\n"
                f"<b>Recent Activity:</b>\n"
                f"• Last 24h: {last_24h}\n"
                f"• Last 7 days: {last_7d}\n\n"
                f"<b>By Appeal Type:</b>\n"
                f"{type_stats}\n\n"
                f"<b>System Info:</b>\n"
                f"• Active Admins: {len(ADMIN_IDS)}\n"
                f"• Owner ID: {OWNER_ID if OWNER_ID else 'Not set'}\n\n"
                "Use /pending to view pending appeals"
            )
            
            update.message.reply_text(response, parse_mode=ParseMode.HTML)
            logger.info(f"Admin {update.effective_user.id} viewed statistics")
            
        except sqlite3.Error as e:
            logger.error(f"Database error in stats: {e}")
            update.message.reply_text("❌ Database error. Please try again later.")
        finally:
            conn.close()
            
    except TelegramError as e:
        logger.error(f"Telegram error in stats: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in stats: {e}")

def error_handler(update: Update, context: CallbackContext):
    """Global error handler"""
    logger.error(f"Update {update} caused error {context.error}")

# --- Bot Setup ---
def main():
    """Main function to run the bot"""
    try:
        # Initialize database
        init_db()
        
        # Create updater
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        
        # User commands
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("appeal", appeal))
        
        # Admin commands
        dp.add_handler(CommandHandler("pending", pending))
        dp.add_handler(CommandHandler("view", view_appeal))
        dp.add_handler(CommandHandler("approve", approve))
        dp.add_handler(CommandHandler("reject", reject))
        dp.add_handler(CommandHandler("stats", stats))
        dp.add_handler(CommandHandler("admins", list_admins))
        
        # Owner commands
        dp.add_handler(CommandHandler("addadmin", add_admin))
        dp.add_handler(CommandHandler("removeadmin", remove_admin))
        
        # System commands
        dp.add_handler(CommandHandler("ping", ping_uptime.ping_command))
        dp.add_handler(CommandHandler("status", status_handler))
        
        # Shell commands (Owner only)
        dp.add_handler(CommandHandler(["shell", "sh"], shell_command))
        
        # Callbacks
        dp.add_handler(CallbackQueryHandler(handle_appeal_type))
        
        # Text handler for appeal submission
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_appeal_text))
        
        # Error handler
        dp.add_error_handler(error_handler)
        
        logger.info("Bot started successfully")
        logger.info(f"Configured with {len(ADMIN_IDS)} admin(s) and owner: {OWNER_ID}")
        print("Bot is running...")
        
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
