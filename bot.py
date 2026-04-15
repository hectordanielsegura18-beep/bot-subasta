import time
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ================== VARIABLES ==================
TOKEN = os.getenv("TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise ValueError("Falta TOKEN")

if not ADMIN_ID:
    raise ValueError("Falta ADMIN_ID")

ADMIN_ID = int(ADMIN_ID)

# ================== ESTADO ==================
timer_total = 180
end_time = None
timer_active = False
message_id = None
chat_id_global = None

highest_bid = 0
highest_user = "Nadie"

# ================== FUNCIONES ==================
def format_time(seconds):
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


# ================== TIMER ==================
async def timer_callback(context: ContextTypes.DEFAULT_TYPE):
    global timer_active, end_time

    if not timer_active:
        return

    remaining = int(end_time - time.time())

    if remaining <= 0:
        timer_active = False

        await context.bot.edit_message_text(
            chat_id=chat_id_global,
            message_id=message_id,
            text=f"⏰ SUBASTA FINALIZADA\n\n🏆 Ganador: {highest_user}\n💰 Oferta: ${highest_bid}"
        )
        return

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id_global,
            message_id=message_id,
            text=(
                f"🚗 SUBASTA EN CURSO\n"
                f"⏳ Tiempo: {format_time(remaining)}\n"
                f"💰 Mejor oferta: ${highest_bid}\n"
                f"👤 Lider: {highest_user}"
            )
        )
    except:
        pass


# ================== COMANDOS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active, end_time, message_id, chat_id_global
    global highest_bid, highest_user

    chat_id = update.effective_chat.id

    timer_active = True
    end_time = time.time() + timer_total
    chat_id_global = chat_id
    highest_bid = 0
    highest_user = "Nadie"

    msg = await update.message.reply_text("🚗 Iniciando subasta...")
    message_id = msg.message_id

    # 🔥 Timer correcto (sin threading)
    context.job_queue.run_repeating(timer_callback, interval=

