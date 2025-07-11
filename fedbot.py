import logging
import os
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from telegram.error import TelegramError
from dotenv import load_dotenv
import sys

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
    ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
    DB_PATH = os.getenv('DB_PATH', 'appeals.db')
    
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is required")
    if not ADMIN_ID:
        raise ValueError("ADMIN_ID environment variable is required")
        
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

def handle_appeal(update: Update, context: CallbackContext):
    """Handle appeal callback"""
    try:
        query = update.callback_query
        query.answer()
        user = query.from_user
        
        # Validate appeal type
        if query.data not in ['unban', 'admin']:
            query.edit_message_text("❌ Invalid appeal type")
            return
            
        # Save to database
        conn = get_db_connection()
        if not conn:
            query.edit_message_text("❌ Database error. Please try again later.")
            return
            
        try:
            c = conn.cursor()
            c.execute('''INSERT INTO appeals 
                        (user_id, username, appeal_type, timestamp)
                        VALUES (?, ?, ?, ?)''',
                     (user.id, user.username or 'No username', query.data, 
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            appeal_id = c.lastrowid
            
            query.edit_message_text(
                f"✅ {query.data.capitalize()} appeal submitted successfully!\n"
                f"Appeal ID: #{appeal_id}\n\n"
                "Your appeal will be reviewed by an admin."
            )
            
            # Notify admin
            try:
                context.bot.send_message(
                    ADMIN_ID,
                    f"🚨 New Appeal #{appeal_id}\n"
                    f"User: @{user.username or 'No username'} (ID: {user.id})\n"
                    f"Type: {query.data.capitalize()}\n"
                    f"Time: {datetime.now().strftime('%H:%M %d-%m-%Y')}\n\n"
                    f"Use /pending to view all appeals\n"
                    f"Use /approve {appeal_id} to approve"
                )
                logger.info(f"Admin notified about appeal #{appeal_id}")
            except TelegramError as e:
                logger.error(f"Failed to notify admin: {e}")
                
            logger.info(f"Appeal #{appeal_id} submitted by user {user.id}")
            
        except sqlite3.Error as e:
            logger.error(f"Database error in handle_appeal: {e}")
            query.edit_message_text("❌ Database error. Please try again later.")
        finally:
            conn.close()
            
    except TelegramError as e:
        logger.error(f"Telegram error in handle_appeal: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in handle_appeal: {e}")

# --- Admin Commands ---
def pending(update: Update, context: CallbackContext):
    """Show pending appeals (admin only)"""
    try:
        if update.effective_user.id != ADMIN_ID:
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
                    f"Time: {appeal[5]}\n"
                    f"Status: {appeal[4]}\n"
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

def approve(update: Update, context: CallbackContext):
    """Approve appeal (admin only)"""
    try:
        if update.effective_user.id != ADMIN_ID:
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
            c.execute("SELECT user_id, appeal_type FROM appeals WHERE id=? AND status='pending'", (appeal_id,))
            result = c.fetchone()
            
            if not result:
                update.message.reply_text(f"❌ Appeal #{appeal_id} not found or already processed.")
                return
                
            user_id, appeal_type = result
            
            # Update database
            c.execute("UPDATE appeals SET status='approved' WHERE id=?", (appeal_id,))
            conn.commit()
            
            update.message.reply_text(f"✅ Appeal #{appeal_id} approved successfully!")
            
            # Notify user
            try:
                context.bot.send_message(
                    user_id, 
                    f"🎉 Your {appeal_type} appeal has been approved!\n"
                    f"Appeal ID: #{appeal_id}"
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
    """Reject appeal (admin only)"""
    try:
        if update.effective_user.id != ADMIN_ID:
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
            c.execute("SELECT user_id, appeal_type FROM appeals WHERE id=? AND status='pending'", (appeal_id,))
            result = c.fetchone()
            
            if not result:
                update.message.reply_text(f"❌ Appeal #{appeal_id} not found or already processed.")
                return
                
            user_id, appeal_type = result
            
            # Update database
            c.execute("UPDATE appeals SET status='rejected' WHERE id=?", (appeal_id,))
            conn.commit()
            
            update.message.reply_text(f"❌ Appeal #{appeal_id} rejected.")
            
            # Notify user
            try:
                context.bot.send_message(
                    user_id, 
                    f"❌ Your {appeal_type} appeal has been rejected.\n"
                    f"Appeal ID: #{appeal_id}"
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
        dp.add_handler(CommandHandler("approve", approve))
        dp.add_handler(CommandHandler("reject", reject))
        
        # Callbacks
        dp.add_handler(CallbackQueryHandler(handle_appeal))
        
        # Error handler
        dp.add_error_handler(error_handler)
        
        logger.info("Bot started successfully")
        print("Bot is running...")
        
        updater.start_polling()
        updater.idle()
        
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()