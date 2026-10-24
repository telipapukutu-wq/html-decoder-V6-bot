# HTML Decoder Telegram Bot

A Telegram bot that accepts `.html`, `.htm`, or `.txt` files and decodes common text-encoding layers without executing JavaScript.

## 1. Create a Telegram bot
- Open Telegram and message `@BotFather`.
- Run `/newbot`, follow the prompts, and copy the bot token.
- Keep the token private. Never commit it to GitHub.

## 2. Upload this project to GitHub
Create a new repository and upload these files:
- `bot.py`
- `requirements.txt`
- `Procfile`
- `railway.json`
- `.gitignore`

## 3. Deploy on Railway
- Sign in to Railway and choose **New Project → Deploy from GitHub Repo**.
- Select this repository.
- In the service's **Variables** section, add:
  - `TELEGRAM_BOT_TOKEN` = your token from BotFather
- Deploy. The start command is configured as `python bot.py`.

## 4. Use it
Open your Telegram bot and send `/start`, then upload a `.html`, `.htm`, or `.txt` file.

## Notes
- Input limit: 15 MB.
- Supports HTML entities, URL percent encoding, whole-file Base64/hex, common JavaScript `\\xNN` and `\\uNNNN` escapes, and a limited embedded Base64 pattern.
- It does not run JavaScript and cannot decode every custom packer, encryption scheme, or server-side code.
- Decoded HTML may still contain harmful scripts. Review it and avoid opening untrusted output in your normal browser.
