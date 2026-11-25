import os
from flask import Flask
from threading import Thread
import re
import asyncio
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import instaloader
import yt_dlp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

TOKEN = os.environ["BOT_TOKEN"]
MAX_SIZE = 49 * 1024 * 1024
LIMIT = asyncio.Semaphore(2)

server = Flask(__name__)

@server.route("/")
def home():
    return "Kurdi Download Bot is running!"

def run_server():
    server.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 بەخێربێیت بۆ Kurdi Download Bot\n\n"
        "📥 لینکی پۆست یان ڕیلزی ئینستاگرام بنێرە.\n"
        "🎬 ڤیدیۆ و وێنە بەبێ زیادکردنی لۆگۆ.\n\n"
        "تەنها ناوەڕۆکی گشتی و ڕێگەپێدراو."
    )


def download_media(url, shortcode, folder):
    try:
        loader = instaloader.Instaloader(
            dirname_pattern=folder,
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            post_metadata_txt_pattern="",
            max_connection_attempts=2,
            request_timeout=30,
            quiet=True,
        )

        post = instaloader.Post.from_shortcode(
            loader.context, shortcode
        )

        loader.download_post(post, target="media")

        files = [
            p for p in Path(folder).rglob("*")
            if p.is_file()
            and p.suffix.lower() in (
                ".jpg", ".jpeg", ".png", ".mp4"
            )
        ]

        if files:
            return sorted(files)

    except Exception:
        pass

    options = {
        "outtmpl": os.path.join(folder, "%(id)s.%(ext)s"),
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "noplaylist": True,
        "max_filesize": MAX_SIZE,
        "socket_timeout": 30,
        "retries": 2,
    }

    with yt_dlp.YoutubeDL(options) as downloader:
        downloader.download([url])

    return sorted(
        p for p in Path(folder).rglob("*")
        if p.is_file()
        and p.suffix.lower() in (
            ".jpg", ".jpeg", ".png", ".mp4"
        )
    )


async def handle_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.message
    url = message.text.strip()

    try:
        parsed = urlparse(url)
        match = re.fullmatch(
            r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?",
            parsed.path
        )

        if (
            parsed.scheme != "https"
            or parsed.netloc.lower() not in (
                "instagram.com",
                "www.instagram.com"
            )
            or not match
        ):
            raise ValueError()

        shortcode = match.group(1)
        url = "https://www.instagram.com" + parsed.path

    except ValueError:
        await message.reply_text(
            "❌ تکایە لینکێکی دروستی ئینستاگرام بنێرە."
        )
        return

    status = await message.reply_text(
        "⏳ خەریکی داونلۆدکردنم، تکایە چاوەڕێ بکە..."
    )

    try:
        async with LIMIT:
            with tempfile.TemporaryDirectory() as folder:
                files = await asyncio.to_thread(
                    download_media,
                    url,
                    shortcode,
                    folder
                )

                sent = 0
                skipped = 0

                for file in files:
                    if file.stat().st_size > MAX_SIZE:
                        skipped += 1
                        continue

                    with file.open("rb") as media:
                        await message.reply_document(
                            document=media,
                            filename=file.name
                        )
                    sent += 1

                if sent:
                    result = "✅ بە سەرکەوتوویی داونلۆد کرا."
                    if skipped:
                        result += "\n⚠️ هەندێک فایل زۆر گەورە بوون."
                else:
                    result = "❌ فایل بەردەست نییە یان زۆر گەورەیە."

                await status.edit_text(result)

    except Exception:
        await status.edit_text(
            "❌ داونلۆد سەرکەوتوو نەبوو.\n"
            "لەوانەیە پۆستەکە تایبەت بێت یان "
            "ئینستاگرام داونلۆدکردنی سنووردار کردبێت."
        )


def main():
    app = (
        Application.builder()
        .token(TOKEN)
        .concurrent_updates(4)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_link
        )
    )

    print("Kurdi Download Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    Thread(target=run_server, daemon=True).start()
    main()
