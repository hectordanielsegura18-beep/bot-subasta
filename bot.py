import time
import threading
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

# Lock para threading (solo para el hilo del timer)
lock = threading.Lock()

# ================== FUNCIONES ==================
def format_time(seconds):
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def timer_loop(app, loop):
    """Hilo del timer — usa run_coroutine_threadsafe para llamadas async al bot."""
    global timer_active, end_time

    while timer_active:
        time.sleep(1)

        with lock:
            remaining = int(end_time - time.time())

            if remaining <= 0:
                timer_active = False

                asyncio.run_coroutine_threadsafe(
                    app.bot.edit_message_text(
                        chat_id=chat_id_global,
                        message_id=message_id,
                        text=(
                            f"⏰ SUBASTA FINALIZADA\n\n"
                            f"🏆 Ganador: {highest_user}\n"
                            f"💰 Oferta: ${highest_bid}"
                        )
                    ),
                    loop
                )
                break

            try:
                asyncio.run_coroutine_threadsafe(
                    app.bot.edit_message_text(
                        chat_id=chat_id_global,
                        message_id=message_id,
                        text=(
                            f"🚗 SUBASTA EN CURSO\n"
                            f"⏳ Tiempo: {format_time(remaining)}\n"
                            f"💰 Mejor oferta: ${highest_bid}\n"
                            f"👤 Lider: {highest_user}"
                        )
                    ),
                    loop
                )
            except Exception:
                pass


# ================== COMANDOS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active, end_time, message_id, chat_id_global
    global highest_bid, highest_user

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ No tienes permiso para iniciar la subasta")
        return

    chat_id = update.effective_chat.id

    with lock:
        if timer_active:
            await update.message.reply_text("⚠️ Ya hay una subasta en curso")
            return

        timer_active = True
        end_time = time.time() + timer_total
        chat_id_global = chat_id
        highest_bid = 0
        highest_user = "Nadie"

    msg = await update.message.reply_text("🚗 Iniciando subasta...")
    message_id = msg.message_id

    # Obtener el event loop actual para pasarlo al hilo
    loop = asyncio.get_event_loop()
    threading.Thread(target=timer_loop, args=(context.application, loop), daemon=True).start()


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ No tienes permiso")
        return

    with lock:
        timer_active = False

    await update.message.reply_text("🛑 Subasta detenida manualmente")


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_total

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ No tienes permiso")
        return

    try:
        minutos = int(context.args[0])
        if minutos <= 0:
            raise ValueError
        timer_total = minutos * 60
        await update.message.reply_text(f"⏱ Tiempo configurado a {minutos} minutos")
    except (IndexError, ValueError):
        await update.message.reply_text("Uso: /settime 5  (número entero positivo)")


# ================== MENSAJES ==================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global end_time, timer_active, highest_bid, highest_user

    if not timer_active:
        return

    texto = update.message.text.strip()

    # Solo números
    if not texto.isdigit():
        return

    oferta = int(texto)
    user = update.effective_user.first_name

    # Usar lock solo para leer/escribir variables compartidas (sin await adentro)
    with lock:
        if not timer_active:
            return

        remaining = int(end_time - time.time())
        es_mejor = oferta > highest_bid
        ultimo_minuto = remaining <= 60

        if es_mejor:
            highest_bid = oferta
            highest_user = user
            if ultimo_minuto:
                end_time += 120

    # Los awaits van FUERA del lock
    if es_mejor:
        await update.message.reply_text(f"💰 Nueva mejor oferta: ${oferta} por {user}")
        if ultimo_minuto:
            await update.message.reply_text("🔥 ¡Último minuto! Se agregan +2 minutos")
    else:
        await update.message.reply_text(f"❌ Oferta muy baja. La mejor oferta actual es ${highest_bid}")


# ================== APP ==================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("settime", set_time))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))


# ================== RUN ==================
if __name__ == "__main__":
    print("Bot corriendo...")
    app.run_polling()

