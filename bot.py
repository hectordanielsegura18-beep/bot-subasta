import time
import threading
import os
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

lock = threading.Lock()

# ================== FUNCIONES ==================
def format_time(seconds):
    m = seconds // 60
    s = seconds % 60
    return f"{m:02d}:{s:02d}"


def timer_loop(context):
    global timer_active, end_time

    while timer_active:
        time.sleep(1)

        with lock:
            remaining = int(end_time - time.time())

            if remaining <= 0:
                timer_active = False

                context.bot.edit_message_text(
                    chat_id=chat_id_global,
                    message_id=message_id,
                    text=f"⏰ SUBASTA FINALIZADA\n\n🏆 Ganador: {highest_user}\n💰 Oferta: ${highest_bid}"
                )
                break

            try:
                context.bot.edit_message_text(
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

    with lock:
        timer_active = True
        end_time = time.time() + timer_total
        chat_id_global = chat_id
        highest_bid = 0
        highest_user = "Nadie"

    msg = await update.message.reply_text("🚗 Iniciando subasta...")
    message_id = msg.message_id

    threading.Thread(target=timer_loop, args=(context,), daemon=True).start()


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_active

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ No tienes permiso")
        return

    timer_active = False
    await update.message.reply_text("🛑 Subasta detenida")


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global timer_total

    try:
        minutos = int(context.args[0])
        timer_total = minutos * 60
        await update.message.reply_text(f"⏱ Tiempo configurado a {minutos} minutos")
    except:
        await update.message.reply_text("Uso: /settime 5")


# ================== MENSAJES ==================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global end_time, timer_active, highest_bid, highest_user

    if not timer_active:
        return

    texto = update.message.text

    # Solo números
    if not texto.isdigit():
        return

    oferta = int(texto)
    user = update.effective_user.first_name

    with lock:
        remaining = int(end_time - time.time())

        if oferta > highest_bid:
            highest_bid = oferta
            highest_user = user

            await update.message.reply_text(f"💰 Nueva mejor oferta: ${oferta} por {user}")

            # Extensión en último minuto
            if remaining <= 60:
                end_time += 120
                await update.message.reply_text("🔥 Último minuto! +2 minutos")
        else:
            await update.message.reply_text("❌ Oferta menor a la actual")


# ================== APP ==================
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("settime", set_time))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))


# ================== RUN ==================
import asyncio

if _name_ == "_main_":
    print("Bot corriendo...")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(app.run_polling())
