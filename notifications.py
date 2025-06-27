import datetime
import asyncio
from typing import List, Dict
from telegram import Bot
from database import Database
from utils import calculate_next_payment_date, days_until_payment
from config import NOTIFICATION_DAYS_BEFORE
import sqlite3

class NotificationManager:
    def __init__(self, bot: Bot, db: Database):
        self.bot = bot
        self.db = db
    
    async def check_and_send_notifications(self):
        """Проверка и отправка уведомлений"""
        current_time = datetime.datetime.now()
        current_time_str = current_time.strftime('%H:%M')
        
        # Получаем подписки для текущего времени
        subscriptions = self.db.get_subscriptions_for_time_notification(current_time_str)
        
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
    
    async def check_and_send_daily_summaries(self):
        """Проверка и отправка ежедневных сводок в выбранное время"""
        current_time = datetime.datetime.now()
        current_time_str = current_time.strftime('%H:%M')
        
        # Получаем всех пользователей с активными подписками в текущее время
        with sqlite3.connect(self.db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT user_id FROM subscriptions 
                WHERE status = 'active' AND notifications_enabled = 1 
                AND notification_time = ?
            ''', (current_time_str,))
            user_ids = [row[0] for row in cursor.fetchall()]
        
        for user_id in user_ids:
            await self.send_daily_summary(user_id)
    
    async def run_notification_loop(self):
        """Основной цикл уведомлений"""
        while True:
            try:
                await self.check_and_send_notifications()
                await self.check_and_send_daily_summaries()
                # Проверяем каждую минуту для более точного времени уведомлений
                await asyncio.sleep(60)
            except Exception as e:
                print(f"Ошибка в цикле уведомлений: {e}")
                await asyncio.sleep(60)  # Ждем минуту перед повторной попыткой 