import os
from dotenv import load_dotenv

load_dotenv()

# Настройки бота
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
DATABASE_PATH = 'subscriptions.db'

# Настройки уведомлений
NOTIFICATION_DAYS_BEFORE = 1  # За сколько дней уведомлять о списании

# Варианты времени уведомлений
NOTIFICATION_TIMES = {
    '08:00': '08:00 - Утро',
    '09:00': '09:00 - Утро',
    '10:00': '10:00 - Утро',
    '12:00': '12:00 - Обед',
    '15:00': '15:00 - День',
    '18:00': '18:00 - Вечер',
    '20:00': '20:00 - Вечер',
    '21:00': '21:00 - Вечер'
}

# Периодичности подписок
SUBSCRIPTION_PERIODS = {
    'monthly': 'Ежемесячно',
    'quarterly': 'Ежеквартально', 
    'yearly': 'Ежегодно',
    'weekly': 'Еженедельно',
    'daily': 'Ежедневно'
}

# Статусы подписок
SUBSCRIPTION_STATUSES = {
    'active': 'Активна',
    'paused': 'Приостановлена',
    'cancelled': 'Отменена'
} 