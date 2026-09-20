import os
import asyncio
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from openai import OpenAI


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY environment variable is missing.")

client = OpenAI(api_key=OPENAI_API_KEY)


# ============================================================
# PERMISSIONS
# ============================================================

# Add Telegram user IDs that you trust here.
# You can get your Telegram ID using /id.
AUTHORIZED_USERS = set()

# Email permission is separate from normal bot permission.
EMAIL_ENABLED_USERS = set()


def is_authorized(user_id: int) -> bool:
    return user_id in AUTHORIZED_USERS


def email_permission(user_id: int) -> bool:
    return user_id in EMAIL_ENABLED_USERS


# ============================================================
# START / HELP
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Hello! I'm your personal AI assistant.\n\n"
        "Commands:\n"
        "/id - Show your Telegram ID\n"
        "/help - Show commands\n"
        "/ai <message> - Ask AI something\n"
        "/prompt <idea> - Generate a prompt\n"
        "/image <description> - Generate an image\n"
        "/remind <minutes> <message> - Set a reminder\n"
        "/email <address> | <subject> | <message> - Send email\n"
        "/permission - Show your permissions\n\n"
        "You can also simply send me a message and I'll reply."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def show_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Your Telegram ID is:\n`{update.effective_user.id}`",
        parse_mode="Markdown",
    )


async def permission_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ You are not authorized to use this bot.")
        return

    email_status = "ON" if email_permission(user_id) else "OFF"

    await update.message.reply_text(
        f"✅ Bot permission: ON\n"
        f"📧 Email permission: {email_status}"
    )


# ============================================================
# AI CHAT
# ============================================================

async def ask_ai(prompt: str) -> str:
    response = client.responses.create(
        model="gpt-5-mini",
        input=prompt,
    )

    return response.output_text


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ You don't have permission to use this bot.")
        return

    if not context.args:
        await update.message.reply_text("Example:\n/ai Write an advert for my business")
        return

    prompt = " ".join(context.args)

    try:
        answer = await ask_ai(prompt)
        await update.message.reply_text(answer[:4000])
    except Exception as e:
        await update.message.reply_text(
            f"AI error: {str(e)[:500]}"
        )


# ============================================================
# NORMAL CHAT
# ============================================================

async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text(
            "❌ You are not authorized to use this assistant."
        )
        return

    message = update.message.text

    try:
        answer = await ask_ai(
            "You are a helpful personal AI assistant. "
            "Answer naturally and concisely. "
            "Do not claim to have performed an action unless it was actually performed.\n\n"
            f"User message:\n{message}"
        )

        await update.message.reply_text(answer[:4000])

    except Exception as e:
        await update.message.reply_text(
            f"Something went wrong: {str(e)[:500]}"
        )


# ============================================================
# PROMPT GENERATOR
# ============================================================

async def prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text(
            "Example:\n/prompt A cinematic video of Lagos at night"
        )
        return

    idea = " ".join(context.args)

    try:
        prompt = await ask_ai(
            "Create a detailed professional AI-generation prompt "
            "from this idea. Include subject, environment, lighting, "
            "camera, style and quality where appropriate:\n\n"
            + idea
        )

        await update.message.reply_text(prompt[:4000])

    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)[:500]}")


# ============================================================
# IMAGE GENERATION
# ============================================================

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not context.args:
        await update.message.reply_text(
            "Example:\n/image A futuristic Lagos skyline"
        )
        return

    prompt = " ".join(context.args)

    await update.message.reply_text("🎨 Generating image...")

    try:
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size="1024x1024",
        )

        # Depending on the API response, image data may be returned
        # as base64. This starter bot reports success rather than
        # pretending a public URL exists.
        await update.message.reply_text(
            "✅ Image generated successfully.\n"
            "Your image-generation API response was received."
        )

    except Exception as e:
        await update.message.reply_text(
            f"Image generation failed: {str(e)[:500]}"
        )


# ============================================================
# REMINDERS
# ============================================================

async def reminder_callback(context: ContextTypes.DEFAULT_TYPE):
    job = context.job

    await context.bot.send_message(
        chat_id=job.chat_id,
        text=f"⏰ Reminder:\n{job.data}",
    )


async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n/remind 30 Call John\n\n"
            "This will remind you after 30 minutes."
        )
        return

    try:
        minutes = int(context.args[0])
        message = " ".join(context.args[1:])

        if minutes <= 0:
            raise ValueError

        context.job_queue.run_once(
            reminder_callback,
            when=minutes * 60,
            chat_id=update.effective_chat.id,
            data=message,
        )

        await update.message.reply_text(
            f"✅ Reminder set for {minutes} minute(s)."
        )

    except ValueError:
        await update.message.reply_text(
            "❌ First value must be a positive number of minutes."
        )


# ============================================================
# EMAIL
# ============================================================

async def send_email(to_address: str, subject: str, body: str):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")

    if not all([smtp_host, smtp_user, smtp_password]):
        raise RuntimeError(
            "SMTP configuration is missing."
        )

    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = to_address
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)


async def email_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_authorized(user_id):
        await update.message.reply_text("❌ Unauthorized.")
        return

    if not email_permission(user_id):
        await update.message.reply_text(
            "📧 Email permission is currently OFF for your account."
        )
        return

    text = update.message.text.replace("/email", "", 1).strip()

    parts = [x.strip() for x in text.split("|")]

    if len(parts) != 3:
        await update.message.reply_text(
            "Usage:\n"
            "/email email@example.com | Subject | Message"
        )
        return

    to_address, subject, body = parts

    await update.message.reply_text("📧 Sending email...")

    try:
        await asyncio.to_thread(
            send_email,
            to_address,
            subject,
            body,
        )

        await update.message.reply_text(
            "✅ Email sent successfully."
        )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Email failed: {str(e)[:500]}"
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("Bot error:", context.error)


# ============================================================
# MAIN
# ============================================================

def main():
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("id", show_id))
    application.add_handler(CommandHandler("permission", permission_command))

    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(CommandHandler("prompt", prompt_command))
    application.add_handler(CommandHandler("image", image_command))
    application.add_handler(CommandHandler("remind", remind_command))
    application.add_handler(CommandHandler("email", email_command))

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat_handler,
        )
    )

    application.add_error_handler(error_handler)

    print("🤖 Bot is running...")

    application.run_polling()


if __name__ == "__main__":
    main()
