"""
HOS Inbox Bot – Telegram → Claude → Notion
===========================================
Zachytáva správy, posiela ich Claude, odpoveď ukladá do Notion.

NASTAVENIE – env premenné na Railway:
  TELEGRAM_TOKEN   – od BotFather
  NOTION_TOKEN     – Internal Integration Secret
  NOTION_DB_ID     – ID Notion databázy (z URL)
  ANTHROPIC_API_KEY – z console.anthropic.com

SPUSTENIE:
  pip install -r requirements.txt
  python3 bot.py
"""

import os
import logging
import datetime
import tempfile
import anthropic
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from notion_client import Client

# ─── ENV ──────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN    = os.environ.get("TELEGRAM_TOKEN")
NOTION_TOKEN      = os.environ.get("NOTION_TOKEN")
NOTION_DB_ID      = os.environ.get("NOTION_DB_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s – %(message)s")
log = logging.getLogger(__name__)

notion         = Client(auth=NOTION_TOKEN)
claude_client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Si holistický kouč a myšlienkový partner Willa.
Pristupuješ integrálne – zohľadňuješ praktické, emocionálne, systémové aj hodnotové dimenzie.
Keď Will niečo pošle:
- Ak je to myšlienka alebo problém: reflektuj, polož jednu otázku alebo navrhni jeden konkrétny krok
- Ak je to úloha alebo zámer: pomôž ho sformulovať jasne a akciovateľne
- Ak je to link alebo dokument: zhrň podstatu a relevantnosť pre Life OS
Buď stručný, direktívny, bez omáčky. Odpovedaj v slovenčine."""
# ──────────────────────────────────────────────────────────────────────────────


def now_iso():
    return datetime.datetime.now().isoformat()


def now_str():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


def ask_claude(user_message: str) -> str:
    """Pošle správu Claude a vráti odpoveď."""
    try:
        response = claude_client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
        return response.content[0].text
    except Exception as e:
        log.error(f"Claude error: {e}")
        return f"[Claude nedostupný: {e}]"


def make_paragraph_blocks(content: str) -> list:
    """Rozdelí dlhý text na bloky po 2000 znakov."""
    chunks = [content[i:i+1900] for i in range(0, len(content), 1900)]
    return [
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}]
            }
        }
        for chunk in chunks
    ]


def save_to_notion(name, typ, content, source="telegram"):
    """Uloží záznam do Notion databázy."""
    notion.pages.create(
        parent={"database_id": NOTION_DB_ID},
        properties={
            "Name":   {"title":  [{"text": {"content": name}}]},
            "Type":   {"select": {"name": typ}},
            "Date":   {"date":   {"start": now_iso()}},
            "Source": {"select": {"name": source}},
        },
        children=make_paragraph_blocks(content)
    )


# ─── HANDLERY ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 HOS Inbox aktívny.\n\n"
        "Pošli mi:\n"
        "📝 Text / myšlienku → Claude odpovie\n"
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

    # Získaj odpoveď od Claude
    await update.message.reply_text("🤔 Spracovávam...")
    claude_response = ask_claude(text)

    # Obsah do Notion: vstup + odpoveď
    notion_content = f"📥 Vstup:\n{text}\n\n🤖 Claude:\n{claude_response}"

    try:
        save_to_notion(name=name, typ=typ, content=notion_content)
        await update.message.reply_text(
            f"🤖 {claude_response}\n\n✅ Uložené do Notion"
        )
    except Exception as e:
        log.error(e)
        # Aj keď Notion zlyhá, Claude odpoveď pošleme
        await update.message.reply_text(
            f"🤖 {claude_response}\n\n⚠️ Notion zlyhal: {e}"
        )


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
            f"[Whisper transkripcia – TODO]"
        )
        save_to_notion(name=name, typ="VOICE", content=content)
        await update.message.reply_text("🎤 Hlas zachytený v Notion\n⚠️ Transkripcia zatiaľ nie je aktívna")
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
