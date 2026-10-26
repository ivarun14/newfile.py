import logging
import asyncio
import re
import sqlite3
import os
import threading
import http.server
import socketserver
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
)

# Gemini AI & PDF Libraries
try:
    from google import genai
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
except ImportError:
    import subprocess
    subprocess.run(["pip", "install", "google-genai", "reportlab", "python-telegram-bot"])
    from google import genai
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

# -------------------------------------------------------------------
# RENDER DUMMY WEB SERVER (To prevent "Application exited early")
# -------------------------------------------------------------------
PORT = int(os.environ.get("PORT", 10000))

class HealthCheckHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is active and running successfully!")

def run_web_server():
    with socketserver.TCPServer(("", PORT), HealthCheckHandler) as httpd:
        print(f"Web server running on port {PORT}")
        httpd.serve_forever()

# Background thread me web server start kar rahe hain
threading.Thread(target=run_web_server, daemon=True).start()

# -------------------------------------------------------------------
# CONFIGURATION & API KEYS
# -------------------------------------------------------------------
BOT_TOKEN = "8913215515:AAHSiZMG3VFmTWFVZN3JCBTK_JsFEjo3RC8"
ADMIN_CHAT_ID = "5611130588"

# Gemini API Key
GEMINI_API_KEY = "AQ.Ab8RN6K3kR9e6LYwwL54bctXrKBnmCVJmomNDyaGWGk1ochyrA"

# UPI Payment Details (₹99 Fixed)
UPI_ID = "rajputvarun2914@oksbi"
PAYEE_NAME = "Varun Rajput"
FIXED_AMOUNT = 99

# Telegram Web App URL
WEB_APP_URL = "https://core.telegram.org/bots/webapps"

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation States
LANG, ASK_NAME, ASK_PHONE, ASK_DOB, ASK_TIME, LIVE_CHAT = range(6)

