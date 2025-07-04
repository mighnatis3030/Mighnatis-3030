import os, json, random
from functools import wraps
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler,
    CallbackQueryHandler, MessageHandler, filters, ConversationHandler
)
from telegram.error import BadRequest

# --- تنظیمات مسیر فایل‌ها ---
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
USERS_FILE  = os.path.join(BASE_DIR, "users.json")

# --- متغیرهای محیطی ---
TOKEN       = os.getenv("BOT_TOKEN")               # توکن ربات
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "989366582052") # شماره ادمین

# --- حالت‌های مکالمه (برای ConversationHandler) ---
PHONE, NAME, ADD_PRIZE_NAME, ADD_PRIZE_WEIGHT, EDIT_PRIZE_NAME, EDIT_PRIZE_WEIGHT = range(6)

# --- توابع کمکی برای کار با فایل‌های JSON ---
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- بارگذاری پیکربندی و اطلاعات کاربران ---
config = load_json(CONFIG_FILE, {
    "prizes":[
        {"name":"🎁 تخفیف 10٪", "weight":1},
        {"name":"💰 ۵۰ هزار تومان اعتبار", "weight":1},
        {"name":"❌ این بار هیچی برنده نشدی! 😅", "weight":1},
        {"name":"🔁 یک شانس دیگر! دوباره امتحان کن", "weight":1},
        {"name":"🏆 جایزه ویژه! (با ادمین تماس بگیرید)", "weight":1}
    ],
    "current_round": 1,
    "channel_username": "@mighnatis" # برای تست می توانید به کانال خودتان تغییر دهید
})
users  = load_json(USERS_FILE, {})   # {uid:{phone,name,round,spin_count}}

# --- مجموعه ادمین‌ها (برای دسترسی سریع) ---
ADMIN_IDS = set()

# --- دکوراتور برای محدود کردن دسترسی به ادمین‌ها ---
def admin_only(func):
    @wraps(func)
    async def wrapper(update:Update, context:ContextTypes.DEFAULT_TYPE):
        uid   = update.effective_user.id
        phone = users.get(str(uid), {}).get("phone")
        if phone and phone.endswith(ADMIN_PHONE.lstrip('+')): # .lstrip('+') برای حذف + از شماره در صورت وجود
            ADMIN_IDS.add(uid)
        if uid in ADMIN_IDS:
            return await func(update, context)
        if update.message:
            await update.message.reply_text("⛔️ شما ادمین نیستید و به این بخش دسترسی ندارید.")
        elif update.callback_query:
            await update.callback_query.answer("⛔️ شما ادمین نیستید و به این بخش دسترسی ندارید.", show_alert=True)
    return wrapper

# --- بررسی عضویت کاربر در کانال ---
async def is_member(bot, channel, uid):
    if not channel or channel == "@YourChannel": # برای تست می توانید این شرط را حذف کنید
        return True
    try:
        m = await bot.get_chat_member(channel, uid)
        return m.status in {"creator","administrator","member","restricted"}
    except BadRequest as e:
        print(f"Error checking channel membership for {uid} in {channel}: {e}")
        return False

# --- شروع مکالمه با ربات ---
async def start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "دوست عزیز"
    await update.message.reply_text(
        f"سلام {user_name}! 👋\n\nبه ربات گردونه شانس خوش آمدید! 🎉\n"
        "شانس خودتو امتحان کن و برنده جوایز هیجان‌انگیز شو!\n\n"
        "برای شروع، روی /spin کلیک کن تا گردونه بچرخه. 👇",
        reply_markup=ReplyKeyboardRemove() # حذف کیبورد قبلی اگر هست
    )

