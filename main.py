import logging
import os
import sqlite3
import subprocess
import html
import io
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    ParseMode,
)
from telegram.error import TelegramError
from dotenv import load_dotenv
import sys

from bot_status import async_status_handler
from ping_module import ping_command

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- CONFIG ---
try:
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    ADMIN_IDS_FROM_ENV = []
    admin_ids_str = os.getenv('ADMIN_IDS', '')
    if admin_ids_str:
        ADMIN_IDS_FROM_ENV = [int(id.strip()) for id in admin_ids_str.split(',') if id.strip().isdigit()]
    
    legacy_admin_id = os.getenv('ADMIN_ID', '')
    if legacy_admin_id and legacy_admin_id.isdigit():
        legacy_admin_id = int(legacy_admin_id)
        if legacy_admin_id not in ADMIN_IDS_FROM_ENV:
            ADMIN_IDS_FROM_ENV.append(legacy_admin_id)
    
    OWNER_ID = int(os.getenv('OWNER_ID', 0))
    DB_PATH = os.getenv('DB_PATH', 'appeals.db')
    
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is required")
    if not OWNER_ID:
        logger.warning("OWNER_ID not set, shell commands and admin management will be disabled.")
        
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    sys.exit(1)
except Exception as e:
    logger.error(f"Unexpected configuration error: {e}")
    sys.exit(1)

