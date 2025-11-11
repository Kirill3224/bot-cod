# -*- coding: utf-8 -*-
"""
Головний файл бота "Privacy Sentry" (v2.8 - Skip Logic)
Реалізує stateless логіку для генерації документів приватності.
"""

import logging
import os
import html
from datetime import date
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest

# Локальні імпорти
import templates
from pdf_utils import create_pdf_from_markdown, clear_temp_file

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Завантаження конфігурації ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("!!! Змінна BOT_TOKEN не знайдена в .env файлі !!!")
    exit()

# === Етапи для Conversation Handlers ===

# --- Етапи для "Політики" ---
(
    POLICY_START,
    POLICY_Q_PROJECT_NAME,
    POLICY_Q_CONTACT,
    POLICY_Q_DATA_COLLECTED,
    POLICY_Q_DATA_STORAGE,
    POLICY_Q_DELETE_MECHANISM,
) = range(6)

# --- Етапи для "DPIA" ---
(
    DPIA_START,
    DPIA_Q_PROJECT_NAME,
    DPIA_Q_TEAM,
    DPIA_Q_GOAL,
    DPIA_Q_DATA_LIST,
    DPIA_Q_MINIMIZATION_START,
    DPIA_Q_MINIMIZATION_STATUS,
    DPIA_Q_MINIMIZATION_REASON,
    DPIA_Q_RETENTION_PERIOD,
    DPIA_Q_RETENTION_MECHANISM,
    DPIA_Q_STORAGE,
    DPIA_Q_RISK,
    DPIA_Q_MITIGATION,
    DPIA_GENERATE,
) = range(14)


# --- (ОНОВЛЕНО v2.8) Етапи для "Чек-ліста" (19 етапів) ---
# Ми все ще використовуємо ті ж 19 етапів, але логіка в ConversationHandler
# буде розрізняти Text (для нотатки) та Callback (для skip)
(
    CHECKLIST_START, # C0
    # Категорія 1 (3*2 = 6)
    C1_S1_NOTE, # C1
    C1_S2_STATUS, # C2
    C1_S2_NOTE, # C3
    C1_S3_STATUS, # C4
    C1_S3_NOTE, # C5
    # Категорія 2 (3*2 = 6)
    C2_S1_STATUS, # C6
    C2_S1_NOTE, # C7
    C2_S2_STATUS, # C8
    C2_S2_NOTE, # C9
    C2_S3_STATUS, # C10
    C2_S3_NOTE, # C11
    # Категорія 3 (3*2 = 6)
    C3_S1_STATUS, # C12
    C3_S1_NOTE, # C13
    C3_S2_STATUS, # C14
    C3_S2_NOTE, # C15
    C3_S3_STATUS, # C16
    C3_S3_NOTE, # C17
    # Генерація
    CHECKLIST_GENERATE, # C18
) = range(19) 