# --- چرخاندن گردونه شانس ---
async def spin(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    user_data_in_db = users.get(uid, {})

    # 1. بررسی عضویت در کانال
    if config["channel_username"] and not await is_member(context.bot, config["channel_username"], update.effective_user.id):
        url = f"https://t.me/{config['channel_username'].lstrip('@')}"
        kb  = [[InlineKeyboardButton("✅ عضویت در کانال", url=url)]]
        await update.message.reply_text(f"👇 برای شرکت در گردونه، اول باید عضو کانال ما بشید: {config['channel_username']}",
                                        reply_markup=InlineKeyboardMarkup(kb))
        return

    # 2. درخواست شماره موبایل (اگر قبلاً ثبت نشده)
    if "phone" not in user_data_in_db:
        kb = ReplyKeyboardMarkup([[KeyboardButton("📱 ارسال شماره موبایل من", request_contact=True)]],
                                 resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "قبل از چرخش گردونه، لطفاً شماره موبایل خود را ارسال کنید تا در صورت برنده شدن، با شما تماس بگیریم.",
            reply_markup=kb
        )
        context.user_data["stage"] = PHONE # تنظیم مرحله برای ConversationHandler
        return ConversationHandler.WAITING_FOR_PHONE

    # 3. درخواست نام و نام‌خانوادگی (اگر قبلاً ثبت نشده)
    if "name" not in user_data_in_db:
        await update.message.reply_text(
            "حالا لطفاً نام و نام‌خانوادگی کامل فارسی خود را ارسال کنید (مثال: 'علی حسینی').",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data["stage"] = NAME # تنظیم مرحله برای ConversationHandler
        return ConversationHandler.WAITING_FOR_NAME

    # 4. بررسی اینکه کاربر در دور فعلی چرخیده است یا خیر
    if user_data_in_db.get("round", 0) >= config["current_round"]:
        await update.message.reply_text(
            f"🚫 شما قبلاً در *دور شماره {config['current_round']}* گردونه را چرخاندید. "
            "لطفاً برای دور بعدی منتظر بمانید! 😉",
            parse_mode='Markdown'
        )
        return

    # 5. انجام قرعه‌کشی
    if not config["prizes"]:
        await update.message.reply_text("🚨 هیچ جایزه‌ای برای قرعه‌کشی تعریف نشده است! لطفاً ادمین را مطلع کنید.")
        return

    # فیلتر کردن جوایز بدون وزن یا وزن صفر
    valid_prizes = [p for p in config["prizes"] if p.get("weight", 0) > 0]
    if not valid_prizes:
        await update.message.reply_text("🚨 هیچ جایزه‌ای با وزن معتبر برای قرعه‌کشی وجود ندارد! لطفاً ادمین را مطلع کنید.")
        return

    chosen_prize = random.choices(
        valid_prizes,
        weights=[p["weight"] for p in valid_prizes]
    )[0]["name"]

    # 6. ذخیره اطلاعات کاربر و نتیجه
    user_data_in_db["round"] = config["current_round"]
    user_data_in_db["spin_count"] = user_data_in_db.get("spin_count", 0) + 1 # تعداد چرخش های کاربر
    user_data_in_db["last_prize"] = chosen_prize # ذخیره آخرین جایزه برنده شده
    users[uid] = user_data_in_db
    save_json(USERS_FILE, users)

    await update.message.reply_text(
        f"🎉 گردونه شانس چرخید! شما برنده شدید: \n\n✨ **{chosen_prize}** ✨\n\n"
        "امیدواریم خوشتان آمده باشد! برای اطلاعات بیشتر با ادمین تماس بگیرید. 📞",
        parse_mode='Markdown'
    )
    return ConversationHandler.END # پایان مکالمه پس از چرخش

# --- دریافت شماره موبایل ---
async def receive_phone(update:Update, context:ContextTypes.DEFAULT_TYPE):
    # این تابع توسط ConversationHandler مدیریت می‌شود
    contact_info = update.message.contact
    if not contact_info or contact_info.user_id != update.effective_user.id:
        await update.message.reply_text("🚫 لطفاً فقط شماره موبایل خودتان را از طریق دکمه 'ارسال شماره' بفرستید.")
        return PHONE # بازگشت به مرحله PHONE

    uid = str(update.effective_user.id)
    users.setdefault(uid, {})["phone"] = contact_info.phone_number
    save_json(USERS_FILE, users)

    # افزودن ادمین بر اساس شماره موبایل
    if contact_info.phone_number.endswith(ADMIN_PHONE.lstrip('+')):
        ADMIN_IDS.add(update.effective_user.id)

    await update.message.reply_text(
        "✅ شماره موبایل شما با موفقیت ثبت شد!\n"
        "حالا لطفاً نام و نام‌خانوادگی کامل فارسی خود را ارسال کنید (مثال: 'علی حسینی').",
        reply_markup=ReplyKeyboardRemove()
    )
    return NAME # رفتن به مرحله NAME

# --- دریافت نام و نام‌خانوادگی ---
async def receive_name(update:Update, context:ContextTypes.DEFAULT_TYPE):
    # این تابع توسط ConversationHandler مدیریت می‌شود
    name = update.message.text.strip()
    if not name or len(name.split()) < 2:
        await update.message.reply_text(
            "لطفاً نام و نام‌خانوادگی کامل (حداقل دو کلمه) را به فارسی وارد کنید. مثال: 'سارا احمدی'"
        )
        return NAME # بازگشت به مرحله NAME

    uid = str(update.effective_user.id)
    users.setdefault(uid, {})["name"] = name
    save_json(USERS_FILE, users)

    await update.message.reply_text(
        "🎉 ثبت‌نام شما با موفقیت کامل شد!\n"
        "حالا می‌توانید /spin را بزنید تا گردونه شانس را بچرخانید و برنده شوید! 🎡"
    )
    return ConversationHandler.END # پایان مکالمه

# --- کنسل کردن مکالمه ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        'عملیات لغو شد.',
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear() # پاک کردن داده های موقت کاربر
    return ConversationHandler.END

# --- پنل ادمین ---
@admin_only
async def admin_panel(update:Update, context:ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔄 شروع دور جدید", callback_data="admin_next_round")],
        [InlineKeyboardButton("➕ افزودن جایزه", callback_data="admin_add_prize")],
        [InlineKeyboardButton("📝 مدیریت جوایز", callback_data="admin_manage_prizes")],
        [InlineKeyboardButton("📊 گزارش کاربران", callback_data="admin_user_report")] # اضافه شده
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"🤖 به پنل ادمین خوش آمدید!\n"
        f"دور فعلی: *{config['current_round']}*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# --- شروع دور جدید (فقط برای ادمین) ---
@admin_only
async def admin_next_round(update:Update, context:ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    config["current_round"] += 1
    save_json(CONFIG_FILE, config)
    await query.edit_message_text(
        f"✅ *دور جدید* با موفقیت آغاز شد! \n\n"
        f"هم‌اکنون در *دور شماره {config['current_round']}* هستیم. \n"
        "کاربران می‌توانند دوباره شانس خود را امتحان کنند. 🥳",
        parse_mode='Markdown'
    )
    # بازگشت به پنل ادمین
    await admin_panel(query, context)


# --- مدیریت جوایز ---
@admin_only
async def admin_manage_prizes(update:Update, context:ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not config["prizes"]:
        await query.edit_message_text("❌ هیچ جایزه‌ای برای مدیریت وجود ندارد. لطفاً ابتدا جایزه اضافه کنید.")
        await admin_panel(query, context)
        return

    prize_list_text = "لیست جوایز فعلی:\n\n"
    keyboard = []
    for i, prize in enumerate(config["prizes"]):
        prize_list_text += f"{i+1}. {prize['name']} (وزن: {prize['weight']})\n"
        keyboard.append([
            InlineKeyboardButton(f"✏️ ویرایش {i+1}", callback_data=f"edit_prize_{i}"),
            InlineKeyboardButton(f"🗑️ حذف {i+1}", callback_data=f"delete_prize_{i}")
        ])

    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل ادمین", callback_data="admin_panel_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        prize_list_text,
        reply_markup=reply_markup
    )

@admin_only
async def admin_add_prize(update:Update, context:ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("لطفاً *نام جایزه جدید* را وارد کنید (مثال: '۱۰۰ هزار تومان اعتبار').", parse_mode='Markdown')
    return ADD_PRIZE_NAME # تغییر مرحله برای مکالمه

@admin_only
async def admin_receive_new_prize_name(update:Update, context:ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prize_name"] = update.message.text.strip()
    await update.message.reply_text(
        f"نام جایزه '{context.user_data['new_prize_name']}' ثبت شد.\n"
        "حالا لطفاً *وزن* این جایزه را وارد کنید (یک عدد صحیح برای احتمال برنده شدن، مثلاً '۱۰' برای احتمال بیشتر).",
        parse_mode='Markdown'
    )
    return ADD_PRIZE_WEIGHT # تغییر مرحله

@admin_only
async def admin_receive_new_prize_weight(update:Update, context:ContextTypes.DEFAULT_TYPE):
    try:
        weight = int(update.message.text.strip())
        if weight < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ وزن باید یک عدد صحیح و مثبت باشد. لطفاً دوباره وارد کنید.")
        return ADD_PRIZE_WEIGHT

    new_prize = {
        "name": context.user_data.pop("new_prize_name"),
        "weight": weight
    }
    config["prizes"].append(new_prize)
    save_json(CONFIG_FILE, config)
    await update.message.reply_text(f"✅ جایزه '{new_prize['name']}' با وزن {new_prize['weight']} با موفقیت اضافه شد.")
    # بازگشت به پنل ادمین
    await admin_panel(update, context)
    return ConversationHandler.END


@admin_only
async def admin_edit_prize_start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prize_index = int(query.data.split('_')[-1])
    
    if 0 <= prize_index < len(config["prizes"]):
        context.user_data["edit_prize_index"] = prize_index
        current_prize = config["prizes"][prize_index]
        await query.message.reply_text(
            f"در حال ویرایش جایزه: *{current_prize['name']}* (وزن: {current_prize['weight']})\n\n"
            "لطفاً *نام جدید* برای این جایزه را وارد کنید. اگر نمی‌خواهید تغییر دهید، همان نام قبلی را دوباره بنویسید.",
            parse_mode='Markdown'
        )
        return EDIT_PRIZE_NAME
    else:
        await query.message.reply_text("🚨 جایزه انتخاب شده معتبر نیست.")
        await admin_panel(query, context)
        return ConversationHandler.END

@admin_only
async def admin_receive_edited_prize_name(update:Update, context:ContextTypes.DEFAULT_TYPE):
    prize_index = context.user_data["edit_prize_index"]
    config["prizes"][prize_index]["name"] = update.message.text.strip()
    context.user_data["edited_prize_name"] = update.message.text.strip() # برای نمایش در پیام بعدی

    await update.message.reply_text(
        f"نام جایزه به '{update.message.text.strip()}' تغییر یافت.\n"
        "حالا لطفاً *وزن جدید* را وارد کنید (یک عدد صحیح).",
        parse_mode='Markdown'
    )
    return EDIT_PRIZE_WEIGHT

@admin_only
async def admin_receive_edited_prize_weight(update:Update, context:ContextTypes.DEFAULT_TYPE):
    prize_index = context.user_data.pop("edit_prize_index")
    try:
        weight = int(update.message.text.strip())
        if weight < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ وزن باید یک عدد صحیح و مثبت باشد. لطفاً دوباره وارد کنید.")
        return EDIT_PRIZE_WEIGHT

    config["prizes"][prize_index]["weight"] = weight
    save_json(CONFIG_FILE, config)
    
    edited_name = context.user_data.pop("edited_prize_name", config["prizes"][prize_index]["name"])
    await update.message.reply_text(
        f"✅ جایزه '{edited_name}' با وزن {weight} با موفقیت ویرایش شد."
    )
    # بازگشت به پنل ادمین
    await admin_panel(update, context)
    return ConversationHandler.END

@admin_only
async def admin_delete_prize(update:Update, context:ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prize_index = int(query.data.split('_')[-1])

    if 0 <= prize_index < len(config["prizes"]):
        deleted_prize = config["prizes"].pop(prize_index)
        save_json(CONFIG_FILE, config)
        await query.edit_message_text(f"🗑️ جایزه '{deleted_prize['name']}' با موفقیت حذف شد.")
    else:
        await query.edit_message_text("🚨 جایزه انتخاب شده معتبر نیست.")
    
    # بازگشت به مدیریت جوایز
    await admin_manage_prizes(query, context)

# --- گزارش کاربران (برای ادمین) ---
@admin_only
async def admin_user_report(update:Update, context:ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not users:
        await query.edit_message_text("🤷‍♂️ هیچ کاربری در سیستم ثبت‌نام نکرده است.")
        await admin_panel(query, context)
        return

    report_text = f"📊 *گزارش کاربران ثبت‌نام شده (دور {config['current_round']}):*\n\n"
    for uid, user_data in users.items():
        name = user_data.get("name", "نام نامشخص")
        phone = user_data.get("phone", "شماره نامشخص")
        last_round_played = user_data.get("round", 0)
        last_prize = user_data.get("last_prize", "ندارد")
        
        report_text += (
            f"👤 *نام:* {name}\n"
            f"📞 *شماره:* {phone}\n"
            f"⚙️ *آخرین دور بازی:* {last_round_played}\n"
            f"🏆 *آخرین جایزه:* {last_prize}\n"
            f"--- \n"
        )
    
    # تلگرام محدودیت طول پیام دارد. اگر گزارش خیلی طولانی شود، باید آن را بخش‌بندی کنیم.
    # برای سادگی، فعلاً فرض می‌کنیم طول پیام کافی است.
    if len(report_text) > 4000: # تقریباً حداکثر طول پیام در تلگرام
        await query.edit_message_text("⚠️ گزارش خیلی طولانی است و نمی‌تواند کامل نمایش داده شود. در حال کار بر روی قابلیت خروجی فایل...")
        # در آینده اینجا می توانید فایل CSV/Excel را ایجاد و ارسال کنید
    else:
        await query.edit_message_text(report_text, parse_mode='Markdown')
    
    # بازگشت به پنل ادمین
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به پنل ادمین", callback_data="admin_panel_back")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("برای انجام کارهای دیگر ادمین:", reply_markup=reply_markup)


# --- بازگشت به پنل ادمین از طریق CallbackQuery ---
async def admin_panel_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await admin_panel(query, context) # فراخوانی تابع پنل ادمین

# --- Main function ---
def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN not set! Please set the BOT_TOKEN environment variable.")
    
    app = ApplicationBuilder().token(TOKEN).build()

    # --- ConversationHandler برای فرآیند ثبت‌نام کاربر ---
    conv_handler_register = ConversationHandler(
        entry_points=[CommandHandler("spin", spin)],
        states={
            PHONE: [MessageHandler(filters.CONTACT, receive_phone)],
            NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)], # امکان لغو ثبت‌نام
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END # پایان مکالمه در صورت موفقیت
        }
    )
    app.add_handler(conv_handler_register)

    # --- ConversationHandler برای افزودن جایزه توسط ادمین ---
    conv_handler_add_prize = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_prize, pattern="^admin_add_prize$")],
        states={
            ADD_PRIZE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_new_prize_name)],
            ADD_PRIZE_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_new_prize_weight)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        map_to_parent={
            ConversationHandler.END: "some_value" # این مقدار مهم نیست، فقط برای خروج از مکالمه
        }
    )
    app.add_handler(conv_handler_add_prize)
    
    # --- ConversationHandler برای ویرایش جایزه توسط ادمین ---
    conv_handler_edit_prize = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_prize_start, pattern=r"^edit_prize_\d+$")],
        states={
            EDIT_PRIZE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_edited_prize_name)],
            EDIT_PRIZE_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_receive_edited_prize_weight)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        map_to_parent={
            ConversationHandler.END: "some_other_value"
        }
    )
    app.add_handler(conv_handler_edit_prize)


    # --- هندلرهای عمومی ---
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))
    
    # --- هندلرهای CallbackQuery ادمین ---
    app.add_handler(CallbackQueryHandler(admin_next_round, pattern="^admin_next_round$"))
    app.add_handler(CallbackQueryHandler(admin_manage_prizes, pattern="^admin_manage_prizes$"))
    app.add_handler(CallbackQueryHandler(admin_delete_prize, pattern=r"^delete_prize_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_user_report, pattern="^admin_user_report$")) # اضافه شده
    app.add_handler(CallbackQueryHandler(admin_panel_back, pattern="^admin_panel_back$"))


    print("Bot running... Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
