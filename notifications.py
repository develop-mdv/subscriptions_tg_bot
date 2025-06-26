import datetime
import asyncio
from typing import List, Dict
from telegram import Bot
from database import Database
from utils import calculate_next_payment_date, days_until_payment
from config import NOTIFICATION_DAYS_BEFORE

class NotificationManager:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
    
    async def check_and_send_notifications(self):
        """Проверка и отправка уведомлений"""
        subscriptions = self.db.get_subscriptions_for_notification()
        today = datetime.date.today()
        
        for subscription in subscriptions:
            next_payment = calculate_next_payment_date(subscription['start_date'], subscription['period'])
            days_left = days_until_payment(next_payment)
            
            # Уведомление за день до списания
            if days_left == NOTIFICATION_DAYS_BEFORE:
                await self.send_payment_reminder(subscription, days_left)
            
            # Уведомление в день списания
            elif days_left == 0:
                await self.send_payment_today_notification(subscription)
    
    async def send_payment_reminder(self, subscription: Dict, days_left: int):
        """Отправка напоминания о платеже"""
        message = f"🔔 <b>Напоминание о платеже</b>\n\n"
        message += f"📋 Подписка: <b>{subscription['name']}</b>\n"
        message += f"💰 Сумма: {subscription['price']} ₽\n"
        message += f"📅 Дата списания: {datetime.date.today() + datetime.timedelta(days=days_left)}\n"
        message += f"⏰ Осталось дней: {days_left}\n\n"
        message += "Не забудьте пополнить счет! 💳"
        
        try:
            await self.bot.send_message(
                chat_id=subscription['user_id'],
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления: {e}")
    
    async def send_payment_today_notification(self, subscription: Dict):
        """Отправка уведомления о списании сегодня"""
        message = f"💳 <b>Списание средств сегодня!</b>\n\n"
        message += f"📋 Подписка: <b>{subscription['name']}</b>\n"
        message += f"💰 Сумма: {subscription['price']} ₽\n"
        message += f"📅 Дата: {datetime.date.today().strftime('%d.%m.%Y')}\n\n"
        message += "Убедитесь, что на счете достаточно средств! ✅"
        
        try:
            await self.bot.send_message(
                chat_id=subscription['user_id'],
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Ошибка отправки уведомления: {e}")
    
    async def send_daily_summary(self, user_id: int):
        """Отправка ежедневной сводки"""
        subscriptions = self.db.get_user_subscriptions(user_id, 'active')
        
        if not subscriptions:
            return
        
        total_monthly = self.db.get_total_expenses(user_id, 'monthly')
        total_yearly = self.db.get_total_expenses(user_id, 'yearly')
        
        message = f"📊 <b>Ежедневная сводка подписок</b>\n\n"
        message += f"📋 Активных подписок: {len(subscriptions)}\n"
        message += f"💰 Расходы в месяц: {total_monthly:.2f} ₽\n"
        message += f"💰 Расходы в год: {total_yearly:.2f} ₽\n\n"
        
        # Ближайшие платежи
        upcoming_payments = []
        for sub in subscriptions:
            next_payment = calculate_next_payment_date(sub['start_date'], sub['period'])
            days_left = days_until_payment(next_payment)
            if days_left <= 7:  # Показываем только ближайшие 7 дней
                upcoming_payments.append((sub, days_left))
        
        if upcoming_payments:
            message += "🔔 <b>Ближайшие платежи:</b>\n"
            for sub, days in sorted(upcoming_payments, key=lambda x: x[1]):
                message += f"• {sub['name']} - через {days} дн. ({sub['price']} ₽)\n"
        
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Ошибка отправки сводки: {e}")
    
    async def run_notification_loop(self):
        """Основной цикл уведомлений"""
        while True:
            try:
                await self.check_and_send_notifications()
                # Проверяем каждые 6 часов
                await asyncio.sleep(6 * 60 * 60)
            except Exception as e:
                print(f"Ошибка в цикле уведомлений: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед повторной попыткой 