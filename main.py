import asyncio
import logging
import os
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from config import BOT_TOKEN
from database import Database
from handlers import SubscriptionBot, WAITING_NAME, WAITING_PRICE, WAITING_COMMENT, WAITING_DATE, EDIT_VALUE
from notifications import NotificationManager

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class SubscriptionBotApp:
    def __init__(self):
        self.db = Database()
        self.bot_handler = SubscriptionBot(self.db)
        self.notification_manager = None
        
        # Создаем необходимые папки
        os.makedirs('exports', exist_ok=True)
        os.makedirs('charts', exist_ok=True)
    
    async def setup_application(self):
        """Настройка приложения"""
        if not BOT_TOKEN:
            raise ValueError("BOT_TOKEN не найден в переменных окружения!")
        
        # Создаем приложение
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Настраиваем обработчики команд
        self.setup_handlers(application)
        
        # Инициализируем менеджер уведомлений
        self.notification_manager = NotificationManager(application.bot, self.db)
        
        return application
    
    def setup_handlers(self, application):
        """Настройка всех обработчиков"""
        
        # ConversationHandler для добавления подписки через команду
        add_command_handler = ConversationHandler(
            entry_points=[
                CommandHandler("add", self.bot_handler.start_add_subscription_command),
                CallbackQueryHandler(self.bot_handler.start_add_subscription, pattern="^add_subscription$")
            ],
            states={
                WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.bot_handler.handle_name)],
                WAITING_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.bot_handler.handle_price)],
                WAITING_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.bot_handler.handle_comment)],
                WAITING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.bot_handler.handle_date)],
            },
            fallbacks=[
                CallbackQueryHandler(self.bot_handler.handle_period_selection, pattern="^period_"),
                CallbackQueryHandler(self.bot_handler.show_main_menu, pattern="^back_to_main$"),
                CallbackQueryHandler(self.cancel_conversation_callback, pattern="^cancel_add$"),
                CommandHandler("cancel", self.cancel_conversation)
            ],
            name="add_subscription_command",
            persistent=False
        )
        
        # Регистрируем ConversationHandler для команд
        application.add_handler(add_command_handler)
        
        # ConversationHandler для редактирования подписки
        edit_subscription_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.bot_handler.edit_field_entry, pattern="^edit_field_")
            ],
            states={
                EDIT_VALUE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.bot_handler.edit_field_value),
                    CallbackQueryHandler(self.bot_handler.edit_field_set_period, pattern="^set_period_"),
                    CallbackQueryHandler(self.bot_handler.edit_field_set_status, pattern="^set_status_")
                ],
            },
            fallbacks=[
                CallbackQueryHandler(self.bot_handler.show_main_menu, pattern="^back_to_main$"),
                CallbackQueryHandler(self.bot_handler.show_subscriptions, pattern="^list_subscriptions$")
            ],
            name="edit_subscription_handler",
            persistent=False
        )
        application.add_handler(edit_subscription_handler)
        
        # Основные команды
        application.add_handler(CommandHandler("start", self.bot_handler.start))
        application.add_handler(CommandHandler("help", self.bot_handler.help_command))
        application.add_handler(CommandHandler("list", self.list_subscriptions_command))
        application.add_handler(CommandHandler("analytics", self.analytics_command))
        application.add_handler(CommandHandler("export", self.export_command))
        
        # Обработчик inline кнопок (включая добавление подписки через кнопку)
        application.add_handler(CallbackQueryHandler(self.bot_handler.button_handler))
        # Обработчик неактивных подписок
        application.add_handler(CallbackQueryHandler(self.bot_handler.show_inactive_subscriptions, pattern="^inactive_subscriptions$"))
        application.add_handler(CallbackQueryHandler(self.bot_handler.change_subscription_status_menu, pattern="^change_status_"))
        application.add_handler(CallbackQueryHandler(self.bot_handler.set_status_inactive, pattern="^set_status_inactive_"))
        
        # Обработчик неизвестных команд
        application.add_handler(MessageHandler(filters.COMMAND, self.unknown_command))
    
    async def cancel_conversation(self, update: Update, context):
        """Отмена разговора"""
        user_id = update.message.from_user.id
        if user_id in self.bot_handler.user_states:
            del self.bot_handler.user_states[user_id]
        
        await update.message.reply_text(
            "❌ Операция отменена. Используйте /start для возврата в главное меню."
        )
        return ConversationHandler.END
    
    async def cancel_conversation_callback(self, update: Update, context):
        """Отмена разговора через инлайн-кнопку"""
        query = update.callback_query
        user_id = query.from_user.id
        if user_id in self.bot_handler.user_states:
            del self.bot_handler.user_states[user_id]
        await query.edit_message_text(
            "❌ Операция отменена. Используйте /start для возврата в главное меню."
        )
        return ConversationHandler.END
    
    async def list_subscriptions_command(self, update: Update, context):
        """Команда /list"""
        user_id = update.message.from_user.id
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        if not subscriptions:
            await update.message.reply_text(
                "📋 <b>У вас пока нет активных подписок</b>\n\n"
                "Добавьте первую подписку, чтобы начать отслеживание!",
                parse_mode='HTML'
            )
            return
        
        message = "📋 <b>Ваши активные подписки:</b>\n\n"
        
        for i, sub in enumerate(subscriptions, 1):
            from utils import calculate_next_payment_date
            next_payment = calculate_next_payment_date(sub['start_date'], sub['period'])
            days_left = (next_payment - update.message.date.date()).days
            
            message += f"{i}. <b>{sub['name']}</b>\n"
            message += f"   💰 {sub['price']} ₽ | 📅 {sub['period']}\n"
            message += f"   ⏰ Следующий платеж: {next_payment.strftime('%d.%m.%Y')} (через {days_left} дн.)\n\n"
        
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def analytics_command(self, update: Update, context):
        """Команда /analytics"""
        user_id = update.message.from_user.id
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        if not subscriptions:
            await update.message.reply_text(
                "📊 <b>Нет данных для аналитики</b>\n\n"
                "Добавьте подписки, чтобы увидеть статистику!",
                parse_mode='HTML'
            )
            return
        
        # Расчет статистики
        total_monthly = self.db.get_total_expenses(user_id, 'monthly')
        total_yearly = self.db.get_total_expenses(user_id, 'yearly')
        total_all = self.db.get_total_expenses(user_id, 'total')
        
        message = "📊 <b>Аналитика расходов</b>\n\n"
        message += f" Всего активных подписок: {len(subscriptions)}\n"
        message += f"💰 Расходы в месяц: {total_monthly:.2f} ₽\n"
        message += f"💰 Расходы в год: {total_yearly:.2f} ₽\n"
        message += f"💰 Общие расходы: {total_all:.2f} ₽\n\n"
        
        # Расходы по категориям
        expenses_by_category = self.db.get_expenses_by_category(user_id)
        if expenses_by_category:
            message += "📈 <b>Расходы по периодичности:</b>\n"
            for period, amount in expenses_by_category:
                message += f"• {period}: {amount:.2f} ₽\n"
        
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def export_command(self, update: Update, context):
        """Команда /export"""
        user_id = update.message.from_user.id
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        if not subscriptions:
            await update.message.reply_text(
                "📤 <b>Нет данных для экспорта</b>\n\n"
                "Добавьте подписки, чтобы экспортировать данные!",
                parse_mode='HTML'
            )
            return
        
        try:
            from utils import export_to_excel
            import datetime
            
            # Создаем папку для экспорта, если её нет
            os.makedirs('exports', exist_ok=True)
            
            filename = export_to_excel(subscriptions, user_id, self.db)
            
            with open(filename, 'rb') as file:
                await update.message.reply_document(
                    document=file,
                    filename=f"subscriptions_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    caption="📤 <b>Экспорт данных завершен!</b>\n\nФайл содержит:\n• Список всех подписок\n• Аналитику расходов\n• Сводную таблицу",
                    parse_mode='HTML'
                )
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ <b>Ошибка при экспорте:</b>\n\n{str(e)}",
                parse_mode='HTML'
            )
    
    async def debug_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отладочный обработчик для всех сообщений"""
        logger.info(f"=== ОТЛАДКА: Получено сообщение ===")
        logger.info(f"Текст: {update.message.text}")
        logger.info(f"Пользователь: {update.message.from_user.id}")
        logger.info(f"Chat ID: {update.message.chat_id}")
        
        # Проверяем, есть ли пользователь в состояниях
        user_id = update.message.from_user.id
        if hasattr(self.bot_handler, 'user_states') and user_id in self.bot_handler.user_states:
            logger.info(f"Пользователь {user_id} найден в состояниях: {self.bot_handler.user_states[user_id]}")
        else:
            logger.warning(f"Пользователь {user_id} НЕ найден в состояниях!")
        
        # Отправляем сообщение пользователю
        await update.message.reply_text(
            f"🔍 <b>Отладка:</b>\n\n"
            f"Получено сообщение: {update.message.text}\n"
            f"Пользователь ID: {user_id}\n"
            f"В состояниях: {'Да' if user_id in getattr(self.bot_handler, 'user_states', {}) else 'Нет'}",
            parse_mode='HTML'
        )
    
    async def start_notification_loop(self):
        """Запуск цикла уведомлений"""
        if self.notification_manager:
            await self.notification_manager.run_notification_loop()
    
    async def run(self):
        """Запуск бота"""
        try:
            # Настраиваем приложение
            application = await self.setup_application()
            
            logger.info("Бот запускается...")
            
            # Запускаем бота
            await application.initialize()
            await application.start()
            await application.updater.start_polling()
            
            logger.info("Бот успешно запущен!")
            
            # Запускаем цикл уведомлений в отдельной задаче
            notification_task = asyncio.create_task(self.start_notification_loop())
            
            # Ждем завершения
            try:
                await notification_task
            except KeyboardInterrupt:
                logger.info("Получен сигнал остановки...")
            finally:
                await application.updater.stop()
                await application.stop()
                await application.shutdown()
                
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
            raise

    async def unknown_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик неизвестных команд"""
        await update.message.reply_text(
            "❓ <b>Неизвестная команда</b>\n\n"
            "Используйте /start для доступа к главному меню или /help для справки.",
            parse_mode='HTML'
        )

async def main():
    """Главная функция"""
    bot_app = SubscriptionBotApp()
    await bot_app.run()

if __name__ == "__main__":
    # Запускаем бота
    asyncio.run(main())
