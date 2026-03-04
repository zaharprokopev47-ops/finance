import asyncio
import logging
import sqlite3
import re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ✅ ЗАМЕНИТЕ НА ВАШ ТОКЕН!
BOT_TOKEN = "8435391945:AAFFuc8m7kL6k1cQwxCqPv5mRz5CcZlRjOQ"

# Категории операций
CATEGORIES = {
    'еда': ['еда', 'продукты', 'магазин', 'супермаркет', 'ресторан', 'кафе', 'обед', 'ужин', 'завтрак', 'кофе', 'столовая'],
    'транспорт': ['транспорт', 'такси', 'метро', 'автобус', 'бензин', 'заправка', 'парковка', 'штраф'],
    'развлечения': ['кино', 'концерт', 'игры', 'хобби', 'отдых', 'театр', 'выставка', 'клуб'],
    'здоровье': ['врач', 'аптека', 'медицина', 'больница', 'стоматолог', 'анализы', 'лекарства'],
    'коммуналка': ['коммуналка', 'квартплата', 'электричество', 'вода', 'интернет', 'телефон', 'тв'],
    'одежда': ['одежда', 'обувь', 'магазин одежды', 'белье', 'аксессуары'],
    'образование': ['курсы', 'книги', 'обучение', 'репетитор', 'учеба'],
    'подарки': ['подарок', 'день рождения', 'свадьба', 'юбилей'],
    'доходы': ['зарплата', 'аванс', 'премия', 'доход', 'продажа', 'инвестиции', 'дивиденды']
}

# Создаем клавиатуру с кнопками
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📅 Сегодня")],
            [KeyboardButton(text="📈 Месяц"), KeyboardButton(text="📋 Детали")],
            [KeyboardButton(text="💰 Бюджет"), KeyboardButton(text="🎯 Цели")],
            [KeyboardButton(text="ℹ️ Помощь"), KeyboardButton(text="❌ Скрыть кнопки")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    # Таблица транзакций
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            category TEXT NOT NULL DEFAULT 'другое',
            type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица бюджетов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            period TEXT DEFAULT 'monthly',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица целей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            current_amount REAL DEFAULT 0,
            deadline DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    logger.info("✅ База данных инициализирована")

def detect_category(description):
    """Автоматическое определение категории по описанию"""
    description_lower = description.lower()
    
    for category, keywords in CATEGORIES.items():
        if any(keyword in description_lower for keyword in keywords):
            return category
    
    return 'другое'

def add_transaction(user_id, amount, description, transaction_type, category):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, description, category, type)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, amount, description, category, transaction_type))
    conn.commit()
    conn.close()

def set_budget(user_id, category, amount):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    # Удаляем старый бюджет для этой категории
    cursor.execute('''
        DELETE FROM budgets WHERE user_id = ? AND category = ?
    ''', (user_id, category))
    
    # Добавляем новый бюджет
    cursor.execute('''
        INSERT INTO budgets (user_id, category, amount)
        VALUES (?, ?, ?)
    ''', (user_id, category, amount))
    
    conn.commit()
    conn.close()

def get_budgets(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT category, amount FROM budgets WHERE user_id = ?
    ''', (user_id,))
    
    budgets = dict(cursor.fetchall())
    conn.close()
    return budgets

def get_budget_progress(user_id, days=30):
    """Прогресс по бюджетам за период"""
    try:
        conn = sqlite3.connect('finance.db')
        cursor = conn.cursor()
        
        start_date = datetime.now() - timedelta(days=days)
        
        # Получаем расходы по категориям
        cursor.execute('''
            SELECT category, SUM(amount) FROM transactions 
            WHERE user_id = ? AND type = 'expense' AND created_at >= ?
            GROUP BY category
        ''', (user_id, start_date))
        
        expenses = dict(cursor.fetchall())
        
        # Получаем бюджеты
        budgets = get_budgets(user_id)
        
        conn.close()
        
        # Считаем прогресс
        progress = {}
        for category, budget_amount in budgets.items():
            spent = expenses.get(category, 0)
            progress[category] = {
                'budget': budget_amount,
                'spent': spent,
                'remaining': budget_amount - spent,
                'percentage': (spent / budget_amount * 100) if budget_amount > 0 else 0
            }
        
        return progress
    except sqlite3.OperationalError as e:
        logger.error(f"Ошибка базы данных: {e}")
        return {}

def add_goal(user_id, name, target_amount, deadline=None):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO goals (user_id, name, target_amount, deadline)
        VALUES (?, ?, ?, ?)
    ''', (user_id, name, target_amount, deadline))
    
    conn.commit()
    conn.close()

