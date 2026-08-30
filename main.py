import os
import logging
import sqlite3
import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ضبط إعدادات السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN", "8785205102:AAF2P3mbXdWDCBVuuN8nyJoG2AfjxESsCBw")
ADMIN_CHAT_ID = 123456789  # استبدل هذا الرقم بـ ID التليجرام الخاص بك لتلقي تقاريرك والشكاوى

TIMEZONE = pytz.timezone("Africa/Cairo")

# قائمة المواد الأزهرية والعامة المتاحة للاختيار
ALL_SUBJECTS = [
    "نحو", "صرف", "بلاغة", "أدب ونصوص", "مطالعة وإملاء", "عروض وقافية",
    "فقه", "توحيد", "حديث", "تفسير", "منطق",
    "إنجليزي", "فرنساوي", "كيمياء", "فيزياء", "أحياء", "رياضيات", "تاريخ", "جغرافيا", "فلسفة"
]

# ذاكرة مؤقتة لاختيارات المواد والحالات
user_selected_subjects = {}
user_states = {}

# 1. إعداد قاعدة البيانات
def init_db():
    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_date TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subjects TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_text TEXT,
            is_done INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📚 اختيار المواد للمذاكرة", callback_data="open_subjects_menu"),
            InlineKeyboardButton("⏱️ ابدأ جلسة المذاكرة (ساعة)", callback_data="start_60m_session")
        ],
        [
            InlineKeyboardButton("📝 قائمة المهام اليومية", callback_data="show_tasks"),
            InlineKeyboardButton("➕ إضافة مهمة", callback_data="add_general_task")
        ],
        [
            InlineKeyboardButton("📊 تقريري الأسبوعي", callback_data="my_weekly_report"),
            InlineKeyboardButton("📩 تقديم شكوى / اقتراح", callback_data="send_complaint")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ----------------- بدء البوت -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO students VALUES (?, ?, ?, ?)',
                   (user.id, user.username or "بدون_معرف", user.first_name, datetime.datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

    msg = f"أهلاً بك يا {user.first_name} في بوت تنظيم المذاكرة والمهام! 🦅\n\nاختر من القائمة أدناه للبدء:"
    if update.message:
        await update.message.reply_text(msg, reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, reply_markup=get_main_keyboard())

# ----------------- بناء قائمة أزرار المواد -----------------
def build_subjects_keyboard(user_id):
    selected = user_selected_subjects.get(user_id, set())
    keyboard = []
    row = []
    for subj in ALL_SUBJECTS:
        icon = "[✅]" if subj in selected else "[  ]"
        btn_text = f"{icon} {subj}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"toggle_subj_{subj}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("✨ تأكيد الاختيار وبدء المذاكرة ✨", callback_data="confirm_subjects")])
    keyboard.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")])
    return InlineKeyboardMarkup(keyboard)

