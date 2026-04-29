import time
import os
import logging
from datetime import datetime
 
import pytz
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
 
# ================== CONFIG ==================
 
logging.basicConfig(level=logging.WARNING)
 
TOKEN = os.getenv("TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
 
TZ = pytz.timezone("America/Mexico_City")
TIMER_DEFAULT = 180
MAX_INCREMENT = 500
TIMER_JOB_NAME = "auction_timer"
 
# ================== ESTADO ==================
 
class Auction:
    def __init__(self):
        self.reset()
 
    def reset(self):
        self.active = False
        self.paused = False
        self.end_time = None
        self.remaining = 0
        self.chat_id = None
        self.message_id = None
        self.highest_bid = 0
        self.highest_user = "Nadie"
        self.highest_time = None
        self.timer_total = TIMER_DEFAULT
        self.extension_count = 0
        self.final_extension = False
        self.bids_last_minute = 0
 
 
auction = Auction()
 
 
# ================== HELPERS ==================
 
def is_admin(update: Update):
    return update.effective_user.id == ADMIN_ID
 
 
def format_time(sec):
    m, s = divmod(max(sec, 0), 60)
    return f"{m:02d}:{s:02d}"
 
 
def cancel_timer_jobs(context: ContextTypes.DEFAULT_TYPE):
    """Cancela todos los jobs del timer sin detener el job_queue global."""
    jobs = context.job_queue.get_jobs_by_name(TIMER_JOB_NAME)
    for job in jobs:
        job.schedule_removal()
 
 
# ================== TIMER JOB ==================
 
async def timer_job(context: ContextTypes.DEFAULT_TYPE):
    if not auction.active or auction.paused:
        return
 
    remaining = int(auction.end_time - time.time())
 
    if remaining <= 0:
        auction.active = False
        cancel_timer_jobs(context)
 
        await context.bot.send_message(
            auction.chat_id, "🚫 CERRADA! No se aceptan más ofertas"
        )
        await context.bot.send_message(
            auction.chat_id,
            f"🏁 FINALIZADA\n\n"
            f"🏆 {auction.highest_user}\n"
            f"💰 ${auction.highest_bid}\n"
            f"🕐 {auction.highest_time or '—'}"
        )
        return
 
    try:
        await context.bot.edit_message_text(
            chat_id=auction.chat_id,
            message_id=auction.message_id,
            text=(
                f"⏱ {format_time(remaining)}\n"
                f"${auction.highest_bid}\n"
                f"{auction.highest_user}"
            ),
        )
    except Exception:
        pass
 
 
# ================== COMANDOS ==================
 
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
 
    if auction.active:
        await update.message.reply_text("⚠️ Ya hay una subasta activa")
        return
 
    timer_total = TIMER_DEFAULT
    if context.args:
        try:
            timer_total = int(context.args[0]) * 60
        except ValueError:
            await update.message.reply_text("Uso: /start 5")
            return
 
    cancel_timer_jobs(context)
 
    auction.reset()
    auction.active = True
    auction.chat_id = update.effective_chat.id
    auction.timer_total = timer_total
    auction.end_time = time.time() + timer_total
 
    msg = await update.message.reply_text(
        f"🚗 Subasta iniciada\n⏱ {timer_total // 60} min"
    )
    auction.message_id = msg.message_id
 
    context.job_queue.run_repeating(
        timer_job,
        interval=5,
        first=0,
        name=TIMER_JOB_NAME,
    )
 
 
async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not auction.active or auction.paused:
        return
 
    auction.remaining = int(auction.end_time - time.time())
    auction.paused = True
    await update.message.reply_text("⏸ Pausada")
 
 
async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not auction.paused:
        return
 
    auction.end_time = time.time() + auction.remaining
    auction.paused = False
    await update.message.reply_text("▶️ Reanudada")
 
 
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update) or not auction.active:
        return
 
    auction.active = False
    cancel_timer_jobs(context)
    await update.message.reply_text("🛑 Detenida")
 
 
async def kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
 
    await update.message.reply_text("💀 Bot apagándose...")
    os._exit(0)
 
 
# ================== MENSAJES ==================
 
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not auction.active or auction.paused:
        return
 
    text = update.message.text.strip()
    if not text.isdigit():
        return
 
    bid = int(text)
    user = update.effective_user.first_name
 
    if bid <= auction.highest_bid:
        return
 
    if auction.highest_bid > 0 and (bid - auction.highest_bid) > MAX_INCREMENT:
        await update.message.reply_text("⚠️ Incremento muy alto")
        return
 
    auction.highest_bid = bid
    auction.highest_user = user
    auction.highest_time = datetime.now(TZ).strftime("%H:%M:%S")
 
 
# ================== APP ==================
 
app = ApplicationBuilder().token(TOKEN).build()
 
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("pause", pause))
app.add_handler(CommandHandler("resume", resume))
app.add_handler(CommandHandler("stop", stop))
app.add_handler(CommandHandler("kill", kill))
 
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
 
 
# ================== RUN ==================
 
if __name__ == "__main__":
    print("Bot PRO corriendo...")
    app.run_polling(drop_pending_updates=True)
 