def update_goal_progress(user_id, goal_name, amount):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE goals SET current_amount = current_amount + ? 
        WHERE user_id = ? AND name = ?
    ''', (amount, user_id, goal_name))
    
    conn.commit()
    conn.close()

def get_goals(user_id):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT name, target_amount, current_amount, deadline FROM goals 
        WHERE user_id = ? ORDER BY created_at DESC
    ''', (user_id,))
    
    goals = cursor.fetchall()
    conn.close()
    return goals

def get_statistics(user_id, days=None):
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    query = "SELECT type, SUM(amount) FROM transactions WHERE user_id = ?"
    params = [user_id]
    
    if days:
        start_date = datetime.now() - timedelta(days=days)
        query += " AND created_at >= ?"
        params.append(start_date)
    
    query += " GROUP BY type"
    
    cursor.execute(query, params)
    results = dict(cursor.fetchall())
    conn.close()
    
    return {
        'income': results.get('income', 0),
        'expense': results.get('expense', 0)
    }

def get_detailed_stats(user_id, days=30):
    try:
        conn = sqlite3.connect('finance.db')
        cursor = conn.cursor()
        
        start_date = datetime.now() - timedelta(days=days)
        
        # Расходы по категориям
        cursor.execute('''
            SELECT category, SUM(amount) FROM transactions 
            WHERE user_id = ? AND type = 'expense' AND created_at >= ?
            GROUP BY category 
            ORDER BY SUM(amount) DESC
        ''', (user_id, start_date))
        expenses_by_category = cursor.fetchall()
        
        # Доходы по категориям
        cursor.execute('''
            SELECT category, SUM(amount) FROM transactions 
            WHERE user_id = ? AND type = 'income' AND created_at >= ?
            GROUP BY category 
            ORDER BY SUM(amount) DESC
        ''', (user_id, start_date))
        incomes_by_category = cursor.fetchall()
        
        conn.close()
        
        return {
            'expenses_by_category': expenses_by_category,
            'incomes_by_category': incomes_by_category
        }
    except sqlite3.OperationalError as e:
        logger.error(f"Ошибка базы данных: {e}")
        return {'expenses_by_category': [], 'incomes_by_category': []}

def get_today_stats(user_id):
    """Статистика за сегодня"""
    conn = sqlite3.connect('finance.db')
    cursor = conn.cursor()
    
    today = datetime.now().date()
    
    cursor.execute('''
        SELECT type, SUM(amount) FROM transactions 
        WHERE user_id = ? AND DATE(created_at) = ?
        GROUP BY type
    ''', (user_id, today))
    
    results = dict(cursor.fetchall())
    conn.close()
    
    return {
        'income': results.get('income', 0),
        'expense': results.get('expense', 0)
    }

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Инициализируем базу при запуске
init_db()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "💰 Привет! Я умный финансовый бот!\n\n"
        "💡 **Новые возможности:**\n"
        "• 📊 Автоматические категории\n"
        "• 💰 Бюджеты по категориям\n"
        "• 🎯 Цели и накопления\n\n"
        "📱 Используйте кнопки для быстрого доступа!",
        reply_markup=get_main_keyboard()
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    help_text = """
📝 **Новые команды:**

💸 **Бюджетирование:**
/budget еда 10000 - установить бюджет на еду
/budgets - посмотреть все бюджеты

🎯 **Цели:**
/goal машина 1000000 - создать цель
/goals - мои цели
/goal добавить машина 50000 - добавить к цели

📊 **Категории:**
• Автоматически определяются из описания
• Доступные: еда, транспорт, развлечения, здоровье, коммуналка, одежда, образование, подарки

💡 Примеры:
+50000 зарплата
-500 еда
/budget транспорт 5000
/goal отпуск 50000
"""
    await message.answer(help_text, reply_markup=get_main_keyboard())

@dp.message(Command("keyboard"))
async def cmd_keyboard(message: types.Message):
    """Показать клавиатуру"""
    await message.answer("📱 Клавиатура активирована!", reply_markup=get_main_keyboard())

# Обработчики кнопок - ИСПРАВЛЕННЫЕ
@dp.message(F.text == "📊 Статистика")
async def handle_stats_button(message: Message):
    user_id = message.from_user.id
    stats = get_statistics(user_id, days=30)
    detailed_stats = get_detailed_stats(user_id, days=30)
    
    balance = stats['income'] - stats['expense']
    
    response = f"📊 **Статистика за месяц:**\n\n📥 Доходы: {stats['income']:,.2f} руб\n📤 Расходы: {stats['expense']:,.2f} руб\n💰 Баланс: {balance:,.2f} руб\n\n"
    
    if detailed_stats['expenses_by_category']:
        response += "📤 **Расходы по категориям:**\n"
        for category, amount in detailed_stats['expenses_by_category'][:5]:
            response += f"• {category}: {amount:,.0f} руб\n"
    
    await message.answer(response, reply_markup=get_main_keyboard())