# ----------------- معالجة الضغط على الأزرار -----------------
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # 1. قائمة اختيار المواد
    if data == "open_subjects_menu":
        if user_id not in user_selected_subjects:
            user_selected_subjects[user_id] = set()
        await query.edit_message_text(
            "📚 **اختر المواد التي تود مذاكرتها اليوم:**\n(اضغط على المادة لتحديدها أو إلغاء تحديدها)",
            reply_markup=build_subjects_keyboard(user_id),
            parse_mode="Markdown"
        )

    elif data.startswith("toggle_subj_"):
        subj = data.replace("toggle_subj_", "")
        if user_id not in user_selected_subjects:
            user_selected_subjects[user_id] = set()
        
        if subj in user_selected_subjects[user_id]:
            user_selected_subjects[user_id].remove(subj)
        else:
            user_selected_subjects[user_id].add(subj)
        
        await query.edit_message_text(
            "📚 **اختر المواد التي تود مذاكرتها اليوم:**\n(اضغط على المادة لتحديدها أو إلغاء تحديدها)",
            reply_markup=build_subjects_keyboard(user_id),
            parse_mode="Markdown"
        )

    elif data == "confirm_subjects":
        selected = list(user_selected_subjects.get(user_id, set()))
        if not selected:
            await query.message.reply_text("⚠️ يرجى اختيار مادة واحدة على الأقل قبل التأكيد!")
            return

        # حفظ الاختيار في قاعدة البيانات
        conn = sqlite3.connect("study_azhar_bot.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO study_sessions (user_id, subjects) VALUES (?, ?)", (user_id, ", ".join(selected)))
        conn.commit()
        conn.close()

        bless_msg = (
            "✨ **اللهم صلِّ على سيدنا محمد وعلى آله وصحبه وسلم** 🌸\n\n"
            "🚀 **ابدأ يومك بالصلاة على النبي.. ابدأ مذاكرة!**\n\n"
            f"📋 المواد المحددة: `{', '.join(selected)}`\n\n"
            "اضغط على زر **'ابدأ جلسة المذاكرة (ساعة)'** لتبدأ التوقيت!"
        )
        await query.message.reply_text(bless_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

    # 2. جلسة المذاكرة (ساعة: 25 م + 5 ر + 25 م)
    elif data == "start_60m_session":
        await query.edit_message_text("⏱️ **بدأت جلسة المذاكرة (25 دقيقة الأولى)!**\nاستعن بالله وابتعد عن المشتتات. 🎯")
        # تنبيه 1: بعد 25 دقيقة (1500 ثانية) -> استراحة 5 دقائق
        context.job_queue.run_once(session_break_notice, 1500, chat_id=query.message.chat_id, user_id=user_id)

    # 3. المهام اليومية
    elif data == "show_tasks":
        await display_tasks(query.message, user_id)

    elif data == "add_general_task":
        user_states[user_id] = {"action": "awaiting_general_task"}
        await query.message.reply_text("✍️ اكتب المهمة الجديدة الآن:")

    elif data.startswith("tog_"):
        task_id = int(data.split("_")[1])
        conn = sqlite3.connect("study_azhar_bot.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET is_done = NOT is_done WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        await display_tasks(query.message, user_id, is_edit=True)

    elif data == "send_complaint":
        user_states[user_id] = {"action": "awaiting_complaint"}
        await query.message.reply_text("📩 اكتب شكواك أو اقتراحك الآن وسوف يتم إرسالها للمشرف مباشرة:")

    elif data == "my_weekly_report":
        await send_individual_weekly_report(user_id, context)

    elif data == "main_menu":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=get_main_keyboard())

# ----------------- مراحل جلسة المذاكرة الساعية -----------------
async def session_break_notice(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text="☕ **حان وقت الاستراحة! (5 دقائق)**\nخد قسطاً من الراحة واسترخِ قليلاً."
    )
    # تنبيه 2: بعد 5 دقائق (300 ثانية) -> عودة للمذاكرة
    context.job_queue.run_once(session_resume_notice, 300, chat_id=job.chat_id, user_id=job.user_id)

async def session_resume_notice(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text="📚 **انتهت الاستراحة!**\nعد لمذاكرتك لإكمال الـ 25 دقيقة المتبقية من الجلسة 💪"
    )
    # تنبيه 3: بعد 25 دقيقة أخرى (1500 ثانية) -> انتهاء الجلسة
    context.job_queue.run_once(session_finished_notice, 1500, chat_id=job.chat_id, user_id=job.user_id)

async def session_finished_notice(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text="🥳 **أحسنت! انتهت جلسة المذاكرة كاملة (ساعة كاملة).**\n\nيمكنك الآن اختيار مواد جديدة أو أخذ استراحة طويلة! 🌟",
        reply_markup=get_main_keyboard()
    )

# ----------------- استقبال النصوص -----------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id, {})
    action = state.get("action")
    text = update.message.text.strip()

    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()

    if action == "awaiting_general_task":
        cursor.execute("INSERT INTO tasks (user_id, task_text) VALUES (?, ?)", (user_id, text))
        conn.commit()
        user_states[user_id] = {}
        await update.message.reply_text(f"✅ تم إضافة المهمة: **{text}**", parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif action == "awaiting_complaint":
        user = update.effective_user
        user_states[user_id] = {}
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"⚠️ **شكوى/اقتراح جديد:**\nمن: {user.first_name} (@{user.username or 'لا يوجد'})\nالمعرف: {user.id}\n\nالرسالة:\n{text}"
        )
        await update.message.reply_text("✅ تم إرسال رسالتك إلى المشرف مباشرة. شكراً لك!", reply_markup=get_main_keyboard())

    conn.close()

# ----------------- عرض المهام اليومية -----------------
async def display_tasks(message, user_id, is_edit=False):
    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, task_text, is_done FROM tasks WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        msg = "📭 لا توجد مهام حالية."
        reply_markup = get_main_keyboard()
    else:
        msg = "📋 **مهامك اليومية:** (اضغط على المهمة لتعديل حالتها ✅/❌)\n"
        keyboard = []
        for task_id, task_text, is_done in rows:
            icon = "[✅]" if is_done else "[  ]"
            keyboard.append([InlineKeyboardButton(f"{icon} {task_text}", callback_data=f"tog_{task_id}")])
        keyboard.append([InlineKeyboardButton("🔙 الرئيسية", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)

    if is_edit:
        await message.edit_text(msg, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await message.reply_text(msg, reply_markup=reply_markup, parse_mode="Markdown")

# ----------------- التقرير الأسبوعي -----------------
async def send_individual_weekly_report(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()
    week_ago = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("SELECT subjects, timestamp FROM study_sessions WHERE user_id = ? AND timestamp >= ?", (user_id, week_ago))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await context.bot.send_message(chat_id=user_id, text="📅 لم تسجل أي مواد مذاكرة خلال هذا الأسبوع. شد حيلك للأسبوع القادم! 💪")
        return

    report = "📊 **تقريرك الأسبوعي للمذاكرة:**\n\nإليك المواد التي اخترتها وذاكرتها هذا الأسبوع:\n"
    for subjs, time_str in rows:
        report += f"• [{time_str[:10]}] {subjs}\n"

    await context.bot.send_message(chat_id=user_id, text=report)

# ----------------- التنبيهات المجدولة -----------------

# 1. تنبيه 6:00 صباحاً
async def morning_reminder(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM students")
    users = cursor.fetchall()
    conn.close()

    for (u_id,) in users:
        try:
            await context.bot.send_message(
                chat_id=u_id,
                text="☀️ **صباح الخير! الساعة 6:00 صباحاً** 🦅\n\nحان وقت تنظيم اليوم! افتح البوت وسجل خطة مذاكرتك ومهامك اليومية.",
                reply_markup=get_main_keyboard()
            )
        except Exception:
            pass

# 2. تنبيه 6:00 مساءً
async def evening_reminder(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM students")
    users = cursor.fetchall()
    
    for (u_id,) in users:
        cursor.execute("SELECT task_text FROM tasks WHERE user_id = ? AND is_done = 0", (u_id,))
        pending = cursor.fetchall()
        try:
            if pending:
                msg = f"🌅 **تذكير 6:00 مساءً** ⏰\n\nما زال لديك **{len(pending)}** مهام لم تكتمل بعد:\n"
                for p in pending:
                    msg += f"• {p[0]}\n"
                msg += "\nاستعن بالله وأكمل باقي اليوم!"
            else:
                msg = "🌅 **تذكير 6:00 مساءً** 🌟\nرائع جداً! أنهيت جميع مهامك، يمكنك إضافة مهام جديدة للمساء إن أردت."
            
            await context.bot.send_message(chat_id=u_id, text=msg, reply_markup=get_main_keyboard())
        except Exception:
            pass
    conn.close()

# 3. تقرير يومي لك كمشرف (10:00 مساءً)
async def daily_admin_report(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    cursor.execute('''
        SELECT s.first_name, s.username, ss.subjects
        FROM study_sessions ss
        JOIN students s ON ss.user_id = s.user_id
        WHERE DATE(ss.timestamp) = ?
    ''', (today,))
    today_sessions = cursor.fetchall()
    conn.close()

    msg = f"📋 **تقرير اليوم للمشرف ({today}):**\n\n"
    if today_sessions:
        msg += "🔹 **الطلاب الذين سجلوا المواد اليوم:**\n"
        for name, uname, subjs in today_sessions:
            msg += f"- {name} (@{uname}): [{subjs}]\n"
    else:
        msg += "🔹 لا يوجد نشاط مذاكرة جديد اليوم.\n"

    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg)

# ----------------- تشغيل التطبيق -----------------
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()

    job_queue = app.job_queue
    job_queue.run_daily(morning_reminder, time=datetime.time(hour=6, minute=0, tzinfo=TIMEZONE))
    job_queue.run_daily(evening_reminder, time=datetime.time(hour=18, minute=0, tzinfo=TIMEZONE))
    job_queue.run_daily(daily_admin_report, time=datetime.time(hour=22, minute=0, tzinfo=TIMEZONE))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("البوت يعمل بنجاح...")
    app.run_polling()
  
