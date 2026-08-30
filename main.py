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

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN", "8785205102:AAF2P3mbXdWDCBVuuN8nyJoG2AfjxESsCBw")

ADMIN_CHAT_ID = "mahmoud_t_bot"

TIMEZONE = pytz.timezone("Africa/Cairo")

CATEGORIES = {
    "sharia": "🕌 المواد الشرعية",
    "arabic": "📖 المواد العربية",
    "science": "🔬 المواد العلميّة/الثقافيّة"
}

SUBJECTS_DATA = {
    "علمي": {
        "sharia": ["فقه", "توحيد", "حديث", "تفسير"],
        "arabic": ["نحو", "صرف", "بلاغة", "أدب ونصوص", "مطالعة وإنشاء"],
        "science": ["كيمياء", "فيزياء", "تاريخ", "رياضيات", "إنجليزي"]
    },
    "أدبي": {
        "sharia": ["فقه", "توحيد", "حديث", "تفسير", "منطق"],
        "arabic": ["نحو", "صرف", "بلاغة", "أدب ونصوص", "مطالعة", "إنشاء", "عروض وقافية"],
        "science": ["تاريخ", "جغرافيا", "فلسفة", "علم نفس", "إنجليزي", "فرنساوي"]
    }
}

user_selected_subjects = {}
user_branch = {}
user_states = {}

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
            InlineKeyboardButton("📚 اختيار المواد للمذاكرة", callback_data="select_branch"),
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = sqlite3.connect("study_azhar_bot.db")
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO students VALUES (?, ?, ?, ?)',
                   (user.id, user.username or "بدون_معرف", user.first_name, datetime.datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

    welcome_msg = (
        "✨ **اللهم صلِّ على سيدنا محمد وعلى آله وصحبه وسلم** 🌸\n\n"
        f"أهلاً بك يا {user.first_name} في بوت تنظيم المذاكرة والمهام! 🦅\n\n"
        "اختر من القائمة أدناه للبدء:"
    )

    if update.message:
        await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

def get_branch_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔬 القسم العلمي", callback_data="set_branch_علمي")],
        [InlineKeyboardButton("📚 القسم الأدبي", callback_data="set_branch_أدبي")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_categories_keyboard(branch):
    keyboard = []
    for cat_key, cat_name in CATEGORIES.items():
        keyboard.append([InlineKeyboardButton(cat_name, callback_data=f"show_cat_{cat_key}")])
    keyboard.append([InlineKeyboardButton("✨ تأكيد المواد وبدء المذاكرة ✨", callback_data="confirm_subjects")])
    keyboard.append([InlineKeyboardButton("🔄 تغيير الشعبة (علمي/أدبي)", callback_data="select_branch")])
    return InlineKeyboardMarkup(keyboard)

def get_subjects_keyboard(user_id, branch, category_key):
    selected = user_selected_subjects.get(user_id, set())
    subjects = SUBJECTS_DATA[branch].get(category_key, [])
    
    keyboard = []
    row = []
    for subj in subjects:
        icon = "[✅]" if subj in selected else "[  ]"
        btn_text = f"{icon} {subj}"
        keyboard_data = f"tg_{category_key}_{subj}"
        row.append(InlineKeyboardButton(btn_text, callback_data=keyboard_data))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 العودة للأقسام", callback_data="back_to_cats")])
    return InlineKeyboardMarkup(keyboard)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    if data == "select_branch":
        await query.edit_message_text("🎓 **اختر شعبتك أولاً:**", reply_markup=get_branch_keyboard(), parse_mode="Markdown")

    elif data.startswith("set_branch_"):
        branch = data.replace("set_branch_", "")
        user_branch[user_id] = branch
        if user_id not in user_selected_subjects:
            user_selected_subjects[user_id] = set()
            
        await query.edit_message_text(
            f"🎯 الشعبة المختارة: **{branch}**\n\nاختر القسم لتحديد مواد اليوم:",
            reply_markup=get_categories_keyboard(branch),
            parse_mode="Markdown"
        )

    elif data == "back_to_cats":
        branch = user_branch.get(user_id, "علمي")
        selected_txt = ", ".join(list(user_selected_subjects.get(user_id, set()))) or "لا يوجد"
        await query.edit_message_text(
            f"🎯 الشعبة: **{branch}**\n📌 المواد المحددة حالياً: `{selected_txt}`\n\nاختر القسم لتحديد المواد:",
            reply_markup=get_categories_keyboard(branch),
            parse_mode="Markdown"
        )

    elif data.startswith("show_cat_"):
        cat_key = data.replace("show_cat_", "")
        branch = user_branch.get(user_id, "علمي")
        cat_name = CATEGORIES.get(cat_key, "")
        await query.edit_message_text(
            f"📂 **{cat_name}** ({branch}):\nاضغط على المادة لتحديدها أو إلغائها:",
            reply_markup=get_subjects_keyboard(user_id, branch, cat_key),
            parse_mode="Markdown"
        )

    elif data.startswith("tg_"):
        parts = data.split("_")
        cat_key = parts[1]
        subj = parts[2]
        branch = user_branch.get(user_id, "علمي")
        cat_name = CATEGORIES.get(cat_key, "")
        
        if user_id not in user_selected_subjects:
            user_selected_subjects[user_id] = set()
        
        if subj in user_selected_subjects[user_id]:
            user_selected_subjects[user_id].remove(subj)
        else:
            user_selected_subjects[user_id].add(subj)
        
        await query.edit_message_text(
            f"📂 **{cat_name}** ({branch}):\nاضغط على المادة لتحديدها أو إلغائها:",
            reply_markup=get_subjects_keyboard(user_id, branch, cat_key),
            parse_mode="Markdown"
        )

    elif data == "confirm_subjects":
        selected = list(user_selected_subjects.get(user_id, set()))
        if not selected:
            await query.message.reply_text("⚠️ يرجى اختيار مادة واحدة على الأقل!")
            return

        conn = sqlite3.connect("study_azhar_bot.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO study_sessions (user_id, subjects) VALUES (?, ?)", (user_id, ", ".join(selected)))
        conn.commit()
        conn.close()

        bless_msg = (
            "✨ **اللهم صلِّ على سيدنا محمد وعلى آله وصحبه وسلم** 🌸\n\n"
            "🚀 **تم تأكيد المواد بنجاح!**\n\n"
            f"📋 المواد المحددة: `{', '.join(selected)}`\n\n"
            "اضغط على زر **'ابدأ جلسة المذاكرة (ساعة)'** لتبدأ الـ 25 دقيقة الأولى!"
        )
        await query.message.reply_text(bless_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif data == "start_60m_session":
        await query.edit_message_text("⏱️ **بدأت جلسة المذاكرة الآن (25 دقيقة الأولى)!**\n\nركز في موادك وابتعد عن التشتت. بالتوفيق! 🎯")
        context.job_queue.run_once(session_break_notice, 1500, chat_id=query.message.chat_id, user_id=user_id)

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

async def session_break_notice(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text="☕ **انتهت الـ 25 دقيقة الأولى! حان وقت الاستراحة (5 دقائق).**\nخذ قسطاً من الراحة واسترخِ."
    )
    context.job_queue.run_once(session_resume_notice, 300, chat_id=job.chat_id, user_id=job.user_id)

async def session_resume_notice(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text="📚 **انتهت الاستراحة!**\nعد لمذاكرتك لإكمال الـ 25 دقيقة الثانية 💪"
    )
    context.job_queue.run_once(session_finished_notice, 1500, chat_id=job.chat_id, user_id=job.user_id)

async def session_finished_notice(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    await context.bot.send_message(
        chat_id=job.chat_id,
        text="🥳 **أحسنت جداً! انتهت جلسة المذاكرة كاملة (ساعة كاملة).**\n\nيمكنك البدء في جلسة جديدة أو أخذ استراحة طويلة! 🌟",
        reply_markup=get_main_keyboard()
    )

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
        try:
            await context.bot.send_message(
                chat_id=f"@{ADMIN_CHAT_ID}" if not str(ADMIN_CHAT_ID).startswith("@") and not str(ADMIN_CHAT_ID).isdigit() else ADMIN_CHAT_ID,
                text=f"⚠️ **شكوى/اقتراح جديد:**\nمن: {user.first_name} (@{user.username or 'لا يوجد'})\nID: {user.id}\n\nالرسالة:\n{text}"
            )
            await update.message.reply_text("✅ تم إرسال رسالتك إلى المشرف مباشرة. شكراً لك!", reply_markup=get_main_keyboard())
        except Exception as e:
            await update.message.reply_text("⚠️ حصل خطأ في إرسال الشكوى، تأكد أنك بدأت المحادثة مع المشرف.", reply_markup=get_main_keyboard())

    conn.close()

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
                text="✨ **اللهم صلِّ على سيدنا محمد وعلى آله وصحبه وسلم** 🌸\n\n☀️ **صباح الخير! الساعة 6:00 صباحاً** 🦅\n\nحان وقت تنظيم اليوم! افتح البوت وسجل خطة مذاكرتك ومهامك اليومية.",
                reply_markup=get_main_keyboard()
            )
        except Exception:
            pass

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

    try:
        await context.bot.send_message(
            chat_id=f"@{ADMIN_CHAT_ID}" if not str(ADMIN_CHAT_ID).startswith("@") and not str(ADMIN_CHAT_ID).isdigit() else ADMIN_CHAT_ID,
            text=msg
        )
    except Exception:
        pass

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
  