@dp.message(F.text == "📅 Сегодня")
async def handle_today_button(message: Message):
    user_id = message.from_user.id
    stats = get_today_stats(user_id)
    
    balance = stats['income'] - stats['expense']
    
    response = (
        f"📅 **Статистика за сегодня:**\n\n"
        f"📥 Доходы: {stats['income']:,.2f} руб\n"
        f"📤 Расходы: {stats['expense']:,.2f} руб\n"
        f"💰 Баланс за день: {balance:,.2f} руб"
    )
    
    await message.answer(response, reply_markup=get_main_keyboard())

@dp.message(F.text == "📈 Месяц")
async def handle_month_button(message: Message):
    user_id = message.from_user.id
    stats = get_statistics(user_id, days=30)
    
    balance = stats['income'] - stats['expense']
    
    response = (
        f"📈 **Статистика за месяц (30 дней):**\n\n"
        f"📥 Доходы: {stats['income']:,.2f} руб\n"
        f"📤 Расходы: {stats['expense']:,.2f} руб\n"
        f"💰 Баланс: {balance:,.2f} руб\n\n"
        f"📊 Средний доход в день: {stats['income']/30:,.0f} руб\n"
        f"📉 Средний расход в день: {stats['expense']/30:,.0f} руб"
    )
    
    await message.answer(response, reply_markup=get_main_keyboard())

@dp.message(F.text == "📋 Детали")
async def handle_details_button(message: Message):
    user_id = message.from_user.id
    detailed_stats = get_detailed_stats(user_id, days=30)
    
    response = "📋 **Детальная статистика за 30 дней:**\n\n"
    
    if detailed_stats['incomes_by_category']:
        response += "📥 **Доходы по категориям:**\n"
        for category, amount in detailed_stats['incomes_by_category'][:5]:
            response += f"• {category}: {amount:,.0f} руб\n"
        response += "\n"
    
    if detailed_stats['expenses_by_category']:
        response += "📤 **Расходы по категориям:**\n"
        for category, amount in detailed_stats['expenses_by_category'][:5]:
            response += f"• {category}: {amount:,.0f} руб\n"
    
    if not detailed_stats['incomes_by_category'] and not detailed_stats['expenses_by_category']:
        response += "❌ Нет данных за последние 30 дней"
    
    await message.answer(response, reply_markup=get_main_keyboard())

@dp.message(F.text == "💰 Бюджет")
async def handle_budget_button(message: Message):
    user_id = message.from_user.id
    progress = get_budget_progress(user_id)
    
    if not progress:
        response = "❌ Бюджеты не установлены\n\n💡 Используйте: /budget еда 10000"
    else:
        response = "💰 **Прогресс по бюджетам:**\n\n"
        for category, data in progress.items():
            status = "✅" if data['percentage'] <= 80 else "⚠️" if data['percentage'] <= 100 else "❌"
            response += f"{status} {category}:\n"
            response += f"   📊 {data['spent']:,.0f} / {data['budget']:,.0f} руб ({data['percentage']:.1f}%)\n"
            response += f"   💰 Осталось: {data['remaining']:,.0f} руб\n\n"
    
    await message.answer(response, reply_markup=get_main_keyboard())

@dp.message(F.text == "🎯 Цели")
async def handle_goals_button(message: Message):
    user_id = message.from_user.id
    goals = get_goals(user_id)
    
    if not goals:
        response = "❌ Цели не установлены\n\n💡 Используйте: /goal машина 1000000"
    else:
        response = "🎯 **Мои цели:**\n\n"
        for name, target, current, deadline in goals:
            percentage = (current / target * 100) if target > 0 else 0
            response += f"🏆 {name}:\n"
            response += f"   📈 {current:,.0f} / {target:,.0f} руб ({percentage:.1f}%)\n"
            response += f"   💰 Осталось: {target - current:,.0f} руб\n"
            if deadline:
                response += f"   📅 До: {deadline}\n"
            response += "\n"
    
    await message.answer(response, reply_markup=get_main_keyboard())

@dp.message(F.text == "ℹ️ Помощь")
async def handle_help_button(message: Message):
    await cmd_help(message)

@dp.message(F.text == "❌ Скрыть кнопки")
async def handle_hide_button(message: Message):
    await message.answer(
        "❌ Клавиатура скрыта. Используйте /keyboard чтобы вернуть.",
        reply_markup=ReplyKeyboardRemove()
    )

