# 🌐 Socials-Bot: Your Cross-Platform Publishing Assistant

A Telegram bot [@pyworldwide_socials_bot](https://t.me/pyworldwide_socials_bot) that publishes your posts on Bluesky and Fosstodon with just a few taps! 📱✨

## 📋 Prerequisites

- Python 3.11+ installed
- [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager
- A Telegram bot token (obtained from [@BotFather](https://t.me/botfather))
- Bluesky account credentials
- A Fosstodon (Mastodon) access token

## 🚀 Installation

1. Clone the project:
   ```bash
   git clone https://github.com/pyworldwide/socials-bot.git
   cd socials-bot
   ```

2. Install the dependencies:
   ```bash
   uv sync --frozen
   ```

## ⚙️ Configuration

1. Create a `.env` file with your credentials:
   ```
   TELEGRAM_TOKEN=your_telegram_bot_token
   BLUESKY_USERNAME=your_bluesky_username
   BLUESKY_PASSWORD=your_bluesky_password
   MASTODON_ACCESS_TOKEN=your_mastodon_access_token
   AUTHORIZED_USERS=[123456789, 987654321]
   ```
   Replace the values with your actual credentials. For `AUTHORIZED_USERS`, include the Telegram user IDs of people who should be allowed to use the bot (as a JSON array).

2. To get your Telegram user ID, you can talk to [@userinfobot](https://t.me/userinfobot) on Telegram.

3. For the Mastodon access token, follow these steps:
   - Log in to your Fosstodon account
   - Go to Preferences > Development > New Application
   - Name your application, give it the `write:statuses` scope
   - Submit and copy the access token

## 🏃‍♂️ Running the Bot

### 🐳 Via Docker
1. Build the docker image:
   ```bash
   docker build -t socials-bot .
   ```
2. Run the bot:
   ```bash
   docker run --env-file ./.env socials-bot
   ```
3. To run in background (detached mode):
   ```bash
   docker run -d --env-file ./.env --name socials-bot socials-bot
   ```
4. View logs if running in detached mode:
   ```bash
   docker logs -f socials-bot
   ```

### 💻 Without Docker
1. Run the bot:
   ```bash
   uv run python3 main.py
   ```

## 🤖 Bot Usage

Once your bot is running, you can interact with it via Telegram:

- `/start` - Shows welcome message and instructions 👋
- `/help` - To see the available commands 📚
- `/post` - Start the posting process ✏️
- `/list_scheduled` - List all your scheduled posts 📅
- `/delete_scheduled [post_id]` - Delete a scheduled post 🗑️
- `/cancel` - Cancel the current operation ❌

## 🔧 Troubleshooting

If you encounter issues:

1. Check your credentials in the `.env` file 🔑
2. Ensure your bot has the necessary permissions on Telegram 👮‍♀️
3. Verify your Bluesky and Mastodon credentials are correct 🔐
4. Check the logs for any error messages 📊

For persistent storage of scheduled posts, the bot creates a `scheduled_posts.json` file. Make sure the directory is writable. 💾

## 🤝 Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

## 📝 License

This project is licensed under the [CC0 1.0 Universal](./LICENSE) - see the LICENSE file for details.

---

**Happy cross-posting!** 🎉