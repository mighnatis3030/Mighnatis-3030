import os, json, random
from functools import wraps
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters
)
from telegram.error import BadRequest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
USERS_FILE  = os.path.join(BASE_DIR, "users.json")

TOKEN       = os.getenv("bot183830:7c86e9e4-3334-4a64-a3f6-cc2dbdbf52f5")               # توکن ربات را متغیر محیطی کن
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "989366582052")

# ---------- فایل‌ها ----------
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

config = load_json(CONFIG_FILE, {
    "prizes":[
        {"name":"🎁 تخفیف 10٪","weight":1},
        {"name":"💰 ۵۰ هزار تومان","weight":1},
        {"name":"❌ هیچی برنده نشدی","weight":1},
        {"name":"🔁 دوباره امتحان کن","weight":1},
        {"name":"🏆 جایزه ویژه","weight":1}
    ],
    "current_round":1,
    "channel_username":"@mighnatis"
})
users  = load_json(USERS_FILE, {})   # {uid:{phone,name,round}}

ADMIN_IDS = set()

# ---------- دکوراتور ادمین ----------
def admin_only(func):
    @wraps(func)
    async def wrapper(update:Update, context:ContextTypes.DEFAULT_TYPE):
        uid   = update.effective_user.id
        phone = users.get(str(uid), {}).get("phone")
        if phone and phone.endswith(ADMIN_PHONE):
            ADMIN_IDS.add(uid)
        if uid in ADMIN_IDS:
            return await func(update, context)
        await update.message.reply_text("⛔️ شما ادمین نیستید.")
    return wrapper

# ---------- عضویت در کانال ----------
async def is_member(bot, channel, uid):
    if not channel or channel == "@YourChannel":
        return True
    try:
        m = await bot.get_chat_member(channel, uid)
        return m.status in {"creator","administrator","member","restricted"}
    except BadRequest:
        return False

# ---------- دستورات ----------
async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! برای چرخش گردونه /spin را بزن.")

async def spin(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)

    # کانال
    if not await is_member(context.bot, config["channel_username"], update.effective_user.id):
        url = f"https://t.me/{config['channel_username'].lstrip('@')}"
        kb  = [[InlineKeyboardButton("عضویت در کانال", url=url)]]
        await update.message.reply_text(f"اول عضو کانال {config['channel_username']} شو.",
                                        reply_markup=InlineKeyboardMarkup(kb))
        return

    data = users.get(uid, {})
    # شماره
    if "phone" not in data:
        kb = ReplyKeyboardMarkup([[KeyboardButton("📱 ارسال شماره", request_contact=True)]],
                                 resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text("شماره موبایل خود را بفرست:", reply_markup=kb)
        context.user_data["stage"] = "phone"
        return
    # نام
    if "name" not in data:
        await update.message.reply_text("نام و نام‌خانوادگی فارسی را بفرست:",
                                        reply_markup=ReplyKeyboardRemove())
        context.user_data["stage"] = "name"
        return
    # یک‌بار در هر دور
    if data.get("round", 0) >= config["current_round"]:
        await update.message.reply_text("🚫 در این دور قبلاً چرخاندی.")
        return
    # قرعه
    prize   = random.choices(config["prizes"],
                 weights=[p["weight"] for p in config["prizes"]])[0]["name"]
    data["round"] = config["current_round"]
    users[uid] = data
    save_json(USERS_FILE, users)
    await update.message.reply_text(f"🎯 نتیجه: {prize}")

# ---------- دریافت شماره ----------
async def contact(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("stage") != "phone":
        return
    c = update.message.contact
    if c.user_id != update.effective_user.id:
        return
    uid = str(update.effective_user.id)
    users.setdefault(uid, {})["phone"] = c.phone_number
    save_json(USERS_FILE, users)
    if c.phone_number.endswith(ADMIN_PHONE):
        ADMIN_IDS.add(update.effective_user.id)
    context.user_data["stage"] = "name"
    await update.message.reply_text("نام و نام‌خانوادگی فارسی را بفرست:",
                                    reply_markup=ReplyKeyboardRemove())

# ---------- دریافت نام ----------
async def reg_name(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("stage") != "name":
        return
    name = update.message.text.strip()
    if len(name.split()) < 2:
        await update.message.reply_text("نام کامل را وارد کن.")
        return
    uid = str(update.effective_user.id)
    users.setdefault(uid, {})["name"] = name
    save_json(USERS_FILE, users)
    context.user_data["stage"] = None
    await update.message.reply_text("✅ ثبت‌نام کامل شد! دوباره /spin را بزن.")

# ---------- پنل ادمین ----------
@admin_only
async def admin(update:Update, context:ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("🔄 شروع دور جدید", callback_data="next_round")]]
    await update.message.reply_text("ادمین:", reply_markup=InlineKeyboardMarkup(kb))

@admin_only
async def next_round(update:Update, context:ContextTypes.DEFAULT_TYPE):
    config["current_round"] += 1
    save_json(CONFIG_FILE, config)
    await update.message.reply_text(f"✅ دور {config['current_round']} شروع شد.")

# ---------- main ----------
def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN not set!")
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("spin", spin))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CommandHandler("next_round", next_round))
    app.add_handler(MessageHandler(filters.CONTACT, contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reg_name))
    print("Bot running...")
    app.run_polling()
if __name__ == "__main__":
    main()