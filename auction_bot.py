import time
import os
import asyncio
from datetime import datetime

import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes


# ================== CONFIG ==================

TOKEN = os.getenv("TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise ValueError("Falta TOKEN en las variables de entorno")
if not ADMIN_ID:
    raise ValueError("Falta ADMIN_ID en las variables de entorno")

ADMIN_ID = int(ADMIN_ID)

TIMER_DEFAULT = 180       # segundos
MAX_INCREMENT = 500       # incremento máximo por oferta
TZ_MEXICO = pytz.timezone("America/Mexico_City")


# ================== ESTADO ==================

end_time = None
timer_active = False
message_id = None
chat_id_global = None
timer_job = None

highest_bid = 0
highest_user = "Nadie"
highest_bid_time = None

extension_count = 0
final_extension_used = False
bids_last_minute = 0

paused = False
remaining_on_pause = 0
timer_total = TIMER_DEFAULT


# ================== HELPERS ==================

def format_time(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def reset_state():
    global end_time, timer_active, message_id, chat_id_global, timer_job
    global highest_bid, highest_user, highest_bid_time
    global extension_count, final_extension_used, bids_last_minute
    global paused, remaining_on_pause, timer_total

    end_time = None
    timer_active = False
    message_id = None
    chat_id_global = None
    timer_job = None

    highest_bid = 0
    highest_user = "Nadie"
    highest_bid_time = None

    extension_count = 0
    final_extension_used = False
    bids_last_minute = 0

    paused = False
    remaining_on_pause = 0
    timer_total = TIMER_DEFAULT


def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_ID


# ================== TIMER ==================

async def timer_callback(context: ContextTypes.DEFAULT_TYPE):
    global timer_active

    if not timer_active or paused:
        return

    remaining = int(end_time - time.time())

    if remaining <= 0:
        timer_active = False
        timer_job.schedule_removal()

        await context.bot.send_message(
            chat_id=chat_id_global,
            text="🚫 CERRADA! No se aceptan más ofertas"
        )
        await asyncio.sleep(2)
        await context.bot.send_message(
            chat_id=chat_id_global,
            text=(
                f"⏰ SUBASTA FINALIZADA\n\n"
                f"🏆 Ganador: {highest_user}\n"
                f"💰 Oferta ganadora: ${highest_bid}\n"
                f"🕐 Hora última: {highest_bid_time or '—'}"
            )
        )
        return

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id_global,
            message_id=message_id,
            text=(
                f"EN CURSO!\n"
                f"{format_time(remaining)}\n"
                f"Oferta: ${highest_bid}\n"
                f"{highest_user}"
            )
        )
    except Exception:
        pass


# ================== COMANDOS ==================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active, end_time, message_id, chat_id_global, timer_job

    if timer_active:
        await update.message.reply_text("⚠️ Ya hay una subasta en curso.")
        return

    reset_state()

    chat_id_global = update.effective_chat.id
    timer_active = True
    end_time = time.time() + timer_total

    msg = await update.message.reply_text("🚗 Iniciando subasta...")
    message_id = msg.message_id

    timer_job = context.job_queue.run_repeating(timer_callback, interval=5, first=0)


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused, remaining_on_pause

    if not is_admin(update) or not timer_active or paused:
        return

    remaining_on_pause = int(end_time - time.time())
    paused = True

    await update.message.reply_text(
        f"⏸ Subasta en pausa\nTiempo restante: {format_time(remaining_on_pause)}"
    )


async def cmd_resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused, end_time

    if not is_admin(update) or not timer_active or not paused:
        return

    end_time = time.time() + remaining_on_pause
    paused = False

    await update.message.reply_text("▶️ Subasta reanudada")


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active

    if not is_admin(update) or not timer_active:
        return

    timer_active = False
    timer_job.schedule_removal()

    await update.message.reply_text("🛑 Subasta detenida")


async def cmd_settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_total, end_time

    if not is_admin(update):
        await update.message.reply_text("❌ No tienes permiso")
        return

    try:
        minutes = int(context.args[0])
        if minutes <= 0:
            raise ValueError

        timer_total = minutes * 60

        if timer_active:
            end_time = time.time() + timer_total
            await update.message.reply_text(f"⏱ Tiempo actualizado a {minutes} minuto(s)")
        else:
            await update.message.reply_text(f"⏱ Tiempo configurado a {minutes} minuto(s)")

    except (IndexError, ValueError):
        await update.message.reply_text("Uso correcto: /settime 5")


# ================== MENSAJES ==================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global highest_bid, highest_user, highest_bid_time
    global end_time, extension_count, final_extension_used, bids_last_minute

    if not timer_active:
        await update.message.reply_text("🚫 Subasta cerrada")
        return

    if paused:
        await update.message.reply_text("⏸ Subasta en pausa")
        return

    texto = update.message.text.strip()
    if not texto.isdigit():
        return

    oferta = int(texto)
    user = update.effective_user.first_name
    remaining = int(end_time - time.time())

    if oferta <= highest_bid:
        await update.message.reply_text(f"❌ Mínimo: ${highest_bid + 1}")
        return

    if highest_bid > 0 and (oferta - highest_bid) > MAX_INCREMENT:
        await update.message.reply_text(
            f"⚠️ Incremento muy alto\nMáximo permitido: ${MAX_INCREMENT}"
        )
        return

    highest_bid = oferta
    highest_user = user
    highest_bid_time = datetime.now(TZ_MEXICO).strftime("%H:%M:%S")

    if remaining > 60:
        return

    bids_last_minute += 1

    if extension_count < 2:
        end_time += 120
        extension_count += 1
        await update.message.reply_text("🔥 +2 minutos (extensión)")
    elif not final_extension_used and bids_last_minute >= 3:
        end_time += 120
        final_extension_used = True
        await update.message.reply_text("🚨 EXTENSIÓN FINAL")


# ================== APP ==================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start",   cmd_start))
app.add_handler(CommandHandler("pause",   cmd_pause))
app.add_handler(CommandHandler("resume",  cmd_resume))
app.add_handler(CommandHandler("stop",    cmd_stop))
app.add_handler(CommandHandler("settime", cmd_settime))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

if __name__ == "__main__":
    print("Bot corriendo...")
    app.run_polling(drop_pending_updates=True)
