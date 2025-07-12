# ⚡️ HyperFederation Appeals Bot

![photo_2025-07-11_20-46-48](https://github.com/user-attachments/assets/b38e40d0-98a8-4a51-8aa7-272e2bd1a591)

[![Open Source Love](https://badges.frapsoft.com/os/v2/open-source.png?v=103)](https://github.com/real-ekansh/Fedbot)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-Yes-green)](https://github.com/real-ekansh/Fedbot/graphs/commit-activity)
[![GitHub Forks](https://img.shields.io/github/forks/real-ekansh/Fedbot?&logo=github)](https://github.com/real-ekansh/Fedbot)
[![GitHub Stars](https://img.shields.io/github/stars/real-ekansh/Fedbot?&logo=github)](https://github.com/real-ekansh/Fedbot/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/real-ekansh/Fedbot?&logo=github)](https://github.com/real-ekansh/Fedbot)
[![Contributors](https://img.shields.io/github/contributors/real-ekansh/Fedbot?color=green)](https://github.com/real-ekansh/Fedbot/graphs/contributors)
[![License](https://img.shields.io/badge/License-GPL-pink)](https://github.com/real-ekansh/Fedbot/blob/main/LICENSE)

A comprehensive Telegram bot designed to handle FedBan appeals and Fed Admin requests with an intuitive user interface and robust admin management system.

## 📋 Features

- **Dual Appeal Types**: Support for FedBan unban appeals and Fed Admin requests
- **Interactive Interface**: User-friendly inline keyboards for seamless navigation
- **Database Management**: SQLite database for persistent appeal storage
- **Admin Notifications**: Real-time notifications to administrators
- **Status Tracking**: Comprehensive appeal status management
- **Error Handling**: Robust error handling and logging
- **Template Guidance**: Built-in templates to help users write effective appeals

## 🚀 Installation

### Prerequisites

- Python 3.7+
- pip package manager

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/real-ekansh/Fedbot
cd Fedbot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Create environment file snd Activate it** 
```bash
python -m venv venv 
source venv/bin/activate
```

4. **Configure environment variables** (see Configuration section)

5. **Run the bot**
```bash
python fedbot.py
```

## ⚙️ Configuration

Create a `.env` file in the project root with the following variables:

```env
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_ID=your_telegram_admin_user_id
DB_PATH=appeals.db (defualt path)
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `BOT_TOKEN` | Telegram Bot API token from @BotFather | ✅ |
| `ADMIN_ID` | Telegram user ID of the administrator | ✅ |
| `DB_PATH` | Path to SQLite database file | ❌ (default: appeals.db) |

## 📊 Database Schema

The bot uses SQLite with the following table structure:

```sql
CREATE TABLE appeals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    appeal_type TEXT NOT NULL,
    appeal_text TEXT,
    status TEXT DEFAULT "pending",
    timestamp TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 🤖 Bot Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot introduction |
| `/appeal` | Start the appeal process with type selection |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/pending` | View all pending appeals |
| `/approve <appeal_id>` | Approve a specific appeal |
| `/reject <appeal_id>` | Reject a specific appeal |

## 📱 Usage

### For Users

1. **Start the bot**: Send `/start` to receive a welcome message
2. **Submit an appeal**: Send `/appeal` and select your appeal type:
   - **🔓 Fed Unban Appeal**: For requesting removal of FedBan
   - **👑 Fed Admin Request**: For requesting Fed Admin status
3. **Write your appeal**: Follow the provided template and guidelines
4. **Wait for review**: Your appeal will be reviewed by an administrator

### Appeal Templates

#### FedBan Unban Appeal
```
1. Why were you banned?
2. What have you learned from this experience?
3. Why should we unban you?
4. Any additional information?
```

#### Fed Admin Request
```
1. Why do you want to be an admin?
2. What experience do you have?
3. How will you help the community?
4. Any additional information?
```

### For Administrators

1. **Monitor appeals**: Receive real-time notifications for new appeals
2. **Review pending appeals**: Use `/pending` to see all pending appeals
3. **Process appeals**: Use `/approve <id>` or `/reject <id>` to process appeals

## 🔧 Technical Details

### Dependencies

```
python-telegram-bot>=13.0
python-dotenv>=0.19.0
```

### File Structure

```
telegram-appeals-bot/
├── bot.py              # Main bot application
├── appeals.db          # SQLite database (auto-created)
├── .env               # Environment variables
├── .env.example       # Environment template
├── requirements.txt   # Python dependencies
└── README.md         # This file
```

### Logging

The bot implements comprehensive logging with the following levels:
- **INFO**: General operational information
- **ERROR**: Error conditions and exceptions
- **WARNING**: Warning conditions

Logs include timestamps, logger names, and detailed error messages for debugging.

### Error Handling

- **Configuration Validation**: Validates required environment variables on startup
- **Database Error Handling**: Graceful handling of SQLite connection issues
- **Telegram API Errors**: Proper handling of Telegram API exceptions
- **User Input Validation**: Validates user inputs and appeal types

## 🛡️ Security Features

- **Admin Access Control**: Restricted admin commands to authorized users only
- **Input Sanitization**: Proper handling of user inputs
- **Error Isolation**: Prevents error propagation that could crash the bot
- **Database Security**: Safe database operations with parameterized queries

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🐛 Bug Reports

If you encounter any bugs or issues, please report them through the GitHub issues page with:
- Detailed description of the issue
- Steps to reproduce
- Expected vs actual behavior
- Log messages (if applicable)

## 📞 Support

For support and questions:
- Create an issue on GitHub
- Check the documentation
- Review the logs for error messages
- Contact on Telegram
- [Discussion](https://t.me/hypertechot) in the official telegram chat \[en\]

## 👨🏻‍💼 Credits
* [not_real_ekansh](https://github.com/real-ekansh)
* [Tech Shreyansh](https://github.com/techyshreyansh)
---

If you liked my Work please give my Project a Star ⭐ 
**Made with ❤️ for the Telegram community**
