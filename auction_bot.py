import time
import os
import asyncio
import logging
from datetime import datetime

import pytz
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes


# ================== CONFIG ==================

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not TOKEN or not ADMIN_ID:
    raise ValueError("Faltan variables de entorno")

ADMIN_ID = int(ADMIN_ID)

TIMER_DEFAULT = 180
MAX_INCREMENT = 500
TZ = pytz.timezone("America/Mexico_City")


# ================== ESTADO ==================

class AuctionState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.timer_active = False
        self.paused = False
        self.end_time = None
        self.remaining_on_pause = 0

        self.chat_id = None
        self.message_id = None
        self.timer_task = None

        self.highest_bid = 0
        self.highest_user = "Nadie"
        self.highest_bid_time = None

        self.extension_count = 0
        self.final_extension_used = False
        self.bids_last_minute = 0

        self.timer_total = TIMER_DEFAULT


state = AuctionState()


# ================== HELPERS ==================

def is_admin(update: Update):
    return update.effective_user.id == ADMIN_ID


def format_time(seconds):
    m, s = divmod(max(seconds, 0), 60)
    return f"{m:02d}:{s:02d}"


# ================== TIMER ==================

async def timer_loop(bot: Bot):
    logging.info("Timer iniciado")

    while state.timer_active:
        await asyncio.sleep(5)

        if not state.timer_active:
            break

        if state.paused:
            continue

        remaining = int(state.end_time - time.time())

        if remaining <= 0:
            state.timer_active = False

            try:
                await bot.send_message(state.chat_id, "🚫 CERRADA! No se aceptan más ofertas")
                await asyncio.sleep(2)
                await bot.send_message(
                    state.chat_id,
                    f"⏰ SUBASTA FINALIZADA\n\n"
                    f"🏆 Ganador: {state.highest_user}\n"
                    f"💰 Oferta: ${state.highest_bid}\n"
                    f"🕐 Hora: {state.highest_bid_time or '—'}"
                )
            except Exception as e:
                logging.error(f"Error cierre: {e}")

            break

        try:
            await bot.edit_message_text(
                chat_id=state.chat_id,
                message_id=state.message_id,
                text=(
                    f"EN CURSO\n"
                    f"{format_time(remaining)}\n"
                    f"${state.highest_bid}\n"
                    f"{state.highest_user}"
                )
            )
        except:
            pass


# ================== COMANDOS ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if state.timer_active:
        await update.message.reply_text("⚠️ Ya hay una subasta activa")
        return

    # tiempo opcional
    if context.args:
        try:
            minutes = int(context.args[0])
            if minutes <= 0:
                raise ValueError
            state.timer_total = minutes * 60
        except:
            await update.message.reply_text("Uso: /start 5")
            return

    state.reset()

    state.timer_active = True
    state.chat_id = update.effective_chat.id
    state.end_time = time.time() + state.timer_total

    msg = await update.message.reply_text(
        f"🚗 Subasta iniciada\n⏱ {state.timer_total // 60} min"
    )
    state.message_id = msg.message_id

    state.timer_task = asyncio.create_task(timer_loop(context.bot))


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not state.timer_active or state.paused:
        return

    state.remaining_on_pause = int(state.end_time - time.time())
    state.paused = True

    await update.message.reply_text(
        f"⏸ Pausada\n{format_time(state.remaining_on_pause)}"
    )


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not state.timer_active or not state.paused:
        return

    state.end_time = time.time() + state.remaining_on_pause
    state.paused = False

    await update.message.reply_text("▶️ Reanudada")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not state.timer_active:
        return

    state.timer_active = False

    if state.timer_task:
        state.timer_task.cancel()

    await update.message.reply_text("🛑 Subasta detenida")


async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return

    try:
        minutes = int(context.args[0])
        if minutes <= 0:
            raise ValueError

        state.timer_total = minutes * 60

        if state.timer_active:
            state.end_time = time.time() + state.timer_total
            await update.message.reply_text(f"⏱ Actualizado a {minutes} min")
        else:
            await update.message.reply_text(f"⏱ Configurado a {minutes} min")

    except:
        await update.message.reply_text("Uso: /settime 5")


# ================== MENSAJES ==================

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not state.timer_active:
        return

    if state.paused:
        return

    text = update.message.text.strip()

    if not text.isdigit():
        return

    bid = int(text)
    user = update.effective_user.first_name

    if bid <= state.highest_bid:
        return

    if state.highest_bid > 0 and (bid - state.highest_bid) > MAX_INCREMENT:
        await update.message.reply_text("⚠️ Incremento muy alto")
        return

    state.highest_bid = bid
    state.highest_user = user
    state.highest_bid_time = datetime.now(TZ).strftime("%H:%M:%S")


# ================== APP ==================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("pause", pause))
app.add_handler(CommandHandler("resume", resume))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("settime", settime))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))


# ================== RUN ==================

if __name__ == "__main__":
    logging.info("Bot corriendo...")
    app.run_polling(drop_pending_updates=True)

