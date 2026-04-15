import time
import os
import asyncio
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ================== VARIABLES ==================
TOKEN = os.getenv("TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN:
    raise ValueError("Falta TOKEN en las variables de entorno")
if not ADMIN_ID:
    raise ValueError("Falta ADMIN_ID en las variables de entorno")

ADMIN_ID = int(ADMIN_ID)

# ================== CONFIG ==================
timer_total = 180
MAX_INCREMENT = 500  # 🔥 evita errores de dedo

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

# 🆕 PAUSA
paused = False
remaining_on_pause = 0


# ================== HELPERS ==================
def format_time(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def reset_state():
    global end_time, timer_active, message_id, chat_id_global, timer_job
    global highest_bid, highest_user, highest_bid_time
    global extension_count, final_extension_used, bids_last_minute
    global paused, remaining_on_pause

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


# ================== TIMER ==================
async def timer_callback(context: ContextTypes.DEFAULT_TYPE):
    global timer_active

    if not timer_active or paused:
        return

    remaining = int(end_time - time.time())

    if remaining <= 0:
        timer_active = False

        if timer_job:
            timer_job.schedule_removal()

        # 🔥 MENSAJE FINAL NUEVO (no editado)
        await context.bot.send_message(
            chat_id=chat_id_global,
            text=(
                f"⏰ SUBASTA FINALIZADA\n\n"
                f"🏆 Ganador: {highest_user}\n"
                f"💰 Oferta ganadora: ${highest_bid}\n"
                f"🕐 Hora última: {highest_bid_time if highest_bid_time else '—'}"
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
    except Exception as e:
        pass


# ================== COMANDOS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
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


# 🆕 PAUSE
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused, remaining_on_pause, end_time

    if update.effective_user.id != ADMIN_ID:
        return

    if not timer_active or paused:
        return

    remaining_on_pause = int(end_time - time.time())
    paused = True

    await update.message.reply_text(
        f"⏸ Subasta en pausa\nTiempo restante: {format_time(remaining_on_pause)}"
    )


# 🆕 RESUME
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global paused, end_time

    if update.effective_user.id != ADMIN_ID:
        return

    if not timer_active or not paused:
        return

    end_time = time.time() + remaining_on_pause
    paused = False

    await update.message.reply_text("▶️ Subasta reanudada")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active, timer_job

    if update.effective_user.id != ADMIN_ID:
        return

    if not timer_active:
        return

    timer_active = False

    if timer_job:
        timer_job.schedule_removal()

    await update.message.reply_text("🛑 Subasta detenida")


# ================== MENSAJES ==================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global highest_bid, highest_user, highest_bid_time
    global end_time, extension_count, final_extension_used, bids_last_minute

    if not timer_active:
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

    # 🔥 VALIDACIÓN BASE
    if oferta <= highest_bid:
        await update.message.reply_text(f"❌ Mínimo: ${highest_bid + 1}")
        return

    # 🔥 ANTI ERRORES (incremento máximo)
    if highest_bid > 0 and (oferta - highest_bid) > MAX_INCREMENT:
        await update.message.reply_text(
            f"⚠️ Incremento muy alto\nMáximo permitido: ${MAX_INCREMENT}"
        )
        return

    # ✅ ACEPTAR OFERTA
    highest_bid = oferta
    highest_user = user

    tz_mexico = pytz.timezone("America/Mexico_City")
    highest_bid_time = datetime.now(tz_mexico).strftime("%H:%M:%S")

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

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("pause", pause))
app.add_handler(CommandHandler("resume", resume))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))


# ================== RUN ==================
if __name__ == "__main__":
    print("Bot corriendo...")
    asyncio.run(app.run_polling())
