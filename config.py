import os
from dotenv import load_dotenv

load_dotenv()

# Настройки бота
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
DATABASE_PATH = 'subscriptions.db'

# Настройки уведомлений
NOTIFICATION_DAYS_BEFORE = 1  # За сколько дней уведомлять о списании

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