# Команды бюджетирования
@dp.message(Command("budget"))
async def cmd_budget(message: Message):
    user_id = message.from_user.id
    args = message.text.split()[1:]
    
    if len(args) < 2:
        await message.answer("❌ Формат: /budget категория сумма\nПример: /budget еда 10000")
        return
    
    category = args[0].lower()
    try:
        amount = float(args[1])
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной")
            return
    except ValueError:
        await message.answer("❌ Неверная сумма")
        return
    
    set_budget(user_id, category, amount)
    await message.answer(f"✅ Бюджет установлен:\n{category}: {amount:,.0f} руб/месяц", reply_markup=get_main_keyboard())

@dp.message(Command("budgets"))
async def cmd_budgets(message: Message):
    await handle_budget_button(message)

# Команды целей
@dp.message(Command("goal"))
async def cmd_goal(message: Message):
    user_id = message.from_user.id
    args = message.text.split()[1:]
    
    if len(args) == 0:
        await message.answer("❌ Формат:\n• /goal название сумма - создать цель\n• /goal добавить название сумма - добавить к цели")
        return
    
    if args[0] == 'добавить' and len(args) >= 3:
        # Добавление к существующей цели
        goal_name = args[1]
        try:
            amount = float(args[2])
            update_goal_progress(user_id, goal_name, amount)
            await message.answer(f"✅ Добавлено {amount:,.0f} руб к цели '{goal_name}'", reply_markup=get_main_keyboard())
        except ValueError:
            await message.answer("❌ Неверная сумма")
    elif len(args) >= 2:
        # Создание новой цели
        goal_name = ' '.join(args[:-1])
        try:
            target_amount = float(args[-1])
            if target_amount <= 0:
                await message.answer("❌ Сумма должна быть положительной")
                return
            
            add_goal(user_id, goal_name, target_amount)
            await message.answer(f"✅ Цель создана:\n{goal_name}: {target_amount:,.0f} руб", reply_markup=get_main_keyboard())
        except ValueError:
            await message.answer("❌ Неверная сумма")
    else:
        await message.answer("❌ Неверный формат команды")

@dp.message(Command("goals"))
async def cmd_goals(message: Message):
    await handle_goals_button(message)

# Команды статистики (для совместимости)
@dp.message(Command("today"))
async def cmd_today(message: types.Message):
    await handle_today_button(message)

@dp.message(Command("month"))
async def cmd_month(message: types.Message):
    await handle_month_button(message)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    await handle_stats_button(message)

# Обработка транзакций с категориями
@dp.message()
async def handle_all_messages(message: Message):
    text = message.text.strip()
    user_id = message.from_user.id
    
    # Парсим сообщения вида "+50000 зарплата" или "-500 еда"
    match = re.match(r'^([+-]?\d+)\s+(.+)$', text)
    
    if match:
        amount_str = match.group(1)
        description = match.group(2).strip()
        
        # Определяем тип операции по знаку
        if amount_str.startswith('+'):
            transaction_type = 'income'
            amount = float(amount_str[1:])
            response = f"📥 Доход: {amount} руб\n📝 {description}"
        elif amount_str.startswith('-'):
            transaction_type = 'expense'
            amount = float(amount_str[1:])
            response = f"📤 Расход: {amount} руб\n📝 {description}"
        else:
            transaction_type = 'expense'
            amount = float(amount_str)
            response = f"📤 Расход: {amount} руб\n📝 {description}\n💡 Совет: используйте + для доходов!"
        
        # Определяем категорию
        category = detect_category(description)
        response += f"\n🏷 Категория: {category}"
        
        add_transaction(user_id, amount, description, transaction_type, category)
        response += "\n✅ Успешно добавлено!"
        
        # Проверяем бюджет для расходов
        if transaction_type == 'expense':
            budgets = get_budgets(user_id)
            if category in budgets:
                progress = get_budget_progress(user_id)
                if category in progress:
                    budget_data = progress[category]
                    if budget_data['percentage'] > 80:
                        response += f"\n⚠️ Внимание: по категории '{category}' израсходовано {budget_data['percentage']:.1f}% бюджета!"
        
        await message.answer(response, reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "❌ Неверный формат. Используйте:\n"
            "• +50000 зарплата - ДОХОД\n"
            "• -500 еда - РАСХОД\n\n"
            "📱 Или используйте кнопки ниже!",
            reply_markup=get_main_keyboard()
        )

async def main():
    print("🤖 Умный финансовый бот запускается...")
    print("📱 Все кнопки работают!")
    print("💬 Напишите /start для начала работы")
    print("⏹️  Для остановки: Ctrl+C")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())