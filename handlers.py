import datetime
import os
import logging
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from database import Database
from utils import (
    format_subscription_info, validate_date, validate_price, 
    create_expense_chart, export_to_excel, calculate_next_payment_date, parse_date_flexible
)
from config import SUBSCRIPTION_PERIODS, SUBSCRIPTION_STATUSES, NOTIFICATION_TIMES

# Логирование
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_NAME, WAITING_PRICE, WAITING_COMMENT, WAITING_DATE, WAITING_PERIOD = range(5)
WAITING_EDIT_FIELD, WAITING_EDIT_VALUE = range(5, 7)

# Новые состояния для редактирования
EDIT_FIELD, EDIT_VALUE = range(7, 9)

class SubscriptionBot:
    def __init__(self, db: Database):
        self.db = db
        self.user_states = {}  # Хранение состояния пользователей
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = """
🎉 <b>Добро пожаловать в бот для отслеживания подписок!</b>

Этот бот поможет вам:
• 📝 Добавлять и управлять подписками
• 📊 Анализировать расходы
• 🔔 Получать уведомления о платежах
• 📈 Экспортировать данные в Excel

Используйте меню ниже для навигации:
        """
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить подписку", callback_data="add_subscription")],
            [InlineKeyboardButton("📋 Мои подписки", callback_data="list_subscriptions")],
            [InlineKeyboardButton("📁 Неактивные подписки", callback_data="inactive_subscriptions")],
            [InlineKeyboardButton("📊 Аналитика", callback_data="analytics")],
            [InlineKeyboardButton("📤 Экспорт в Excel", callback_data="export_excel")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📚 <b>Справка по командам:</b>

<b>Основные команды:</b>
/start - Главное меню
/help - Эта справка
/add - Добавить подписку
/list - Список подписок
/analytics - Аналитика расходов
/export - Экспорт в Excel

<b>Управление подписками:</b>
• Добавление: название, цена, дата начала, периодичность
• Редактирование: изменение любых полей
• Удаление: полное удаление подписки
• Статусы: активная, приостановлена, отменена

<b>Уведомления:</b>
• За день до списания
• В день списания
• Ежедневная сводка (опционально)

<b>Аналитика:</b>
• Общие расходы за месяц/год
• Расходы по категориям
• Графики и диаграммы
        """
        
        await update.message.reply_text(help_text, parse_mode='HTML')
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline кнопок"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "add_subscription":
            # Запускаем ConversationHandler через update.callback_query
            # Передаем управление в start_add_subscription (аналогично команде)
            return await self.start_add_subscription(update, context)
        elif query.data == "list_subscriptions":
            await self.show_subscriptions(query, context)
        elif query.data == "analytics":
            await self.show_analytics(query, context)
        elif query.data == "export_excel":
            await self.export_data(query, context)
        elif query.data == "settings":
            await self.show_settings(query, context)
        elif query.data == "settings_notifications":
            await self.show_notifications_settings(query, context)
        elif query.data == "settings_notification_time":
            await self.show_notification_time_settings(query, context)
        elif query.data.startswith("change_notification_time_"):
            await self.change_notification_time_menu(query, context)
        elif query.data.startswith("set_notification_time_"):
            await self.set_notification_time(query, context)
        elif query.data.startswith("edit_"):
            await self.edit_subscription_menu(query, context)
        elif query.data.startswith("delete_"):
            await self.delete_subscription(query, context)
        elif query.data.startswith("toggle_notifications_"):
            await self.toggle_notifications(query, context)
        elif query.data == "back_to_main":
            await self.show_main_menu(query, context)
        elif query.data == "inactive_subscriptions":
            await self.show_inactive_subscriptions(query, context)
        elif query.data.startswith("change_status_"):
            await self.change_subscription_status_menu(query, context)
        elif query.data.startswith("set_status_inactive_"):
            await self.set_status_inactive(query, context)
    
    async def start_add_subscription_simple(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Простое добавление подписки через кнопку (без ConversationHandler)"""
        logger.info("=== ПРОСТОЕ ДОБАВЛЕНИЕ ПОДПИСКИ ЧЕРЕЗ КНОПКУ ===")
        user_id = query.from_user.id
        logger.info(f"Пользователь {user_id} начал добавление подписки через кнопку")
        
        self.user_states[user_id] = {'action': 'add', 'data': {}}
        
        await query.edit_message_text(
            "📝 <b>Добавление новой подписки</b>\n\n"
            "Введите название подписки:",
            parse_mode='HTML'
        )
        logger.info(f"Отправлен запрос названия для пользователя {user_id}")
        
        # Сохраняем состояние в контексте для последующего использования
        context.user_data['waiting_for'] = 'name'
        context.user_data['user_states'] = self.user_states
    
    async def handle_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка названия подписки"""
        logger.info("=== ОБРАБОТКА НАЗВАНИЯ ПОДПИСКИ ===")
        logger.info(f"Получено сообщение: {update.message.text}")
        
        user_id = update.message.from_user.id
        name = update.message.text.strip()
        
        logger.info(f"Обработка названия '{name}' для пользователя {user_id}")
        logger.info(f"Текущие состояния пользователей: {list(self.user_states.keys())}")
        
        if user_id not in self.user_states:
            logger.error(f"Пользователь {user_id} не найден в состояниях!")
            await update.message.reply_text("❌ Ошибка: сессия не найдена. Начните заново с /add")
            return ConversationHandler.END
        
        if len(name) < 2:
            await update.message.reply_text("❌ Название должно содержать минимум 2 символа. Попробуйте снова:")
            return WAITING_NAME
        
        self.user_states[user_id]['data']['name'] = name
        logger.info(f"Название '{name}' сохранено для пользователя {user_id}")
        logger.info(f"Данные пользователя {user_id}: {self.user_states[user_id]}")
        
        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ Название: <b>{name}</b>\n\n"
            "Теперь введите цену подписки (только число):\n"
            "<i>Для отмены используйте /cancel или кнопку ниже.</i>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        logger.info(f"Отправлен запрос цены для пользователя {user_id}")
        return WAITING_PRICE
    
    async def handle_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка цены подписки"""
        user_id = update.message.from_user.id
        price_text = update.message.text.strip()
        
        if not validate_price(price_text):
            await update.message.reply_text("❌ Некорректная цена. Введите положительное число:")
            return WAITING_PRICE
        
        price = float(price_text)
        self.user_states[user_id]['data']['price'] = price
        
        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ Цена: <b>{price} ₽</b>\n\n"
            "Введите комментарий к подписке (или отправьте '-' для пропуска):\n"
            "<i>Для отмены используйте /cancel или кнопку ниже.</i>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return WAITING_COMMENT
    
    async def handle_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка комментария"""
        user_id = update.message.from_user.id
        comment = update.message.text.strip()
        
        if comment == '-':
            comment = ''
        
        self.user_states[user_id]['data']['comment'] = comment
        
        keyboard = [
            [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ Комментарий: <b>{comment or 'не указан'}</b>\n\n"
            "Введите дату начала подписки в формате ГГГГ-ММ-ДД:\n"
            "<i>Для отмены используйте /cancel или кнопку ниже.</i>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return WAITING_DATE
    
    async def handle_date(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка даты"""
        user_id = update.message.from_user.id
        date_text = update.message.text.strip()
        normalized_date = parse_date_flexible(date_text)
        if not normalized_date:
            await update.message.reply_text(
                "❌ Некорректная дата. Примеры: 2024-06-01, 01.06.2024, 1.6.24, 01/06/2024, 01-06-2024",
                parse_mode='HTML'
            )
            return WAITING_DATE
        self.user_states[user_id]['data']['start_date'] = normalized_date
        # Создаем кнопки для выбора периодичности
        keyboard = []
        for period_key, period_name in SUBSCRIPTION_PERIODS.items():
            keyboard.append([InlineKeyboardButton(period_name, callback_data=f"period_{period_key}")])
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")])
        keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ Дата начала: <b>{normalized_date}</b>\n\n"
            "Выберите периодичность подписки:\n"
            "<i>Для отмены используйте /cancel или кнопку ниже.</i>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return WAITING_PERIOD
    
    async def handle_period_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора периодичности"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        period = query.data.replace("period_", "")
        
        # Сохраняем подписку в базу данных
        data = self.user_states[user_id]['data']
        subscription_id = self.db.add_subscription(
            user_id=user_id,
            name=data['name'],
            price=data['price'],
            comment=data['comment'],
            start_date=data['start_date'],
            period=period
        )
        
        # Очищаем состояние пользователя
        del self.user_states[user_id]
        
        await query.edit_message_text(
            f"✅ <b>Подписка успешно добавлена!</b>\n\n"
            f"📋 Название: {data['name']}\n"
            f"💰 Цена: {data['price']} ₽\n"
            f"📅 Периодичность: {SUBSCRIPTION_PERIODS[period]}\n"
            f"📆 Дата начала: {datetime.datetime.strptime(data['start_date'], '%Y-%m-%d').strftime('%d.%m.%Y')}\n\n"
            f"ID подписки: {subscription_id}",
            parse_mode='HTML'
        )
        # После добавления показываем главное меню
        await self.show_main_menu(query, context)
        return ConversationHandler.END
    
    async def show_subscriptions(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Показ списка подписок"""
        user_id = query.from_user.id
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        if not subscriptions:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📋 <b>У вас пока нет активных подписок</b>\n\n"
                "Добавьте первую подписку, чтобы начать отслеживание!",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
        
        message = "📋 <b>Ваши активные подписки:</b>\n\n"
        
        for i, sub in enumerate(subscriptions, 1):
            next_payment = calculate_next_payment_date(sub['start_date'], sub['period'])
            days_left = (next_payment - datetime.date.today()).days
            
            message += f"{i}. <b>{sub['name']}</b>\n"
            message += f"   💰 {sub['price']} ₽ | 📅 {SUBSCRIPTION_PERIODS[sub['period']]}\n"
            message += f"   ⏰ Следующий платеж: {next_payment.strftime('%d.%m.%Y')} (через {days_left} дн.)\n\n"
        
        # Кнопки управления
        keyboard = []
        for sub in subscriptions:
            keyboard.append([
                InlineKeyboardButton(f"✏️ {sub['name']}", callback_data=f"edit_{sub['id']}"),
                InlineKeyboardButton(f"🗑️ {sub['name']}", callback_data=f"delete_{sub['id']}")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def show_analytics(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Показ аналитики"""
        user_id = query.from_user.id
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        if not subscriptions:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📊 <b>Нет данных для аналитики</b>\n\n"
                "Добавьте подписки, чтобы увидеть статистику!",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
        
        # Расчет статистики
        total_monthly = self.db.get_total_expenses(user_id, 'monthly')
        total_yearly = self.db.get_total_expenses(user_id, 'yearly')
        total_all = self.db.get_total_expenses(user_id, 'total')
        total_all_time = self.db.get_total_expenses_active_periods(user_id)
        
        message = "📊 <b>Аналитика расходов</b>\n\n"
        message += f"📋 Всего активных подписок: {len(subscriptions)}\n"
        message += f"💰 Расходы в месяц: {total_monthly:.2f} ₽\n"
        message += f"💰 Расходы в год: {total_yearly:.2f} ₽\n"
        message += f"💰 Общие расходы: {total_all:.2f} ₽\n"
        message += f"🧾 <b>Сумма всех трат за всё время:</b> {total_all_time:.2f} ₽\n\n"
        
        # Расходы по категориям
        expenses_by_category = self.db.get_expenses_by_category(user_id)
        if expenses_by_category:
            message += "📈 <b>Расходы по периодичности:</b>\n"
            for period, amount in expenses_by_category:
                period_name = SUBSCRIPTION_PERIODS.get(period, period)
                message += f"• {period_name}: {amount:.2f} ₽\n"
        
        # Создание графика
        try:
            chart_path = create_expense_chart(subscriptions, user_id)
            if os.path.exists(chart_path):
                with open(chart_path, 'rb') as chart:
                    await query.message.reply_photo(
                        photo=chart,
                        caption="📊 График расходов по подпискам"
                    )
        except Exception as e:
            print(f"Ошибка создания графика: {e}")
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def export_data(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Экспорт данных в Excel"""
        user_id = query.from_user.id
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        if not subscriptions:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "📤 <b>Нет данных для экспорта</b>\n\n"
                "Добавьте подписки, чтобы экспортировать данные!",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
        
        try:
            # Создаем папку для экспорта, если её нет
            os.makedirs('exports', exist_ok=True)
            
            filename = export_to_excel(subscriptions, user_id, self.db)
            
            with open(filename, 'rb') as file:
                await query.message.reply_document(
                    document=file,
                    filename=f"subscriptions_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    caption="📤 <b>Экспорт данных завершен!</b>\n\nФайл содержит:\n• Список всех подписок\n• Аналитику расходов\n• Сводную таблицу",
                    parse_mode='HTML'
                )
            
            await query.edit_message_text(
                "✅ <b>Экспорт успешно завершен!</b>\n\n"
                "Файл Excel отправлен выше.",
                parse_mode='HTML'
            )
            
        except Exception as e:
            await query.edit_message_text(
                f"❌ <b>Ошибка при экспорте:</b>\n\n{str(e)}",
                parse_mode='HTML'
            )
    
    async def show_settings(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Показ настроек"""
        message = "⚙️ <b>Настройки</b>\n\n"
        message += "Выберите раздел настроек:"
        
        keyboard = [
            [InlineKeyboardButton("🔔 Уведомления", callback_data="settings_notifications")],
            [InlineKeyboardButton("⏰ Время уведомлений", callback_data="settings_notification_time")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def toggle_notifications(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Переключение уведомлений"""
        subscription_id = int(query.data.replace("toggle_notifications_", ""))
        subscription = self.db.get_subscription(subscription_id)
        
        if not subscription:
            await query.answer("❌ Подписка не найдена")
            return
        
        new_status = not subscription['notifications_enabled']
        self.db.update_subscription(subscription_id, notifications_enabled=new_status)
        
        status_text = "включены" if new_status else "отключены"
        await query.answer(f"🔔 Уведомления {status_text}")
        
        # Обновляем меню настроек
        await self.show_notifications_settings(query, context)
    
    async def edit_subscription_menu(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Меню редактирования подписки"""
        subscription_id = int(query.data.replace("edit_", ""))
        subscription = self.db.get_subscription(subscription_id)
        
        if not subscription:
            await query.answer("❌ Подписка не найдена")
            return
        
        message = format_subscription_info(subscription)
        message += "\nВыберите, что хотите изменить:"
        
        keyboard = [
            [InlineKeyboardButton("📝 Название", callback_data=f"edit_field_{subscription_id}_name")],
            [InlineKeyboardButton("💰 Цена", callback_data=f"edit_field_{subscription_id}_price")],
            [InlineKeyboardButton("💬 Комментарий", callback_data=f"edit_field_{subscription_id}_comment")],
            [InlineKeyboardButton("📅 Дата начала", callback_data=f"edit_field_{subscription_id}_start_date")],
            [InlineKeyboardButton("🔄 Периодичность", callback_data=f"edit_field_{subscription_id}_period")],
            [InlineKeyboardButton("📊 Статус", callback_data=f"edit_field_{subscription_id}_status")],
            [InlineKeyboardButton("🔙 Назад", callback_data="list_subscriptions")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def delete_subscription(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Удаление подписки"""
        subscription_id = int(query.data.replace("delete_", ""))
        subscription = self.db.get_subscription(subscription_id)
        
        if not subscription:
            await query.answer("❌ Подписка не найдена")
            return
        
        # Удаляем подписку
        self.db.delete_subscription(subscription_id)
        
        await query.answer(f"🗑️ Подписка '{subscription['name']}' удалена")
        
        # Возвращаемся к списку подписок
        await self.show_subscriptions(query, context)
    
    async def show_main_menu(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Показ главного меню"""
        welcome_text = """
🎉 <b>Главное меню</b>

Выберите действие:
        """
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить подписку", callback_data="add_subscription")],
            [InlineKeyboardButton("📋 Мои подписки", callback_data="list_subscriptions")],
            [InlineKeyboardButton("📁 Неактивные подписки", callback_data="inactive_subscriptions")],
            [InlineKeyboardButton("📊 Аналитика", callback_data="analytics")],
            [InlineKeyboardButton("📤 Экспорт в Excel", callback_data="export_excel")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            welcome_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def start_add_subscription_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало добавления подписки через команду /add"""
        logger.info("=== НАЧАЛО ДОБАВЛЕНИЯ ПОДПИСКИ ЧЕРЕЗ КОМАНДУ ===")
        user_id = update.message.from_user.id
        logger.info(f"Пользователь {user_id} начал добавление подписки")
        
        self.user_states[user_id] = {'action': 'add', 'data': {}}
        
        await update.message.reply_text(
            "📝 <b>Добавление новой подписки</b>\n\n"
            "Введите название подписки:",
            parse_mode='HTML'
        )
        logger.info(f"Отправлен запрос названия для пользователя {user_id}")
        return WAITING_NAME
    
    async def start_add_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало добавления подписки"""
        logger.info("=== НАЧАЛО ДОБАВЛЕНИЯ ПОДПИСКИ ЧЕРЕЗ КНОПКУ ===")
        # Получаем CallbackQuery из Update
        query = update.callback_query
        user_id = query.from_user.id
        logger.info(f"Пользователь {user_id} начал добавление подписки через кнопку")
        
        self.user_states[user_id] = {'action': 'add', 'data': {}}
        
        await query.edit_message_text(
            "📝 <b>Добавление новой подписки</b>\n\n"
            "Введите название подписки:",
            parse_mode='HTML'
        )
        logger.info(f"Отправлен запрос названия для пользователя {user_id}")
        return WAITING_NAME

    async def edit_field_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатия на поле для редактирования"""
        query = update.callback_query
        await query.answer()
        data = query.data  # edit_field_{id}_{field}
        parts = data.split('_')
        subscription_id = int(parts[2])
        field = '_'.join(parts[3:])
        context.user_data['edit_subscription_id'] = subscription_id
        context.user_data['edit_field'] = field
        field_names = {
            'name': 'название',
            'price': 'цену',
            'comment': 'комментарий',
            'start_date': 'дату начала',
            'period': 'периодичность',
            'status': 'статус',
        }
        prompt = f"Введите новое значение для поля: <b>{field_names.get(field, field)}</b>"
        # Для period и status — показать варианты
        if field == 'period':
            keyboard = [[InlineKeyboardButton(v, callback_data=f"set_period_{k}")] for k, v in SUBSCRIPTION_PERIODS.items()]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Выберите новую периодичность:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return EDIT_VALUE
        elif field == 'status':
            keyboard = [[InlineKeyboardButton(v, callback_data=f"set_status_{k}")] for k, v in SUBSCRIPTION_STATUSES.items()]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Выберите новый статус:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return EDIT_VALUE
        else:
            await query.edit_message_text(prompt, parse_mode='HTML')
            return EDIT_VALUE

    async def edit_field_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ввода нового значения для поля"""
        subscription_id = context.user_data.get('edit_subscription_id')
        field = context.user_data.get('edit_field')
        value = update.message.text.strip() if update.message else None
        # Валидация
        if field == 'price':
            if not validate_price(value):
                await update.message.reply_text("❌ Некорректная цена. Введите положительное число:")
                return EDIT_VALUE
            value = float(value)
        elif field == 'start_date':
            normalized = parse_date_flexible(value)
            if not normalized:
                await update.message.reply_text("❌ Некорректная дата. Примеры: 2024-06-01, 01.06.2024, 1.6.24, 01/06/2024, 01-06-2024")
                return EDIT_VALUE
            value = normalized
        elif field == 'name':
            if len(value) < 2:
                await update.message.reply_text("❌ Название должно содержать минимум 2 символа. Попробуйте снова:")
                return EDIT_VALUE
        # Обновление
        self.db.update_subscription(subscription_id, **{field: value})
        # Показать обновлённую карточку
        subscription = self.db.get_subscription(subscription_id)
        message = format_subscription_info(subscription)
        message += "\nВыберите, что хотите изменить:"
        keyboard = [
            [InlineKeyboardButton("📝 Название", callback_data=f"edit_field_{subscription_id}_name")],
            [InlineKeyboardButton("💰 Цена", callback_data=f"edit_field_{subscription_id}_price")],
            [InlineKeyboardButton("💬 Комментарий", callback_data=f"edit_field_{subscription_id}_comment")],
            [InlineKeyboardButton("📅 Дата начала", callback_data=f"edit_field_{subscription_id}_start_date")],
            [InlineKeyboardButton("🔄 Периодичность", callback_data=f"edit_field_{subscription_id}_period")],
            [InlineKeyboardButton("📊 Статус", callback_data=f"edit_field_{subscription_id}_status")],
            [InlineKeyboardButton("🔙 Назад", callback_data="list_subscriptions")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
        return ConversationHandler.END

    async def edit_field_set_period(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        subscription_id = context.user_data.get('edit_subscription_id')
        period = query.data.replace('set_period_', '')
        self.db.update_subscription(subscription_id, period=period)
        subscription = self.db.get_subscription(subscription_id)
        message = format_subscription_info(subscription)
        message += "\nВыберите, что хотите изменить:"
        keyboard = [
            [InlineKeyboardButton("📝 Название", callback_data=f"edit_field_{subscription_id}_name")],
            [InlineKeyboardButton("💰 Цена", callback_data=f"edit_field_{subscription_id}_price")],
            [InlineKeyboardButton("💬 Комментарий", callback_data=f"edit_field_{subscription_id}_comment")],
            [InlineKeyboardButton("📅 Дата начала", callback_data=f"edit_field_{subscription_id}_start_date")],
            [InlineKeyboardButton("🔄 Периодичность", callback_data=f"edit_field_{subscription_id}_period")],
            [InlineKeyboardButton("📊 Статус", callback_data=f"edit_field_{subscription_id}_status")],
            [InlineKeyboardButton("🔙 Назад", callback_data="list_subscriptions")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        return ConversationHandler.END

    async def edit_field_set_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        subscription_id = context.user_data.get('edit_subscription_id')
        status = query.data.replace('set_status_', '')
        self.db.update_subscription(subscription_id, status=status)
        subscription = self.db.get_subscription(subscription_id)
        message = format_subscription_info(subscription)
        message += "\nВыберите, что хотите изменить:"
        keyboard = [
            [InlineKeyboardButton("📝 Название", callback_data=f"edit_field_{subscription_id}_name")],
            [InlineKeyboardButton("💰 Цена", callback_data=f"edit_field_{subscription_id}_price")],
            [InlineKeyboardButton("💬 Комментарий", callback_data=f"edit_field_{subscription_id}_comment")],
            [InlineKeyboardButton("📅 Дата начала", callback_data=f"edit_field_{subscription_id}_start_date")],
            [InlineKeyboardButton("🔄 Периодичность", callback_data=f"edit_field_{subscription_id}_period")],
            [InlineKeyboardButton("📊 Статус", callback_data=f"edit_field_{subscription_id}_status")],
            [InlineKeyboardButton("🔙 Назад", callback_data="list_subscriptions")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        return ConversationHandler.END

    async def show_inactive_subscriptions(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Показ неактивных (приостановленных и отменённых) подписок"""
        user_id = query.from_user.id
        paused = self.db.get_user_subscriptions(user_id, 'paused')
        cancelled = self.db.get_user_subscriptions(user_id, 'cancelled')
        subscriptions = paused + cancelled
        if not subscriptions:
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "📋 <b>У вас нет приостановленных или отменённых подписок</b>",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
        message = "📋 <b>Неактивные подписки:</b>\n\n"
        keyboard = []
        for i, sub in enumerate(subscriptions, 1):
            status = SUBSCRIPTION_STATUSES.get(sub['status'], sub['status'])
            start_date = datetime.datetime.strptime(sub['start_date'], '%Y-%m-%d').strftime('%d.%m.%Y')
            message += f"{i}. <b>{sub['name']}</b>\n"
            message += f"   💰 {sub['price']} ₽ | 📅 {SUBSCRIPTION_PERIODS.get(sub['period'], sub['period'])} | 📊 {status}\n"
            message += f"   📆 Дата начала: {start_date}\n"
            keyboard.append([InlineKeyboardButton(f"{i}. Изменить статус", callback_data=f"change_status_{sub['id']}")])
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)

    async def change_subscription_status_menu(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Показать меню выбора нового статуса для подписки"""
        await query.answer()
        subscription_id = int(query.data.replace("change_status_", ""))
        context.user_data['change_status_subscription_id'] = subscription_id
        keyboard = [[InlineKeyboardButton(v, callback_data=f"set_status_inactive_{subscription_id}_{k}")] for k, v in SUBSCRIPTION_STATUSES.items()]
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="inactive_subscriptions")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Выберите новый статус:", parse_mode='HTML', reply_markup=reply_markup)

    async def set_status_inactive(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        await query.answer()
        data = query.data.replace("set_status_inactive_", "")
        parts = data.split("_")
        subscription_id = int(parts[0])
        new_status = '_'.join(parts[1:])
        self.db.update_subscription(subscription_id, status=new_status)
        await self.show_inactive_subscriptions(query, context)

    async def show_notifications_settings(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Показ настроек уведомлений"""
        user_id = query.from_user.id
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        message = "🔔 <b>Настройки уведомлений</b>\n\n"
        message += "Управление уведомлениями по подпискам:\n\n"
        
        keyboard = []
        for sub in subscriptions:
            status = "🔔 Включены" if sub['notifications_enabled'] else "🔕 Отключены"
            message += f"• {sub['name']}: {status}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"{'🔕' if sub['notifications_enabled'] else '🔔'} {sub['name']}", 
                    callback_data=f"toggle_notifications_{sub['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="settings")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def show_notification_time_settings(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Показ настроек времени уведомлений"""
        user_id = query.from_user.id
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        message = "⏰ <b>Настройки времени уведомлений</b>\n\n"
        message += "Выберите подписку для изменения времени уведомлений:\n\n"
        
        keyboard = []
        for sub in subscriptions:
            current_time = sub.get('notification_time', '09:00')
            message += f"• {sub['name']}: {current_time}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⏰ {sub['name']} ({current_time})", 
                    callback_data=f"change_notification_time_{sub['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="settings")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def change_notification_time_menu(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Меню выбора времени уведомлений"""
        subscription_id = int(query.data.replace("change_notification_time_", ""))
        subscription = self.db.get_subscription(subscription_id)
        
        if not subscription:
            await query.answer("❌ Подписка не найдена")
            return
        
        context.user_data['change_time_subscription_id'] = subscription_id
        
        message = f"⏰ <b>Выбор времени уведомлений</b>\n\n"
        message += f"Подписка: <b>{subscription['name']}</b>\n"
        message += f"Текущее время: <b>{subscription.get('notification_time', '09:00')}</b>\n\n"
        message += "Выберите новое время:"
        
        keyboard = []
        for time_key, time_label in NOTIFICATION_TIMES.items():
            keyboard.append([InlineKeyboardButton(time_label, callback_data=f"set_notification_time_{subscription_id}_{time_key}")])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="settings_notification_time")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    
    async def set_notification_time(self, query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
        """Установка времени уведомлений"""
        data = query.data.replace("set_notification_time_", "")
        parts = data.split("_")
        subscription_id = int(parts[0])
        new_time = '_'.join(parts[1:])
        
        subscription = self.db.get_subscription(subscription_id)
        if not subscription:
            await query.answer("❌ Подписка не найдена")
            return
        
        self.db.update_subscription(subscription_id, notification_time=new_time)
        
        await query.answer(f"⏰ Время уведомлений изменено на {new_time}")
        
        # Возвращаемся к настройкам времени
        await self.show_notification_time_settings(query, context) 