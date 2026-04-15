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

# ================== ESTADO ==================
timer_total = 180  # segundos por defecto

end_time = None
timer_active = False
message_id = None
chat_id_global = None
timer_job = None  # FIX: referencia al job para poder cancelarlo

highest_bid = 0
highest_user = "Nadie"
highest_bid_time = None  # Timestamp de la última puja ganadora

extension_count = 0
final_extension_used = False
bids_last_minute = 0


# ================== HELPERS ==================
def format_time(seconds: int) -> str:
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def reset_state():
    """Resetea todas las variables de la subasta."""
    global end_time, timer_active, message_id, chat_id_global, timer_job
    global highest_bid, highest_user
    global extension_count, final_extension_used, bids_last_minute

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


# ================== TIMER ==================
async def timer_callback(context: ContextTypes.DEFAULT_TYPE):
    global timer_active

    if not timer_active:
        return

    remaining = int(end_time - time.time())

    if remaining <= 0:
        timer_active = False

        # Cancelar el job para que no siga corriendo
        if timer_job:
            timer_job.schedule_removal()

        await context.bot.edit_message_text(
            chat_id=chat_id_global,
            message_id=message_id,
            text=(
                f"⏰ SUBASTA FINALIZADA\n\n"
                f"🏆 Ganador: {highest_user}\n"
                f"💰 Oferta final: ${highest_bid}\n"
                f"🕐 Última puja: {highest_bid_time if highest_bid_time else '—'}"
            )
        )
        return

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id_global,
            message_id=message_id,
            text=(
                f"EN CURSO!\n"
                f"⏳ Tiempo: {format_time(remaining)}\n"
                f"💰 Mejor oferta: ${highest_bid}\n"
                f"👤 Líder: {highest_user}"
            )
        )
    except Exception as e:
        error_str = str(e)

        if "Message is not modified" in error_str:
            pass  # Normal, el mensaje no cambió

        elif "Flood control exceeded" in error_str:
            # Extraer segundos de espera y pausar
            try:
                retry_seconds = int(error_str.split("Retry in ")[1].split(" ")[0])
            except (IndexError, ValueError):
                retry_seconds = 5
            print(f"[timer] Flood control, esperando {retry_seconds}s")
            await asyncio.sleep(retry_seconds)

        else:
            print(f"[timer_callback] Error inesperado: {e}")


# ================== COMANDOS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active, end_time, message_id, chat_id_global, timer_job

    if timer_active:
        await update.message.reply_text("⚠️ Ya hay una subasta en curso. Usa /stop para detenerla.")
        return

    reset_state()

    chat_id_global = update.effective_chat.id
    timer_active = True
    end_time = time.time() + timer_total

    msg = await update.message.reply_text("🚗 Iniciando subasta...")
    message_id = msg.message_id

    # FIX: guardar referencia al job para poder cancelarlo después
    timer_job = context.job_queue.run_repeating(timer_callback, interval=5, first=0)


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active, timer_job

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ No tienes permiso para detener la subasta")
        return

    if not timer_active:
        await update.message.reply_text("⚠️ No hay ninguna subasta activa")
        return

    timer_active = False

    if timer_job:
        timer_job.schedule_removal()

    await update.message.reply_text(
        f"🛑 Subasta detenida\n\n"
        f"🏆 Último líder: {highest_user}\n"
        f"💰 Última oferta: ${highest_bid}"
    )


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_total

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ No tienes permiso para cambiar el tiempo")
        return

    if timer_active:
        await update.message.reply_text("⚠️ No puedes cambiar el tiempo con una subasta en curso")
        return

    try:
        minutos = int(context.args[0])
        if minutos <= 0:
            raise ValueError("El tiempo debe ser mayor a 0")
        timer_total = minutos * 60
        await update.message.reply_text(f"⏱ Tiempo configurado a {minutos} minuto(s)")
    except (IndexError, ValueError):
        await update.message.reply_text("Uso correcto: /settime 5")


# ================== MENSAJES ==================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global highest_bid, highest_user, highest_bid_time
    global end_time, extension_count, final_extension_used, bids_last_minute

    if not timer_active:
        return

    texto = update.message.text.strip()

    if not texto.isdigit():
        return

    oferta = int(texto)
    user = update.effective_user.first_name
    remaining = int(end_time - time.time())

    if oferta <= highest_bid:
        await update.message.reply_text(
            f"❌ Oferta inválida. La oferta mínima es ${highest_bid + 1}"
        )
        return

    highest_bid = oferta
    highest_user = user
    tz_mexico = pytz.timezone("America/Mexico_City")
    highest_bid_time = datetime.now(tz_mexico).strftime("%H:%M:%S")

    if remaining > 60:
        return

    # Lógica de extensiones en el último minuto
    bids_last_minute += 1

    if extension_count < 2:
        end_time += 120
        extension_count += 1
        await update.message.reply_text(
            f"🔥 ¡Último minuto! +2 minutos añadidos (Extensión {extension_count}/2)"
        )

    elif not final_extension_used and bids_last_minute >= 3:
        end_time += 120
        final_extension_used = True
        await update.message.reply_text("🚨 EXTENSIÓN FINAL ACTIVADA — +2 minutos extra")


# ================== APP ==================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("settime", set_time))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))


# ================== RUN ==================
if __name__ == "__main__":
    print("Bot corriendo...")
    asyncio.run(app.run_polling())
