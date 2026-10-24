import os
import re
import base64
import binascii
import html
import logging
from pathlib import Path
from urllib.parse import unquote

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

MAX_INPUT_BYTES = 15 * 1024 * 1024  # 15 MB safety limit
MAX_PASSES = 8


def decode_js_escapes(text: str) -> str:
    text = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)
    def braced(m):
        value = int(m.group(1), 16)
        return chr(value) if value <= 0x10FFFF else m.group(0)
    return re.sub(r"\\u\{([0-9a-fA-F]{1,6})\}", braced, text)


def printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    return sum(ch.isprintable() or ch in "\r\n\t" for ch in text) / len(text)


def decode_whole_base64(text: str):
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 8 or not re.fullmatch(r"[A-Za-z0-9+/]*={0,2}", compact):
        return None
    if len(compact) % 4 == 1:
        return None
    padded = compact + "=" * ((4 - len(compact) % 4) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    return decoded if printable_ratio(decoded) >= 0.85 else None


def decode_whole_hex(text: str):
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 8 or len(compact) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", compact):
        return None
    try:
        decoded = bytes.fromhex(compact).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return decoded if printable_ratio(decoded) >= 0.85 else None


def decode_embedded_base64(text: str) -> str:
    pattern = re.compile(r"""(['"])([A-Za-z0-9+/]{24,}={0,2})\1""")
    def replace(match):
        decoded = decode_whole_base64(match.group(2))
        if decoded is None:
            return match.group(0)
        if any(token in decoded.lower() for token in (
            "<html", "<!doctype", "<script", "<div", "function", "document."
        )):
            quote = match.group(1)
            escaped = decoded.replace("\\", "\\\\").replace(quote, "\\" + quote)
            return quote + escaped + quote
        return match.group(0)
    return pattern.sub(replace, text)


def decode_one_pass(text: str):
    changes = []
    updated = html.unescape(text)
    if updated != text:
        text, changes = updated, changes + ["HTML entities"]

    updated = unquote(text)
    if updated != text:
        text, changes = updated, changes + ["URL percent-encoding"]

    updated = decode_js_escapes(text)
    if updated != text:
        text, changes = updated, changes + ["JavaScript hex/Unicode escapes"]

    decoded = decode_whole_base64(text.strip())
    if decoded is not None:
        text, changes = decoded, changes + ["whole-file Base64"]

    decoded = decode_whole_hex(text.strip())
    if decoded is not None:
        text, changes = decoded, changes + ["whole-file hex"]

    updated = decode_embedded_base64(text)
    if updated != text:
        text, changes = updated, changes + ["embedded Base64 strings"]
    return text, changes


def decode_layers(text: str):
    steps = []
    for pass_no in range(1, MAX_PASSES + 1):
        updated, changes = decode_one_pass(text)
        if not changes or updated == text:
            break
        steps.extend(f"Pass {pass_no}: {change}" for change in changes)
        text = updated
    return text, steps


def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧩 Decode HTML", callback_data="decode"),
         InlineKeyboardButton("📋 Formats", callback_data="formats")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🔓 HTML Obfuscation Decoder Bot\n\n"
        "একটি .html / .htm / .txt ফাইল পাঠাও। আমি সমর্থিত encoding layer decode করে "
        "নতুন ফাইল ফেরত দেব।\n\n"
        "⚠️ আমি ফাইলের JavaScript execute করি না; সব ধরনের custom/encrypted obfuscation "
        "decode করা সম্ভব নয়।"
    )
    await update.effective_message.reply_text(msg, reply_markup=keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "ব্যবহার:\n"
        "1) /start চাপো\n"
        "2) HTML/TXT ফাইল পাঠাও\n"
        "3) decoded ফাইলটি ফেরত পাবে\n\n"
        "সমর্থিত: Base64, HTML entities, URL encoding, JS \\x / \\u escapes, "
        "hex text এবং কিছু layered encoding.\n\n"
        "ফাইলটি trusted না হলে browser-এ খুলবে না—ডিকোড করা HTML-এ ক্ষতিকর code থাকতে পারে.",
        reply_markup=keyboard(),
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "formats":
        await query.message.reply_text(
            "📋 Supported formats\n"
            "• Whole-file Base64\n• Whole-file hex text\n• HTML entities\n"
            "• URL percent encoding\n• JavaScript \\xNN / \\uNNNN escapes\n"
            "• Up to 8 decoding passes\n\n"
            "Custom packers, encryption, runtime-generated payloads, and server-side code "
            "may need manual analysis."
        )
    elif query.data == "help":
        await help_cmd(update, context)
    elif query.data == "decode":
        await query.message.reply_text("এখন .html / .htm / .txt ফাইল পাঠাও।")
    elif query.data == "cancel":
        await query.message.reply_text("ঠিক আছে—বর্তমান কাজ বাতিল।", reply_markup=keyboard())


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    document = message.document
    if not document:
        return

    filename = document.file_name or "uploaded.html"
    suffix = Path(filename).suffix.lower()
    if suffix not in {".html", ".htm", ".txt"}:
        await message.reply_text("শুধু .html, .htm বা .txt ফাইল পাঠাও।")
        return
    if document.file_size and document.file_size > MAX_INPUT_BYTES:
        await message.reply_text("ফাইলটি 15 MB-এর বেশি। ছোট ফাইল পাঠাও।")
        return

    status = await message.reply_text("⏳ ফাইল পরীক্ষা ও decode করছি…")
    local_in = None
    local_out = None
    try:
        tg_file = await context.bot.get_file(document.file_id)
        local_in = Path(f"/tmp/input_{message.message_id}{suffix}")
        local_out = Path(f"/tmp/decoded_{message.message_id}.html")
        await tg_file.download_to_drive(custom_path=str(local_in))

        if local_in.stat().st_size > MAX_INPUT_BYTES:
            await status.edit_text("ফাইলটি 15 MB-এর বেশি।")
            return

        try:
            raw = local_in.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            await status.edit_text("ফাইলটি UTF-8 text নয়। UTF-8 encoded HTML/TXT পাঠাও।")
            return

        decoded, steps = decode_layers(raw)
        local_out.write_text(decoded, encoding="utf-8")

        summary = "✅ Decode সম্পন্ন হয়েছে।\n"
        summary += f"ধাপ: {len(steps)}\n" if steps else "সমর্থিত encoding layer শনাক্ত হয়নি।\n"
        if steps:
            summary += "\n".join(f"• {s}" for s in steps[:8])
        await status.edit_text(summary + "\n\n⚠️ Output trusted না হলে browser-এ খুলবে না।")

        with local_out.open("rb") as f:
            await message.reply_document(
                document=f,
                filename=f"{Path(filename).stem}_decoded.html",
                caption="Decoded HTML (JavaScript execute করা হয়নি)",
            )
    except Exception:
        log.exception("Failed to process uploaded file")
        await status.edit_text("❌ ফাইল process করা যায়নি। ফাইলটি valid text কি না পরীক্ষা করো।")
    finally:
        for path in (local_in, local_out):
            if path:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "একটি .html, .htm বা .txt ফাইল হিসেবে পাঠাও—তাহলে decode করতে পারব।",
        reply_markup=keyboard(),
    )


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is missing.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    log.info("Bot is starting")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