# --- Database Setup ---
def init_db():
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
        
        c.execute('''CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY NOT NULL,
                      added_by INTEGER,
                      added_at DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        c.execute("SELECT COUNT(*) FROM admins")
        if c.fetchone()[0] == 0 and ADMIN_IDS_FROM_ENV:
            logger.info("Admin table is empty. Seeding with admins from .env file...")
            for admin_id in ADMIN_IDS_FROM_ENV:
                c.execute("INSERT OR IGNORE INTO admins (user_id, added_by) VALUES (?, ?)", (admin_id, OWNER_ID or 0))
            logger.info(f"Seeded {len(ADMIN_IDS_FROM_ENV)} admin(s) into the database.")

        conn.commit()
        logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

def get_db_connection():
    try:
        conn = sqlite3.connect(DB_PATH)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        return None

# --- Helper function for admin access ---
def is_admin_or_owner(user_id: int) -> bool:
    if OWNER_ID and user_id == OWNER_ID:
        return True
    
    conn = get_db_connection()
    if not conn:
        return False
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,))
        return c.fetchone() is not None
    except sqlite3.Error as e:
        logger.error(f"DB error in is_admin_or_owner check: {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- States for Conversation Handler ---
SELECTING_TYPE, TYPING_APPEAL = range(2)

# --- User Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.reply_text(
            "📝 Welcome to the Appeals Bot!\n\n"
            "Use /appeal to submit a FedBan appeal or request Fed Admin status"
        )
        logger.info(f"User {update.effective_user.id} started the bot")
    except TelegramError as e:
        logger.error(f"Error in start command: {e}")

async def appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        keyboard = [
            [InlineKeyboardButton("🔓 Fed Unban Appeal", callback_data="unban")],
            [InlineKeyboardButton("👑 Fed Admin Request", callback_data="admin")]
        ]
        await update.message.reply_text(
            "Select appeal type:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        logger.info(f"User {update.effective_user.id} initiated appeal process")
        return SELECTING_TYPE
    except TelegramError as e:
        logger.error(f"Error in appeal command: {e}")
        await update.message.reply_text("❌ An error occurred. Please try again later.")
        return ConversationHandler.END

async def handle_appeal_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    appeal_type_choice = query.data

    if appeal_type_choice not in ['unban', 'admin']:
        await query.edit_message_text("❌ Invalid appeal type")
        return ConversationHandler.END
    
    context.user_data['appeal_type'] = appeal_type_choice
    appeal_type_text = "unban" if appeal_type_choice == "unban" else "admin request"
    
    template = ""
    if appeal_type_choice == "unban":
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
        
    await query.edit_message_text(
        f"✍️ Please write and submit your {appeal_type_text} appeal.{template}\n\n"
        "Type your appeal now:"
    )
    
    logger.info(f"User {user.id} selected {appeal_type_choice} appeal type")
    return TYPING_APPEAL

async def handle_appeal_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    appeal_text = update.message.text
    appeal_type = context.user_data.get('appeal_type')

    if not appeal_type:
        return ConversationHandler.END
        
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database error. Please try again later.")
        return ConversationHandler.END
        
    try:
        c = conn.cursor()
        c.execute('''INSERT INTO appeals 
                    (user_id, username, appeal_type, appeal_text, timestamp)
                    VALUES (?, ?, ?, ?, ?)''',
                 (user.id, user.username or 'No username', appeal_type, appeal_text,
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        appeal_id = c.lastrowid
        
        await update.message.reply_text(
            f"✅ {appeal_type.capitalize()} appeal submitted successfully!\n"
            f"Appeal ID: #{appeal_id}\n\n"
            "Your appeal will be reviewed by an admin."
        )
        
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
        
        c.execute("SELECT user_id FROM admins")
        db_admin_ids = {row[0] for row in c.fetchall()}
        if OWNER_ID:
            db_admin_ids.add(OWNER_ID)
        
        successful_notifications = 0
        for recipient_id in db_admin_ids:
            try:
                await context.bot.send_message(recipient_id, notification_message)
                successful_notifications += 1
            except TelegramError as e:
                logger.error(f"Failed to notify {recipient_id}: {e}")
                
        logger.info(f"Appeal #{appeal_id} submitted. Notified {successful_notifications}/{len(db_admin_ids)} admins.")
        
    except sqlite3.Error as e:
        logger.error(f"Database error in handle_appeal_text: {e}")
        await update.message.reply_text("❌ Database error. Please try again later.")
    finally:
        conn.close()
        
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Appeal submission cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

# --- Admin Management Commands ---
async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not OWNER_ID or update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access denied. Only the bot owner can use this command.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /addadmin <user_id>")
        return
    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a valid number.")
        return

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database error. Please try again later.")
        return

    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM admins WHERE user_id = ?", (new_admin_id,))
        if c.fetchone():
            await update.message.reply_text(f"❌ User {new_admin_id} is already an admin.")
            return

        c.execute("INSERT INTO admins (user_id, added_by) VALUES (?, ?)", (new_admin_id, update.effective_user.id))
        conn.commit()

        await update.message.reply_text(f"✅ User {new_admin_id} has been added as an admin.")
        logger.info(f"Owner {update.effective_user.id} added {new_admin_id} as admin to the database")
        
        try:
            await context.bot.send_message(
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
            await update.message.reply_text(f"Admin added but failed to notify them.")
    
    except sqlite3.Error as e:
        logger.error(f"Database error in add_admin: {e}")
        await update.message.reply_text("❌ Database error while adding admin.")
    finally:
        if conn:
            conn.close()

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not OWNER_ID or update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access denied. Only the bot owner can use this command.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /removeadmin <user_id>")
        return
    try:
        admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID. Please provide a valid number.")
        return
        
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database error. Please try again later.")
        return

    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM admins WHERE user_id = ?", (admin_id,))
        if not c.fetchone():
            await update.message.reply_text(f"❌ User {admin_id} is not an admin.")
            return

        c.execute("DELETE FROM admins WHERE user_id = ?", (admin_id,))
        conn.commit()
        
        await update.message.reply_text(f"✅ User {admin_id} has been removed from admin list.")
        logger.info(f"Owner {update.effective_user.id} removed {admin_id} from admin list")
        
        try:
            await context.bot.send_message(
                admin_id,
                "🚫 Your admin access to the Appeals Bot has been revoked."
            )
        except TelegramError as e:
            logger.error(f"Failed to notify removed admin {admin_id}: {e}")
            
    except sqlite3.Error as e:
        logger.error(f"Database error in remove_admin: {e}")
        await update.message.reply_text("❌ Database error while removing admin.")
    finally:
        if conn:
            conn.close()

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
        
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database error. Please try again later.")
        return

    try:
        c = conn.cursor()
        c.execute("SELECT user_id FROM admins ORDER BY user_id")
        db_admins = [row[0] for row in c.fetchall()]
        
        admin_list = "\n".join([f"• {admin_id}" for admin_id in db_admins]) if db_admins else "No admins found."
        owner_info = f"\n👑 Owner: {OWNER_ID}" if OWNER_ID else ""
        
        total_authorized = len(set(db_admins + ([OWNER_ID] if OWNER_ID else [])))
        
        response = (
            f"👥 <b>Admin List ({len(db_admins)} admins)</b>\n\n"
            f"{admin_list}"
            f"{owner_info}\n\n"
            f"Total authorized users: {total_authorized}"
        )
        
        await update.message.reply_text(response, parse_mode=ParseMode.HTML)
    except sqlite3.Error as e:
        logger.error(f"Database error in list_admins: {e}")
        await update.message.reply_text("❌ Database error. Please try again later.")
    finally:
        if conn:
            conn.close()

# --- Shell Command Support ---
async def shell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not OWNER_ID or update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Access denied. Only the bot owner can use this command.")
        return
        
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: /shell <command>\n"
            "Example: /shell ls -la\n"
            "⚠️ Use with caution - this executes system commands!"
        )
        return
        
    command = ' '.join(context.args)
    logger.info(f"Owner {update.effective_user.id} executing shell command: {command}")
    
    try:
        # Run the blocking subprocess call in a separate thread
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        
        output = ""
        if stdout:
            output += f"📤 <b>STDOUT:</b>\n<pre>{html.escape(stdout.decode().strip())}</pre>\n"
        if stderr:
            output += f"🚨 <b>STDERR:</b>\n<pre>{html.escape(stderr.decode().strip())}</pre>\n"
            
        output += f"\n📊 <b>Return code:</b> {proc.returncode}"
        output += f"\n🕐 <b>Command:</b> <code>{html.escape(command)}</code>"
        
        if len(output) > 4000:
            output_file = io.BytesIO(
                f"Command: {command}\n"
                f"Return code: {proc.returncode}\n\n"
                f"STDOUT:\n{stdout.decode()}\n\n"
                f"STDERR:\n{stderr.decode()}".encode()
            )
            output_file.name = f"shell_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            
            await update.message.reply_document(
                document=output_file,
                caption=f"📁 Output too long, sent as file\n"
                       f"Command: <code>{html.escape(command)}</code>\n"
                       f"Return code: {proc.returncode}",
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(output or "Command executed with no output.", parse_mode=ParseMode.HTML)
            
    except asyncio.TimeoutError:
        await update.message.reply_text(
            f"⏰ <b>Command timed out after 30 seconds</b>\n"
            f"Command: <code>{html.escape(command)}</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>Execution error:</b>\n<pre>{html.escape(str(e))}</pre>\n"
            f"Command: <code>{html.escape(command)}</code>",
            parse_mode=ParseMode.HTML
        )

# --- Admin Commands ---
async def pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database error. Please try again later.")
        return
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM appeals WHERE status='pending' ORDER BY id DESC")
        appeals = c.fetchall()
        
        if not appeals:
            await update.message.reply_text("📋 No pending appeals!")
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
        
        if len(response) > 4096:
            for i in range(0, len(response), 4096):
                await update.message.reply_text(response[i:i+4096])
        else:
            await update.message.reply_text(response)
    except sqlite3.Error as e:
        logger.error(f"Database error in pending: {e}")
    finally:
        conn.close()

async def view_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /view <appeal_id>")
        return
    try:
        appeal_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid appeal ID. Please provide a number.")
        return

    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database error. Please try again later.")
        return
        
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM appeals WHERE id=?", (appeal_id,))
        appeal = c.fetchone()
        
        if not appeal:
            await update.message.reply_text(f"❌ Appeal #{appeal_id} not found.")
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
        
        await update.message.reply_text(response)
    except sqlite3.Error as e:
        logger.error(f"Database error in view_appeal: {e}")
    finally:
        conn.close()

async def process_appeal(update: Update, context: ContextTypes.DEFAULT_TYPE, new_status: str):
    if not is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
    
    command = "approve" if new_status == "approved" else "reject"
    if not context.args:
        await update.message.reply_text(f"❌ Usage: /{command} <appeal_id>")
        return
    try:
        appeal_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid appeal ID. Please provide a number.")
        return
        
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database error. Please try again later.")
        return

    try:
        c = conn.cursor()
        c.execute("SELECT user_id, appeal_type, appeal_text FROM appeals WHERE id=? AND status='pending'", (appeal_id,))
        result = c.fetchone()
        
        if not result:
            await update.message.reply_text(f"❌ Appeal #{appeal_id} not found or already processed.")
            return
            
        user_id, appeal_type, appeal_text = result
        c.execute("UPDATE appeals SET status=? WHERE id=?", (new_status, appeal_id))
        conn.commit()
        
        if new_status == "approved":
            await update.message.reply_text(f"✅ Appeal #{appeal_id} approved successfully!")
            notification_text = f"🎉 Your {appeal_type} appeal has been approved!\nAppeal ID: #{appeal_id}\n\nYour appeal text:\n{appeal_text}"
        else: # rejected
            await update.message.reply_text(f"❌ Appeal #{appeal_id} rejected.")
            notification_text = f"❌ Your {appeal_type} appeal has been rejected.\nAppeal ID: #{appeal_id}\n\nYour appeal text:\n{appeal_text}\n\nYou may submit a new appeal if you wish."
        
        try:
            await context.bot.send_message(user_id, notification_text)
            logger.info(f"User {user_id} notified about {new_status} appeal #{appeal_id}")
        except TelegramError as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
            await update.message.reply_text(f"Appeal {new_status} but failed to notify user.")
            
        logger.info(f"Appeal #{appeal_id} {new_status} by admin {update.effective_user.id}")
        
    except sqlite3.Error as e:
        logger.error(f"Database error in {command}: {e}")
    finally:
        conn.close()

async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_appeal(update, context, "approved")

async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_appeal(update, context, "rejected")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin_or_owner(update.effective_user.id):
        await update.message.reply_text("❌ Access denied.")
        return
        
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Database error. Please try again later.")
        return
        
    try:
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM appeals")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM appeals WHERE status='pending'")
        pending_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM appeals WHERE status='approved'")
        approved = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM appeals WHERE status='rejected'")
        rejected = c.fetchone()[0]
        c.execute("SELECT appeal_type, COUNT(*) FROM appeals GROUP BY appeal_type")
        type_stats = "\n".join([f"• {row[0].capitalize()}: {row[1]}" for row in c.fetchall()])
        c.execute("SELECT COUNT(*) FROM appeals WHERE created_at >= datetime('now', '-1 day')")
        last_24h = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM appeals WHERE created_at >= datetime('now', '-7 days')")
        last_7d = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM admins")
        active_admins = c.fetchone()[0]
        
        response = (
            "📊 <b>Appeal Statistics</b>\n\n"
            f"<b>Total Appeals:</b> {total}\n"
            f"<b>Pending:</b> {pending_count}\n"
            f"<b>Approved:</b> {approved}\n"
            f"<b>Rejected:</b> {rejected}\n\n"
            f"<b>Recent Activity:</b>\n"
            f"• Last 24h: {last_24h}\n"
            f"• Last 7 days: {last_7d}\n\n"
            f"<b>By Appeal Type:</b>\n"
            f"{type_stats}\n\n"
            f"<b>System Info:</b>\n"
            f"• Active Admins: {active_admins}\n"
            f"• Owner ID: {OWNER_ID if OWNER_ID else 'Not set'}\n\n"
            "Use /pending to view pending appeals"
        )
        
        await update.message.reply_text(response, parse_mode=ParseMode.HTML)
    except sqlite3.Error as e:
        logger.error(f"Database error in stats: {e}")
    finally:
        conn.close()

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception while handling an update:", exc_info=context.error)

async def main():
    init_db()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Conversation handler for the appeal process
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("appeal", appeal)],
        states={
            SELECTING_TYPE: [CallbackQueryHandler(handle_appeal_type)],
            TYPING_APPEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_appeal_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    
    # User commands
    application.add_handler(CommandHandler("start", start))
    
    # Admin commands
    application.add_handler(CommandHandler("pending", pending))
    application.add_handler(CommandHandler("view", view_appeal))
    application.add_handler(CommandHandler("approve", approve))
    application.add_handler(CommandHandler("reject", reject))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("admins", list_admins))
    
    # Owner commands
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CommandHandler("removeadmin", remove_admin))
    
    # System commands
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("status", async_status_handler))
    
    # Shell commands (Owner only)
    application.add_handler(CommandHandler(["shell", "sh"], shell_command))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM admins")
    num_admins = c.fetchone()[0]
    conn.close()
    
    logger.info("Bot started successfully")
    logger.info(f"Loaded with {num_admins} admin(s) from DB and owner: {OWNER_ID}")
    print("Bot is running...")
    
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