# === 1. Головне Меню та Допоміжні Функції ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Надсилає головне меню."""
    clear_user_data(context)

    keyboard = [
        ["📄 Сгенерувати Політику Конфіденційності"],
        ["📝 Пройти Оцінку Ризиків (DPIA Lite)"],
        ["✅ Пройти Чек-ліст Безпеки"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    
    await update.message.reply_text(
        "Привіт! Я бот 'Privacy Sentry' (v2.8 - *Фінальний*).\n\n"
        "Я допоможу вам згенерувати артефакти приватності для вашого студентського проєкту, дотримуючись 'stateless' принципу (я нічого про вас не зберігаю).\n\n"
        "Оберіть опцію:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    return ConversationHandler.END 

async def show_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показує власну політику приватності бота."""
    await update.message.reply_text(templates.BOT_PRIVACY_POLICY, parse_mode=ParseMode.MARKDOWN)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показує контакти."""
    await update.message.reply_text(templates.BOT_HELP, parse_mode=ParseMode.MARKDOWN)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Скасовує поточну операцію та очищує дані."""
    clear_user_data(context)
    await delete_main_message(context) 
    
    await update.message.reply_text(
        "Дію скасовано. Усі зібрані відповіді видалено з моєї пам'яті.",
        reply_markup=ReplyKeyboardRemove(),
    )
    # Переконуємося, що ми надсилаємо 'start' з об'єктом message,
    # навіть якщо 'cancel' був викликаний з CallbackQuery
    message = update.message if update.message else update.callback_query.message
    
    # Створюємо новий об'єкт Update лише з 'message', якщо це необхідно
    # (Це складний, але надійний спосіб викликати 'start' з 'query')
    if not update.message:
        fake_update = Update(update_id=update.update_id, message=message)
        await start(fake_update, context)
    else:
        await start(update, context)
        
    return ConversationHandler.END

def clear_user_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Безпечно очищує context.user_data."""
    user_id = context._user_id
    if context.user_data:
        logger.info(f"Очищення даних для user {user_id}.")
        context.user_data.clear()
    else:
        logger.info(f"Для user {user_id} немає даних для очищення.")

# === 2. Логіка "Політики Конфіденційності" (1/3) ===

async def start_policy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Починає розмову про Політику."""
    clear_user_data(context)
    logger.info(f"User {update.effective_user.id} почав 'Політику'.")
    
    await update.message.reply_text(
        "Гаразд. Для генерації Політики потрібно пройти швидкий аудит (5 питань).\n\n"
        "Натисніть /cancel у будь-який момент, щоб скасувати.", # (ВИПРАВЛЕНО v2.8) - 'L/'
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text("Яка [Назва Вашого Проєкту]?")
    return POLICY_Q_CONTACT

async def policy_q_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['project_name'] = update.message.text
    await update.message.reply_text("Ваш [Контакт: @username або email для зв'язку]?")
    return POLICY_Q_DATA_COLLECTED

async def policy_q_data_collected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['contact'] = update.message.text
    await update.message.reply_text("Які дані ви збираєте? (напр., [Telegram ID, Номер групи, email])")
    return POLICY_Q_DATA_STORAGE

async def policy_q_data_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['data_collected'] = update.message.text
    await update.message.reply_text("Де ви зберігаєте дані? (напр., [Google Sheets, сервер Heroku, Firebase])")
    return POLICY_Q_DELETE_MECHANISM

async def policy_q_delete_mechanism(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['data_storage'] = update.message.text
    await update.message.reply_text("Який простий механізм видалення даних ви пропонуєте? (напр., [команда /deleteme в боті])")
    return POLICY_START

async def policy_generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Генерує PDF Політики."""
    context.user_data['delete_mechanism'] = update.message.text
    user_id = update.effective_user.id
    logger.info(f"User {user_id}: генерація PDF Політики.")

    generating_msg = await update.message.reply_text(
        "Дякую! Всі відповіді зібрано. Генерую ваш PDF...\n"
        "(Це може зайняти 10-15 секунд)"
    )

    data_dict = {
        'project_name': html.escape(context.user_data.get('project_name', '[Назва Вашого Проєкту]')),
        'contact': html.escape(context.user_data.get('contact', '[Ваш @username або email]')),
        'data_collected': html.escape(context.user_data.get('data_collected', '[Дані, які ви збираєте]')),
        'data_storage': html.escape(context.user_data.get('data_storage', '[Де ви зберігаєте дані]')),
        'delete_mechanism': html.escape(context.user_data.get('delete_mechanism', '[Опишіть простий механізм]')),
        'date': date.today().strftime("%d.%m.%Y"),
    }

    try:
        # Для Політики ми все ще використовуємо Markdown
        filled_markdown = templates.POLICY_TEMPLATE.format(**data_dict)
        
        pdf_file_path = create_pdf_from_markdown(
            content=filled_markdown,
            is_html=False, # Вказуємо, що це Markdown
            output_filename=f"policy_{user_id}.pdf"
        )
        
        await update.message.reply_document(document=open(pdf_file_path, 'rb'))
        await update.message.reply_text(
            "Ваша Політика Конфіденційності готова. Я видалив усі ваші відповіді зі своєї пам'яті.\n\n"
            "Натисніть /start, щоб згенерувати інший документ."
        )
        clear_temp_file(pdf_file_path)

    except Exception as e:
        logger.error(f"PDF generation failed for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"Під час генерації PDF сталася помилка: {e}")
    
    finally:
        try:
            await context.bot.delete_message(chat_id=generating_msg.chat_id, message_id=generating_msg.message_id)
        except Exception as e:
            logger.warning(f"Не вдалося видалити 'Генерую...' {e}")
            
        logger.info(f"Очищення даних для user {user_id}. Причина: Генерація політики завершена.")
        clear_user_data(context)
        return ConversationHandler.END


# === 3. Логіка "DPIA Lite" (2/3) - Таблична версія ===

async def start_dpia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Починає новий DPIA."""
    clear_user_data(context)
    logger.info(f"User {update.effective_user.id} почав 'DPIA'.")
    
    context.user_data['minimization_data'] = []
    context.user_data['data_list'] = []
    context.user_data['current_data_index'] = 0

    await update.message.reply_text(
        "Гаразд. Проведемо повну Оцінку Впливу (DPIA Lite).\n\n"
        "Це анкета з 6-ти розділів (відповідно до `1_dpie_lite.xlsx`). Це займе 3-5 хвилин.\n\n"
        "Натисніть /cancel у будь-який момент, щоб скасувати.", # (ВИПРАВЛЕНО v2.8) - 'L/'
        reply_markup=ReplyKeyboardRemove(),
    )
    await update.message.reply_text("**Розділ 1: Проєкт**\nЯка [Назва проєкту]?", parse_mode=ParseMode.MARKDOWN)
    return DPIA_Q_TEAM

async def dpia_q_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['project_name'] = update.message.text
    await update.message.reply_text("Хто [Керівник/Розробник:] (Ваше ПІБ та роль)?")
    return DPIA_Q_GOAL

async def dpia_q_goal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['team'] = update.message.text
    await update.message.reply_text("**Розділ 2: Мета**\nЯку проблему вирішує сервіс? (1-2 речення)", parse_mode=ParseMode.MARKDOWN)
    return DPIA_Q_DATA_LIST

async def dpia_q_data_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['goal'] = update.message.text
    await update.message.reply_text(
        "**Розділ 3: Дані**\n"
        "Введіть **список** даних, які ви плануєте збирати. Будь ласка, введіть **кожен пункт з нового рядка**.\n\n"
        "(Напр.:\nTelegram ID\nНомер групи\nEmail)",
        parse_mode=ParseMode.MARKDOWN
    )
    return DPIA_Q_MINIMIZATION_START

async def dpia_q_minimization_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отримує список даних і запускає цикл мінімізації."""
    data_list = [item.strip() for item in update.message.text.split('\n') if item.strip()]
    
    if not data_list:
        await update.message.reply_text("Список даних не може бути порожнім. Спробуйте ще раз. Введіть дані, по одному на рядок.")
        return DPIA_Q_MINIMIZATION_START

    context.user_data['data_list'] = data_list
    context.user_data['current_data_index'] = 0
    context.user_data['minimization_data'] = []
    
    await update.message.reply_text(
        f"Дякую. Я 'запам'ятав' ці {len(data_list)} пункти.\n\n"
        "Тепер перейдемо до найважливішого..."
    )
    
    # Викликаємо перший 'ask'
    message = update.message if update.message else update.callback_query.message
    return await dpia_ask_minimization_status(message, context)

async def dpia_ask_minimization_status(message: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Динамічно ставить питання про статус для поточного пункту даних."""
    index = context.user_data['current_data_index']
    data_list = context.user_data['data_list']
    
    if index >= len(data_list):
        # Якщо індекс вийшов за межі, завершуємо цикл
        return await dpia_minimization_finished(message, context)

    current_data_item = data_list[index]
    
    keyboard = [
        [
            InlineKeyboardButton("✅ Так", callback_data="min_yes"),
            InlineKeyboardButton("❌ Ні", callback_data="min_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_to_send = (
        f"**Розділ 4: Мінімізація ({index + 1}/{len(data_list)})**\n\n"
        f"**Пункт:** `{html.escape(current_data_item)}`\n"
        "Він вам *справді* потрібен?"
    )

    # Використовуємо 'message.reply_text'
    await message.reply_text(
        message_to_send,
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    return DPIA_Q_MINIMIZATION_REASON

async def dpia_q_minimization_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обробляє відповідь 'Так'/'Ні' (CallbackQuery) і питає про причину, якщо 'Так'."""
    query = update.callback_query
    await query.answer()
    
    index = context.user_data['current_data_index']
    current_data_item = context.user_data['data_list'][index]
    
    if query.data == "min_yes":
        context.user_data['minimization_data'].append({
            "item": current_data_item,
            "needed": True,
            "reason": "" 
        })
        await query.edit_message_text(
            f"✅ **Так** для `{html.escape(current_data_item)}`.\n\nНавіщо? (1 речення, напр., 'Для ідентифікації та відповідей')",
            parse_mode=ParseMode.MARKDOWN
        )
        return DPIA_Q_MINIMIZATION_STATUS
        
    elif query.data == "min_no":
        context.user_data['minimization_data'].append({
            "item": current_data_item,
            "needed": False,
            "reason": "Відмовлено (мінімізовано)"
        })
        await query.edit_message_text(
            f"❌ **Ні** для `{html.escape(current_data_item)}`. Цей пункт не буде включено у звіт.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        context.user_data['current_data_index'] += 1
        return await dpia_ask_minimization_status(query.message, context)

async def dpia_q_minimization_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отримує текстову причину для відповіді 'Так'."""
    reason = update.message.text
    
    if context.user_data['minimization_data']:
        # Додаємо причину до останнього доданого ('Так') пункту
        context.user_data['minimization_data'][-1]['reason'] = reason
    
    context.user_data['current_data_index'] += 1
    return await dpia_ask_minimization_status(update.message, context)

async def dpia_minimization_finished(message: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Викликається, коли цикл мінімізації завершено."""
    
    total = len(context.user_data['data_list'])
    needed = sum(1 for item in context.user_data['minimization_data'] if item['needed'])
    rejected = total - needed
    
    await message.reply_text(
        f"**Розділ 4 завершено.**\n"
        f"Висновок: Ви залишили {needed} з {total} пунктів даних (відмовилися від {rejected}).\n\n"
        "Це і є мінімізація!",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await message.reply_text(
        "**Розділ 5: Строки Зберігання**\n"
        "Як довго ви плануєте зберігати дані (ті, що залишилися)?\n\n"
        "(Напр., 'Доки студент не видалить акаунт', '6 місяців після випуску')",
        parse_mode=ParseMode.MARKDOWN
    )
    return DPIA_Q_RETENTION_MECHANISM

async def dpia_q_retention_mechanism(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['retention_period'] = update.message.text
    await update.message.reply_text(
        "Який у вас план/механізм видалення цих даних?\n\n"
        "(Напр., 'Автоматичний Cron-скрипт', 'Ручне видалення', 'Команда /deleteme')"
    )
    return DPIA_Q_STORAGE

async def dpia_q_storage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['retention_mechanism'] = update.message.text
    await update.message.reply_text(
        "**Розділ 6: Зберігання та Ризики**\n"
        "Де технічно будуть зберігатися дані?\n\n"
        "(Напр., 'Google Sheets', 'Firebase', 'Сервер Heroku + Postgres')",
        parse_mode=ParseMode.MARKDOWN
    )
    return DPIA_Q_RISK

async def dpia_q_risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['storage'] = update.message.text
    await update.message.reply_text(
        "Який головний ризик, пов'язаний з цим зберіганням?\n\n"
        "(Напр., 'Витік даних через публічне посилання Google Sheets', 'Витік .env файлу')"
    )
    return DPIA_Q_MITIGATION

async def dpia_q_mitigation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['risk'] = update.message.text
    await update.message.reply_text(
        "Як ви мінімізуєте цей ризик?\n\n"
        "(Напр., '2FA на акаунті, обмежений доступ', 'Використання .env та .gitignore')"
    )
    return DPIA_GENERATE

async def dpia_generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Збирає останню відповідь і генерує PDF для DPIA (у вигляді таблиці)."""
    context.user_data['mitigation'] = update.message.text
    user_id = update.effective_user.id
    logger.info(f"User {user_id}: генерація PDF DPIA (у вигляді таблиці).")

    generating_msg = await update.message.reply_text(
        "Дякую! Аудит завершено. Всі 6 розділів заповнені.\n\n"
        "Генерую ваш `1_dpie_lite_filled.pdf` у вигляді таблиці...\n"
        "(Це може зайняти 10-15 секунд)"
    )

    data = context.user_data
    
    def get_data(key, default='[Не вказано]'):
        return html.escape(data.get(key, default))

    table_rows = []
    
    table_rows.append(f"| Назва проєкту: | {get_data('project_name')} |")
    table_rows.append(f"| Керівник/Розробник: | {get_data('team')} |")
    table_rows.append(f"| Мета: | {get_data('goal')} |")
    
    minimization_data = data.get('minimization_data', [])
    if not minimization_data:
        table_rows.append("| Дані: | [Не вказано] |")
    else:
        for i, item in enumerate(minimization_data):
            data_name = f"Дані (пункт {i+1}):"
            item_name = html.escape(item['item'])
            item_reason = html.escape(item['reason'])
            
            if item['needed']:
                data_value = f"{item_name} (✅ **Навіщо:** {item_reason})"
            else:
                data_value = f"~~{item_name}~~ (❌ **Відмовлено**)"
            
            table_rows.append(f"| {data_name} | {data_value} |")

    table_rows.append(f"| Строк Зберігання: | {get_data('retention_period')} |")
    table_rows.append(f"| Механізм Видалення: | {get_data('retention_mechanism')} |")
    table_rows.append(f"| Місце Зберігання: | {get_data('storage')} |")
    table_rows.append(f"| Головний Ризик: | {get_data('risk')} |")
    table_rows.append(f"| Мінімізація Ризику: | {get_data('mitigation')} |")

    table_header = "| Питання | Відповідь |\n| :--- | :--- |\n"
    dpia_table_string = table_header + "\n".join(table_rows)

    data_dict = {
        'project_name': get_data('project_name'),
        'date': date.today().strftime("%d.%m.%Y"),
        'dpia_table': dpia_table_string
    }

    try:
        # Для DPIA ми також використовуємо Markdown-таблицю
        filled_markdown = templates.DPIA_TEMPLATE.format(**data_dict)
        
        pdf_file_path = create_pdf_from_markdown(
            content=filled_markdown,
            is_html=False, # Вказуємо, що це Markdown
            output_filename=f"dpia_{user_id}.pdf"
        )
        
        await update.message.reply_document(document=open(pdf_file_path, 'rb'))
        await update.message.reply_text(
            "Ваш DPIA Lite готовий (у вигляді таблиці).\n\n"
            "**Відповідно до нашої політики, я негайно видалив усі ваші відповіді (про назву проєкту, дані, ризики тощо) зі своєї тимчасової пам'яті.**\n\n"
            "Натисніть /start, щоб почати знову.",
            parse_mode=ParseMode.MARKDOWN
        )
        clear_temp_file(pdf_file_path)

    except Exception as e:
        logger.error(f"PDF DPIA generation failed for user {user_id}: {e}", exc_info=True)
        await update.message.reply_text(f"Під час генерації PDF сталася помилка: {e}")
    
    finally:
        try:
            await context.bot.delete_message(chat_id=generating_msg.chat_id, message_id=generating_msg.message_id)
        except Exception as e:
            logger.warning(f"Не вдалося видалити 'Генерую...' {e}")
            
        logger.info(f"Очищення даних для user {user_id}. Причина: Генерація DPIA завершена.")
        clear_user_data(context)
        return ConversationHandler.END


# === 4. Логіка "Чек-ліста" (3/3) - v2.8 Skip Logic ===

async def delete_main_message(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Допоміжна функція для чистого видалення "Головного" повідомлення."""
    message_id = context.user_data.pop('main_message_id', None)
    chat_id = context._chat_id
    
    if message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.info(f"Видалено 'Головне' повідомлення {message_id}")
        except BadRequest as e:
            logger.warning(f"Не вдалося видалити 'Головне' повідомлення {message_id}: {e}")
    else:
        logger.info("Немає 'Головного' повідомлення для видалення.")

async def edit_main_message(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup: InlineKeyboardMarkup = None, new_message: bool = False) -> None:
    """Допоміжна функція для редагування/надсилання "Головного" повідомлення."""
    message_id = context.user_data.get('main_message_id')
    chat_id = context._chat_id
    
    if new_message and message_id:
        await delete_main_message(context)
        message_id = None

    try:
        if not message_id or new_message:
            sent_message = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            context.user_data['main_message_id'] = sent_message.message_id
        else:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.info("Повідомлення не змінено, пропуск редагування.")
        elif "message to edit not found" in str(e):
             logger.warning(f"Не вдалося знайти повідомлення {message_id} для редагування. Надсилаю нове.")
             await edit_main_message(context, text, reply_markup, new_message=True)
        else:
            logger.error(f"Помилка під час редагування/надсилання повідомлення: {e}", exc_info=True)
            if message_id and not new_message:
                await edit_main_message(context, text, reply_markup, new_message=True)
    except Exception as e:
        logger.error(f"Невідома помилка в edit_main_message: {e}", exc_info=True)

def get_checklist_status_keyboard() -> InlineKeyboardMarkup:
    """Повертає клавіатуру Так/Ні для Чек-ліста."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Виконано", callback_data="cl_yes"),
            InlineKeyboardButton("❌ Не виконано", callback_data="cl_no"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- (НОВЕ v2.8) Клавіатура для пропуску нотатки ---
def get_skip_note_keyboard() -> InlineKeyboardMarkup:
    """Повертає клавіатуру 'Пропустити нотатку'."""
    keyboard = [
        [
            InlineKeyboardButton("➡️ Пропустити нотатку", callback_data="cl_skip_note"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- (ОНОВЛЕНО v2.8) Функції для "Безшовного" UX ---

def get_status_text_md(status: str) -> str:
    """(v2.8) Повертає текстовий статус (для Telegram UI)."""
    if status == "yes":
        return "✅ **Виконано**"
    elif status == "no":
        return "❌ **Не виконано**"
    else:
        return "" 

def get_note_text_md(note: str) -> str:
    """(v2.8) Повертає відформатовану нотатку (без ✅)."""
    if not note:
        return ""
    if note == "*Пропущено*":
        return "Нотатка: *Пропущено*"
    return f"Нотатка: `{html.escape(note)}`"

async def delete_user_note(update: Update) -> None:
    """Видаляє повідомлення користувача (його нотатку), щоб чат був чистим."""
    try:
        await update.message.delete()
    except BadRequest as e:
        logger.warning(f"Не вдалося видалити нотатку користувача: {e}")

# Функція-хелпер для заповнення шаблонів v2.8
def get_checklist_template_data(cl_data: dict) -> dict:
    """(v2.8) Готує словник для заповнення шаблонів v2.8."""
    data = {
        'c1_s1_status': get_status_text_md(cl_data.get('c1_s1_status', '')),
        'c1_s1_note': get_note_text_md(cl_data.get('c1_s1_note', '')),
        'c1_s2_status': get_status_text_md(cl_data.get('c1_s2_status', '')),
        'c1_s2_note': get_note_text_md(cl_data.get('c1_s2_note', '')),
        'c1_s3_status': get_status_text_md(cl_data.get('c1_s3_status', '')),
        'c1_s3_note': get_note_text_md(cl_data.get('c1_s3_note', '')),
        
        'c2_s1_status': get_status_text_md(cl_data.get('c2_s1_status', '')),
        'c2_s1_note': get_note_text_md(cl_data.get('c2_s1_note', '')),
        'c2_s2_status': get_status_text_md(cl_data.get('c2_s2_status', '')),
        'c2_s2_note': get_note_text_md(cl_data.get('c2_s2_note', '')),
        'c2_s3_status': get_status_text_md(cl_data.get('c2_s3_status', '')),
        'c2_s3_note': get_note_text_md(cl_data.get('c2_s3_note', '')),

        'c3_s1_status': get_status_text_md(cl_data.get('c3_s1_status', '')),
        'c3_s1_note': get_note_text_md(cl_data.get('c3_s1_note', '')),
        'c3_s2_status': get_status_text_md(cl_data.get('c3_s2_status', '')),
        'c3_s2_note': get_note_text_md(cl_data.get('c3_s2_note', '')),
        'c3_s3_status': get_status_text_md(cl_data.get('c3_s3_status', '')),
        'c3_s3_note': get_note_text_md(cl_data.get('c3_s3_note', '')),
    }
    return data

async def start_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """(C0) Починає "безшовну" розмову про Чек-ліст."""
    clear_user_data(context)
    logger.info(f"User {update.effective_user.id} почав 'Чек-ліст v2.8'.")
    context.user_data['cl'] = {} # 'cl' для стислості
    
    try:
        # Видаляємо повідомлення з кнопкою "Пройти Чек-ліст"
        await update.message.delete() 
    except Exception as e:
        logger.warning(f"Не вдалося видалити Kнопку 'Пройти Чек-ліст': {e}")
    
    await update.message.reply_text(
        "Гаразд. Проведемо *детальний* Чек-ліст Безпеки (9 пунктів).\n"
        "Натисніть /cancel у будь-який момент, щоб скасувати.", # (ВИПРАВЛЕНО v2.8) - 'L/'
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Починаємо з C1.S1
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C1_S1_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard(), new_message=True)
    
    return C1_S1_NOTE

# === (НОВЕ v2.8) Рефакторинг з логікою "Skip" ===

# --- Категорія 1 ---

async def checklist_c1_s1_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C1.S1 Status -> C1.S1 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c1_s1_status'] = "yes" if query.data == "cl_yes" else "no"
    
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C1_S1_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return C1_S2_STATUS # Наступний стан очікує або Text, або Skip

async def _ask_c1_s2_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    """Hелпер: ставить питання C1.S2"""
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C1_S2_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard())
    return C1_S2_NOTE

async def checklist_c1_s2_status_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c1_s1_note'] = update.message.text
    await delete_user_note(update)
    return await _ask_c1_s2_status(context)

async def checklist_c1_s2_status_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c1_s1_note'] = "*Пропущено*"
    return await _ask_c1_s2_status(context)

async def checklist_c1_s2_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C1.S2 Status -> C1.S2 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c1_s2_status'] = "yes" if query.data == "cl_yes" else "no"
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C1_S2_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return C1_S3_STATUS

async def _ask_c1_s3_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C1_S3_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard())
    return C1_S3_NOTE

async def checklist_c1_s3_status_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c1_s2_note'] = update.message.text
    await delete_user_note(update)
    return await _ask_c1_s3_status(context)

async def checklist_c1_s3_status_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c1_s2_note'] = "*Пропущено*"
    return await _ask_c1_s3_status(context)

async def checklist_c1_s3_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C1.S3 Status -> C1.S3 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c1_s3_status'] = "yes" if query.data == "cl_yes" else "no"
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C1_S3_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return C2_S1_STATUS

# --- Категорія 2 ---

async def _ask_c2_s1_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C2_S1_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard())
    return C2_S1_NOTE

async def checklist_c2_s1_status_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c1_s3_note'] = update.message.text
    await delete_user_note(update)
    return await _ask_c2_s1_status(context)

async def checklist_c2_s1_status_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c1_s3_note'] = "*Пропущено*"
    return await _ask_c2_s1_status(context)

async def checklist_c2_s1_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C2.S1 Status -> C2.S1 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c2_s1_status'] = "yes" if query.data == "cl_yes" else "no"
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C2_S1_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return C2_S2_STATUS

async def _ask_c2_s2_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C2_S2_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard())
    return C2_S2_NOTE

async def checklist_c2_s2_status_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c2_s1_note'] = update.message.text
    await delete_user_note(update)
    return await _ask_c2_s2_status(context)

async def checklist_c2_s2_status_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c2_s1_note'] = "*Пропущено*"
    return await _ask_c2_s2_status(context)

async def checklist_c2_s2_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C2.S2 Status -> C2.S2 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c2_s2_status'] = "yes" if query.data == "cl_yes" else "no"
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C2_S2_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return C2_S3_STATUS

async def _ask_c2_s3_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C2_S3_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard())
    return C2_S3_NOTE

async def checklist_c2_s3_status_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c2_s2_note'] = update.message.text
    await delete_user_note(update)
    return await _ask_c2_s3_status(context)

async def checklist_c2_s3_status_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c2_s2_note'] = "*Пропущено*"
    return await _ask_c2_s3_status(context)

async def checklist_c2_s3_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C2.S3 Status -> C2.S3 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c2_s3_status'] = "yes" if query.data == "cl_yes" else "no"
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C2_S3_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return C3_S1_STATUS

# --- Категорія 3 ---

async def _ask_c3_s1_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C3_S1_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard())
    return C3_S1_NOTE

async def checklist_c3_s1_status_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c2_s3_note'] = update.message.text
    await delete_user_note(update)
    return await _ask_c3_s1_status(context)

async def checklist_c3_s1_status_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c2_s3_note'] = "*Пропущено*"
    return await _ask_c3_s1_status(context)

async def checklist_c3_s1_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C3.S1 Status -> C3.S1 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c3_s1_status'] = "yes" if query.data == "cl_yes" else "no"
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C3_S1_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return C3_S2_STATUS

async def _ask_c3_s2_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C3_S2_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard())
    return C3_S2_NOTE

async def checklist_c3_s2_status_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c3_s1_note'] = update.message.text
    await delete_user_note(update)
    return await _ask_c3_s2_status(context)

async def checklist_c3_s2_status_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c3_s1_note'] = "*Пропущено*"
    return await _ask_c3_s2_status(context)

async def checklist_c3_s2_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C3.S2 Status -> C3.S2 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c3_s2_status'] = "yes" if query.data == "cl_yes" else "no"
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C3_S2_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return C3_S3_STATUS

async def _ask_c3_s3_status(context: ContextTypes.DEFAULT_TYPE) -> int:
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C3_S3_STATUS.format(**template_data)
    await edit_main_message(context, text, get_checklist_status_keyboard())
    return C3_S3_NOTE

async def checklist_c3_s3_status_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c3_s2_note'] = update.message.text
    await delete_user_note(update)
    return await _ask_c3_s3_status(context)

async def checklist_c3_s3_status_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c3_s2_note'] = "*Пропущено*"
    return await _ask_c3_s3_status(context)

async def checklist_c3_s3_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """C3.S3 Status -> C3.S3 Note?"""
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c3_s3_status'] = "yes" if query.data == "cl_yes" else "no"
    template_data = get_checklist_template_data(context.user_data['cl'])
    text = templates.CHECKLIST_C3_S3_NOTE.format(**template_data)
    await edit_main_message(context, text, get_skip_note_keyboard())
    return CHECKLIST_GENERATE

# --- Генерація ---

async def checklist_generate_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['cl']['c3_s3_note'] = update.message.text
    await delete_user_note(update)
    return await checklist_generate(context)

async def checklist_generate_from_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['cl']['c3_s3_note'] = "*Пропущено*"
    return await checklist_generate(context)

async def checklist_generate(context: ContextTypes.DEFAULT_TYPE) -> int:
    """(Generate PDF) v2.8 - Гібридна (H3+Table) + Текст"""
    user_id = context._user_id
    logger.info(f"User {user_id}: генерація PDF Чек-ліста v2.8 (Markdown H3+Table).")
    
    await delete_main_message(context)
    
    generating_msg = await context.bot.send_message(
        chat_id=context._chat_id,
        text="Дякую! Аудит 9/9 завершено. Генерую ваш Чек-ліст PDF..."
    )

    data = context.user_data['cl']
    
    # --- (ОНОВЛЕНО v2.8) Функції для Markdown-таблиці (без ❌) ---
    def get_status_md_text(status_key: str) -> str:
        """(v2.8) Повертає ЧИСТИЙ текстовий статус (для PDF)."""
        status = data.get(status_key)
        if status == "yes":
            return "Виконано"
        elif status == "no":
            return "Не виконано"
        else:
            return "Не заповнено"

    def get_note_md_text_pdf(note_key: str) -> str:
        """(v2.8) Повертає екрановану нотатку (для PDF)."""
        note = data.get(note_key, "*Не заповнено*")
        if note == "*Пропущено*":
            return note
        
        # Екрануємо HTML та замінюємо нові рядки на <br> (працює в Markdown->PDF)
        note_safe = html.escape(note)
        return note_safe.replace("\n", "<br>") 

    # --- (v2.7) Генерація гібридного Markdown (H3 + Таблиця) ---
    
    table_header = "| Пункт | Статус | Ваші Нотатки (для себе) |\n| :--- | :--- | :--- |\n"
    
    # Категорія 1
    cat_1_header = "### Категорія 1: Контроль Доступу\n\n"
    cat_1_rows = [
        f"| 1.1. 2FA (Двофакторна Автентифікація) | {get_status_md_text('c1_s1_status')} | {get_note_md_text_pdf('c1_s1_note')} |",
        f"| 1.2. Принцип 'Найменших привілеїв' | {get_status_md_text('c1_s2_status')} | {get_note_md_text_pdf('c1_s2_note')} |",
        f"| 1.3. БЕЗ ПУБЛІЧНИХ ПОСИЛАНЬ | {get_status_md_text('c1_s3_status')} | {get_note_md_text_pdf('c1_s3_note')} |",
    ]
    cat_1_table = cat_1_header + table_header + "\n".join(cat_1_rows)

    # Категорія 2
    cat_2_header = "\n\n### Категорія 2: Права Користувачів\n\n"
    cat_2_rows = [
        f"| 2.1. Публічна Політика | {get_status_md_text('c2_s1_status')} | {get_note_md_text_pdf('c2_s1_note')} |",
        f"| 2.2. Механізм Видалення (Ст. 8) | {get_status_md_text('c2_s2_status')} | {get_note_md_text_pdf('c2_s2_note')} |",
        f"| 2.3. Контакт для скарг | {get_status_md_text('c2_s3_status')} | {get_note_md_text_pdf('c2_s3_note')} |",
    ]
    cat_2_table = cat_2_header + table_header + "\n".join(cat_2_rows)

    # Категорія 3
    cat_3_header = "\n\n### Категорія 3: Технічна Гігієна\n\n"
    cat_3_rows = [
        f"| 3.1. Безпека Токенів | {get_status_md_text('c3_s1_status')} | {get_note_md_text_pdf('c3_s1_note')} |",
        f"| 3.2. Планування Строків (Retention) | {get_status_md_text('c3_s2_status')} | {get_note_md_text_pdf('c3_s2_note')} |",
        f"| 3.3. Шифрування (Якщо є паролі) | {get_status_md_text('c3_s3_status')} | {get_note_md_text_pdf('c3_s3_note')} |",
    ]
    cat_3_table = cat_3_header + table_header + "\n".join(cat_3_rows)

    # Поєднуємо все в один Markdown-рядок
    checklist_content = f"{cat_1_table}{cat_2_table}{cat_3_table}"

    data_dict = {
        'date': date.today().strftime("%d.%m.%Y"),
        'checklist_content': checklist_content # Передаємо Markdown
    }

    try:
        # Для Чек-ліста ми передаємо Markdown (H3+Table)
        filled_markdown = templates.CHECKLIST_TEMPLATE_PDF.format(**data_dict)
        
        pdf_file_path = create_pdf_from_markdown(
            content=filled_markdown,
            is_html=False, # (v2.8) Це 100% Markdown
            output_filename=f"checklist_{user_id}.pdf"
        )
        
        await context.bot.delete_message(chat_id=generating_msg.chat_id, message_id=generating_msg.message_id)

        await context.bot.send_document(chat_id=context._chat_id, document=open(pdf_file_path, 'rb'))
        await context.bot.send_message(
            chat_id=context._chat_id,
            text="Ваш детальний Чек-ліст готовий (v2.8). Я видалив усі ваші відповіді зі своєї пам'яті.\n\n"
                 "Натисніть /start, щоб почати знову."
        )
        clear_temp_file(pdf_file_path)

    except Exception as e:
        logger.error(f"PDF Checklist generation failed for user {user_id}: {e}", exc_info=True)
        try:
            await context.bot.delete_message(chat_id=generating_msg.chat_id, message_id=generating_msg.message_id)
        except Exception:
            pass
            
        await context.bot.send_message(chat_id=context._chat_id, text=f"Під час генерації PDF сталася помилка: {e}")
    
    finally:
        logger.info(f"Очищення даних для user {user_id}. Причина: Генерація Чек-ліста завершена.")
        clear_user_data(context)
        return ConversationHandler.END


# === 5. Налаштування та Запуск Бота ===

def main() -> None:
    """Запускає бота."""
    application = Application.builder().token(BOT_TOKEN).build()

    policy_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📄 Сгенерувати Політику Конфіденційності$"), start_policy)],
        states={
            POLICY_Q_CONTACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_q_contact)],
            POLICY_Q_DATA_COLLECTED: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_q_data_collected)],
            POLICY_Q_DATA_STORAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_q_data_storage)],
            POLICY_Q_DELETE_MECHANISM: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_q_delete_mechanism)],
            POLICY_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, policy_generate)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    dpia_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📝 Пройти Оцінку Ризиків \(DPIA Lite\)$"), start_dpia)],
        states={
            DPIA_Q_TEAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_team)],
            DPIA_Q_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_goal)],
            DPIA_Q_DATA_LIST: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_data_list)],
            DPIA_Q_MINIMIZATION_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_minimization_start)],
            DPIA_Q_MINIMIZATION_REASON: [CallbackQueryHandler(dpia_q_minimization_reason)],
            DPIA_Q_MINIMIZATION_STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_minimization_status)],
            DPIA_Q_RETENTION_MECHANISM: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_retention_mechanism)],
            DPIA_Q_STORAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_storage)],
            DPIA_Q_RISK: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_risk)],
            DPIA_Q_MITIGATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_q_mitigation)],
            DPIA_GENERATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, dpia_generate)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # (НОВЕ v2.8) Повна логіка для 'skip note'
    checklist_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^✅ Пройти Чек-ліст Безпеки$"), start_checklist)],
        states={
            # Cat 1
            C1_S1_NOTE: [CallbackQueryHandler(checklist_c1_s1_note, pattern="^cl_(yes|no)$")],
            C1_S2_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_c1_s2_status_from_text),
                CallbackQueryHandler(checklist_c1_s2_status_from_skip, pattern="^cl_skip_note$")
            ],
            C1_S2_NOTE: [CallbackQueryHandler(checklist_c1_s2_note, pattern="^cl_(yes|no)$")],
            C1_S3_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_c1_s3_status_from_text),
                CallbackQueryHandler(checklist_c1_s3_status_from_skip, pattern="^cl_skip_note$")
            ],
            C1_S3_NOTE: [CallbackQueryHandler(checklist_c1_s3_note, pattern="^cl_(yes|no)$")],
            
            # Cat 2
            C2_S1_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_c2_s1_status_from_text),
                CallbackQueryHandler(checklist_c2_s1_status_from_skip, pattern="^cl_skip_note$")
            ],
            C2_S1_NOTE: [CallbackQueryHandler(checklist_c2_s1_note, pattern="^cl_(yes|no)$")],
            C2_S2_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_c2_s2_status_from_text),
                CallbackQueryHandler(checklist_c2_s2_status_from_skip, pattern="^cl_skip_note$")
            ],
            C2_S2_NOTE: [CallbackQueryHandler(checklist_c2_s2_note, pattern="^cl_(yes|no)$")],
            C2_S3_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_c2_s3_status_from_text),
                CallbackQueryHandler(checklist_c2_s3_status_from_skip, pattern="^cl_skip_note$")
            ],
            C2_S3_NOTE: [CallbackQueryHandler(checklist_c2_s3_note, pattern="^cl_(yes|no)$")],
            
            # Cat 3
            C3_S1_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_c3_s1_status_from_text),
                CallbackQueryHandler(checklist_c3_s1_status_from_skip, pattern="^cl_skip_note$")
            ],
            C3_S1_NOTE: [CallbackQueryHandler(checklist_c3_s1_note, pattern="^cl_(yes|no)$")],
            C3_S2_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_c3_s2_status_from_text),
                CallbackQueryHandler(checklist_c3_s2_status_from_skip, pattern="^cl_skip_note$")
            ],
            C3_S2_NOTE: [CallbackQueryHandler(checklist_c3_s2_note, pattern="^cl_(yes|no)$")],
            C3_S3_STATUS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_c3_s3_status_from_text),
                CallbackQueryHandler(checklist_c3_s3_status_from_skip, pattern="^cl_skip_note$")
            ],
            C3_S3_NOTE: [CallbackQueryHandler(checklist_c3_s3_note, pattern="^cl_(yes|no)$")],

            # Generate
            CHECKLIST_GENERATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, checklist_generate_from_text),
                CallbackQueryHandler(checklist_generate_from_skip, pattern="^cl_skip_note$")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(policy_conv_handler)
    application.add_handler(dpia_conv_handler)
    application.add_handler(checklist_conv_handler)
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("privacy", show_privacy))
    application.add_handler(CommandHandler("help", show_help))
    # Глобальний fallback 'cancel' (ловить /cancel будь-де)
    application.add_handler(CommandHandler("cancel", cancel)) 

    logger.info("Бот запускається...")
    application.run_polling()

if __name__ == "__main__":
    main()