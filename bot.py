"""
HOS Inbox Bot – Telegram → Notion
==================================
Zachytáva všetko čo mu pošleš a ukladá do Notion databázy.

NASTAVENIE – doplň tieto tri hodnoty:
1. TELEGRAM_TOKEN   – od BotFather
2. NOTION_TOKEN     – z notion.so/profile/integrations → tvoja integrácia → Internal Integration Secret
3. NOTION_DB_ID     – ID tvojej Notion databázy (z URL)

SPUSTENIE:
  pip install -r requirements.txt
  python3 bot.py
"""

import os
import logging
import datetime
import tempfile
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from notion_client import Client

# ─── DOPLŇ TOTO ───────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
NOTION_DB_ID   = os.environ.get("NOTION_DB_ID")
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s – %(message)s")
log = logging.getLogger(__name__)

notion = Client(auth=NOTION_TOKEN)


def now_iso():
    return datetime.datetime.now().isoformat()


def now_str():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


def save_to_notion(name, typ, content, source="telegram"):
    """Uloží záznam do Notion databázy."""
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Name":    {"title":  [{"text": {"content": name}}]},
            "Type":    {"select": {"name": typ}},
            "Date":    {"date":   {"start": now_iso()}},
            "Source":  {"select": {"name": source}},
        },
        children=[
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": content}}]
                }
            }
        ]
    )


# ─── HANDLERY ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 HOS Inbox aktívny.\n\n"
        "Pošli mi:\n"
        "📝 Text / myšlienku\n"
        "🎤 Hlasovú správu\n"
        "📄 PDF / dokument\n"
        "🖼 Fotku (s popisom)\n"
        "🔗 Link\n\n"
        "Všetko ide do Notion → OS Inbox"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    is_link = text.startswith("http://") or text.startswith("https://")
    typ = "LINK" if is_link else "NOTE"
    name = f"{typ} – {now_str()}"

    try:
        save_to_notion(name=name, typ=typ, content=text)
        await update.message.reply_text(f"✅ {typ} uložený do Notion")
    except Exception as e:
        log.error(e)
        await update.message.reply_text(f"❌ Chyba: {e}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = f"VOICE – {now_str()}"
    try:
        file = await context.bot.get_file(update.message.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            size = os.path.getsize(tmp.name)
            os.unlink(tmp.name)

        content = (
            f"Hlasová správa zachytená: {now_str()}\n"
            f"Veľkosť: {size} bytes\n"
            f"File ID: {update.message.voice.file_id}\n\n"
            f"[Hlasová správa – pre transkripciu pripoj Whisper API]"
        )
        save_to_notion(name=name, typ="VOICE", content=content)
        await update.message.reply_text("🎤 Hlas zachytený v Notion")
    except Exception as e:
        log.error(e)
        await update.message.reply_text(f"❌ Chyba: {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    name = f"DOC – {doc.file_name or 'subor'} – {now_str()}"
    content = (
        f"Dokument: {doc.file_name}\n"
        f"Typ: {doc.mime_type}\n"
        f"Veľkosť: {doc.file_size} bytes\n"
        f"File ID: {doc.file_id}"
    )
    try:
        save_to_notion(name=name, typ="DOCUMENT", content=content)
        await update.message.reply_text(f"📄 Dokument zachytený v Notion\n{doc.file_name}")
    except Exception as e:
        log.error(e)
        await update.message.reply_text(f"❌ Chyba: {e}")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.caption or ""
    name = f"PHOTO – {now_str()}"
    content = (
        f"Fotka zachytená: {now_str()}\n"
        f"File ID: {update.message.photo[-1].file_id}\n"
    )
    if caption:
        content += f"\nPopis:\n{caption}"

    try:
        save_to_notion(name=name, typ="PHOTO", content=content)
        await update.message.reply_text(
            "🖼 Fotka zachytená v Notion"
            + (f"\n📝 Popis: {caption}" if caption else "")
        )
    except Exception as e:
        log.error(e)
        await update.message.reply_text(f"❌ Chyba: {e}")


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤔 Tento typ zatiaľ nepodporujem.\nSkús text, hlas, fotku alebo dokument."
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.ALL, handle_unknown))
    log.info("🤖 HOS Bot beží...")
    app.run_polling()


if __name__ == "__main__":
    main()