# -------------------------------------------------------------------
# DATABASE SETUP
# -------------------------------------------------------------------
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            phone TEXT,
            dob TEXT,
            birth_time TEXT,
            username TEXT,
            language TEXT,
            amount INTEGER DEFAULT 99,
            status TEXT DEFAULT 'PENDING',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def save_user_to_db(user_id, name, phone, dob, birth_time, username, language, amount):
    try:
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO users (user_id, name, phone, dob, birth_time, username, language, amount, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
            ON CONFLICT(user_id) DO UPDATE SET
                name=excluded.name,
                phone=excluded.phone,
                dob=excluded.dob,
                birth_time=excluded.birth_time,
                username=excluded.username,
                language=excluded.language,
                amount=excluded.amount,
                created_at=CURRENT_TIMESTAMP
        """, (user_id, name, phone, dob, birth_time, username, language, amount))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error: {e}")

def update_user_status(user_id, status):
    try:
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Update Error: {e}")

init_db()

# -------------------------------------------------------------------
# GEMINI AI ENGINES
# -------------------------------------------------------------------
def generate_gemini_astrology_insights(name, dob, birth_time, language):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Generate a professional astrological and cosmic future roadmap analysis for:\n"
            f"Name: {name}, DOB: {dob}, Birth Time: {birth_time}, Language/Tone: {language}.\n"
            f"Focus deeply on Planetary & Cosmic Alignments and Zodiac energy."
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        return "Planetary Alignment Analysis: Your cosmic chart shows strong celestial positioning for upcoming growth."

def generate_gemini_wealth_insights(name, dob, birth_time, language):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Provide a detailed Career, Wealth Forecast and Personal Life Remedies section for a client named {name}, "
            f"DOB: {dob}, Time: {birth_time}, Tone: {language}."
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        logger.error(f"Gemini Wealth Error: {e}")
        return "Career & Wealth Forecast: Major financial milestones and career breakthroughs are indicated in your near future."

def generate_pdf_report(name, dob, phone, birth_time, language):
    filename = f"Future_Report_{name.replace(' ', '_')}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=15, textColor=colors.navy, spaceAfter=8, alignment=1)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=9, textColor=colors.dimgrey, spaceAfter=12, alignment=1)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=10, leading=14, spaceAfter=8)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=12, textColor=colors.darkblue, spaceBefore=8, spaceAfter=4)

    story.append(Paragraph(f"🔮 FUTUREPREDICTOR AI - ASTROLOGY REPORT 🔮", title_style))
    story.append(Paragraph(f"<b>Generated via Gemini AI Intelligence</b>", subtitle_style))
    
    data = [
        [Paragraph(f"<b>Client:</b> {name}", body_style), Paragraph(f"<b>DOB:</b> {dob}", body_style)],
        [Paragraph(f"<b>Birth Time:</b> {birth_time}", body_style), Paragraph(f"<b>Phone:</b> {phone}", body_style)],
        [Paragraph(f"<b>Report Type:</b> Premium Vedic Roadmap", body_style), Paragraph(f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}", body_style)]
    ]
    t = Table(data, colWidths=[250, 250])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.whitesmoke),
        ('BOX', (0,0), (-1,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>✨ Part 1: Cosmic & Planetary Analysis</b>", heading_style))
    gemini_text = generate_gemini_astrology_insights(name, dob, birth_time, language)
    for line in gemini_text.split('\n'):
        if line.strip():
            story.append(Paragraph(line, body_style))

    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>💡 Part 2: Career, Wealth & Remedy Forecast</b>", heading_style))
    wealth_text = generate_gemini_wealth_insights(name, dob, birth_time, language)
    for line in wealth_text.split('\n'):
        if line.strip():
            story.append(Paragraph(line, body_style))

    story.append(Spacer(1, 10))
    story.append(Paragraph(f"<i>Confidential Astrological Report © FuturePredictor AI.</i>", ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.gray, alignment=1)))

    doc.build(story)
    return filename

# -------------------------------------------------------------------
# HANDLERS & CONVERSATION FLOW (₹99 Fixed)
# -------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [
        [InlineKeyboardButton("🇮🇳 Hinglish", callback_data="lang_hinglish")],
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_english")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "✨ Welcome to FuturePredictor AI 🔮\n\n"
        "Please choose your preferred language:",
        reply_markup=reply_markup
    )
    return LANG

async def language_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    lang = "Hinglish" if "hinglish" in query.data else "English"
    context.user_data["language"] = lang

    await query.message.edit_text(
        f"✅ Language selected: **{lang}**\n\n"
        "👉 Apni kundli prediction shuru karne ke liye, kripya apna **Pura Naam (Full Name)** yahan bhejiye:",
        parse_mode="Markdown"
    )
    return ASK_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["name"] = update.message.text
    
    contact_button = KeyboardButton(text="📱 Share Phone Number", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[contact_button]], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        "✅ Naam Save Ho Gaya Hai!\n\n"
        "Ab verification ke liye apna Mobile Number share karein:",
        reply_markup=reply_markup
    )
    return ASK_PHONE

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.contact:
        phone = update.message.contact.phone_number
    else:
        phone = update.message.text.strip()
        cleaned_phone = re.sub(r'[\s\-()]', '', phone)
        if not re.match(r'^(\+91)?\d{10}$', cleaned_phone):
            await update.message.reply_text("❌ Kripya ek valid 10-digit Mobile Number bhejiye:")
            return ASK_PHONE

    context.user_data["phone"] = phone
    await update.message.reply_text("✅ Phone Number Verified!", reply_markup=ReplyKeyboardRemove())
    await update.message.reply_text("Ab apni **Date of Birth** bhejiye (e.g., 15/08/2002):", parse_mode="Markdown")
    return ASK_DOB

async def get_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["dob"] = update.message.text
    await update.message.reply_text("✅ DOB Saved!\n\nAb apna **Birth Time** bhejiye (e.g., 10:30 AM ya Skip):", parse_mode="Markdown")
    return ASK_TIME

async def get_time_and_show_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["time"] = update.message.text

    name = context.user_data.get("name", "User")
    phone = context.user_data.get("phone", "N/A")
    dob = context.user_data.get("dob", "N/A")
    birth_time = context.user_data.get("time", "N/A")
    lang = context.user_data.get("language", "Hinglish")
    
    tg_user = update.effective_user
    username = f"@{tg_user.username}" if tg_user.username else "N/A"

    save_user_to_db(tg_user.id, name, phone, dob, birth_time, username, lang, FIXED_AMOUNT)

    try:
        admin_keyboard = [
            [
                InlineKeyboardButton(f"✅ Approve (₹{FIXED_AMOUNT})", callback_data=f"approve_{tg_user.id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{tg_user.id}")
            ]
        ]
        admin_markup = InlineKeyboardMarkup(admin_keyboard)

        admin_report = (
            f"🚨 <b>New Lead Generated (₹99)!</b>\n\n"
            f"👤 <b>Name:</b> {name}\n"
            f"📱 <b>Phone:</b> {phone}\n"
            f"📅 <b>DOB:</b> {dob} | ⏰ {birth_time}\n"
            f"🆔 <b>User ID:</b> <code>{tg_user.id}</code>"
        )
        await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_report, parse_mode="HTML", reply_markup=admin_markup)
    except Exception as e:
        logger.error(f"Admin Error: {e}")

    payment_text = (
        f"📊 **PREMIUM ASTROLOGY REPORT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Name: {name}\n"
        f"💰 **Amount to Pay: ₹{FIXED_AMOUNT}**\n\n"
        f"💳 **UPI ID:** `{UPI_ID}`\n"
        f"👤 **Payee Name:** {PAYEE_NAME}\n\n"
        "⚠️ **Instructions:**\n"
        f"UPI ID par **₹{FIXED_AMOUNT}** pay karke screenshot niche support par bhejein, taaki admin turant aapki report approve karein!"
    )

    keyboard = [
        [InlineKeyboardButton("💬 Send Payment Screenshot / Support", url="https://t.me/Varun001212")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(payment_text, reply_markup=reply_markup, parse_mode="Markdown")
    return ConversationHandler.END

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    parts = data.split("_")
    action = parts[0]
    target_user_id = int(parts[1])

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, dob, phone, birth_time, language FROM users WHERE user_id = ?", (target_user_id,))
    user_row = cursor.fetchone()
    conn.close()

    if not user_row:
        await query.edit_message_text("❌ User data not found.")
        return

    name, dob, phone, birth_time, language = user_row

    if action == "approve":
        update_user_status(target_user_id, "APPROVED")
        
        pdf_path = generate_pdf_report(name, dob, phone, birth_time, language)

        try:
            await context.bot.send_document(
                chat_id=target_user_id,
                document=open(pdf_path, "rb"),
                caption="🎉 **Payment Verified!**\nAapka payment approve ho gaya hai. Yeh rahi aapki PDF report!"
            )
            os.remove(pdf_path)

            webapp_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("🌐 Open Astrology Mini-App", web_app=WebAppInfo(url=WEB_APP_URL))],
                [InlineKeyboardButton("💬 Start AI Astrologer Live Chat", callback_data="start_live_chat")]
            ])
            await context.bot.send_message(
                chat_id=target_user_id,
                text="👑 **Exclusive Access Unlocked!**\nAb aap Mini-App explore kar sakte hain ya Live Chat shuru kar sakte hain:",
                reply_markup=webapp_keyboard
            )

            await query.edit_message_text(f"✅ Approved package and sent features to user ID: {target_user_id}")
        except Exception as e:
            await query.edit_message_text(f"⚠️ Approved in DB, but delivery failed: {e}")

    elif action == "reject":
        update_user_status(target_user_id, "REJECTED")
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text="❌ Aapka payment verification reject ho gaya hai. Kripya support par sampark karein: https://t.me/Varun001212"
            )
        except:
            pass
        await query.edit_message_text(f"❌ Rejected user ID: {target_user_id}")

# -------------------------------------------------------------------
# LIVE CHAT HANDLERS
# -------------------------------------------------------------------
async def start_live_chat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "🤖 **AI Astrologer Live Chat Activated!**\n\n"
        "Poochiye apna koi bhi sawaal. Chat khatam karne ke liye `/endchat` type karein."
    )
    return LIVE_CHAT

async def live_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_message = update.message.text
    if user_message and user_message.startswith("/endchat"):
        await update.message.reply_text("Live chat session end ho gaya hai. Dobara start karne ke liye /start use karein.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"You are an elite personal astrologer and life strategist. Answer this question warmly and wisely: {user_message}"
        )
        await update.message.reply_text(response.text)
    except Exception as e:
        logger.error(f"Live chat error: {e}")
        await update.message.reply_text("Technical error. Kripya thodi der baad try karein.")
    
    return LIVE_CHAT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Process cancel ho gaya hai.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != str(ADMIN_CHAT_ID):
        return
    try:
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(amount) FROM users WHERE status = 'APPROVED'")
        revenue = cursor.fetchone()[0] or 0
        conn.close()
        await update.message.reply_text(f"📊 **Bot Stats (₹99 Model):**\n\n• Total Users: {total}\n• Total Revenue: ₹{revenue}")
    except Exception as e:
        logger.error(f"Stats error: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LANG: [CallbackQueryHandler(language_choice, pattern="^lang_")],
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            ASK_PHONE: [
                MessageHandler(filters.CONTACT, get_phone),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)
            ],
            ASK_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dob)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time_and_show_payment)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    live_chat_handler_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_live_chat_callback, pattern="^start_live_chat$")],
        states={
            LIVE_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, live_chat_handler)]
        },
        fallbacks=[CommandHandler("endchat", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(live_chat_handler_conv)
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^(approve|reject)_"))
    app.add_handler(CommandHandler("stats", stats))

logger.info("🤖 Gemini-Powered ₹99 Astrologer Bot is running...")
app.run_polling()

if __name__== "__main__":
    main()
