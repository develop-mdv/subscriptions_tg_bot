import datetime
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import List, Dict, Tuple
from config import SUBSCRIPTION_PERIODS, SUBSCRIPTION_STATUSES

def calculate_next_payment_date(start_date: str, period: str) -> datetime.date:
    """
    Корректный расчет ближайшей даты списания, начиная с даты старта и относительно текущей даты.
    """
    start = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
    today = datetime.date.today()
    
    if today < start:
        return start
    
    # Определяем шаг периода
    if period == 'daily':
        delta = datetime.timedelta(days=1)
        n = (today - start).days
        next_payment = start + delta * (n + 1)
        if next_payment <= today:
            next_payment += delta
        return next_payment
    elif period == 'weekly':
        delta = datetime.timedelta(weeks=1)
        n = (today - start).days // 7
        next_payment = start + delta * (n + 1)
        if next_payment <= today:
            next_payment += delta
        return next_payment
    elif period == 'monthly':
        # Считаем количество месяцев между start и today
        months = (today.year - start.year) * 12 + (today.month - start.month)
        next_month = start.month + months
        next_year = start.year + (next_month - 1) // 12
        next_month = ((next_month - 1) % 12) + 1
        try:
            next_payment = start.replace(year=next_year, month=next_month)
        except ValueError:
            # Если день не существует в следующем месяце (например, 31 февраля), берем последний день месяца
            import calendar
            last_day = calendar.monthrange(next_year, next_month)[1]
            next_payment = start.replace(year=next_year, month=next_month, day=last_day)
        if next_payment <= today:
            # Следующий месяц
            next_month += 1
            if next_month > 12:
                next_month = 1
                next_year += 1
            try:
                next_payment = start.replace(year=next_year, month=next_month)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(next_year, next_month)[1]
                next_payment = start.replace(year=next_year, month=next_month, day=last_day)
        return next_payment
    elif period == 'quarterly':
        # Квартал = 3 месяца
        months = ((today.year - start.year) * 12 + (today.month - start.month)) // 3 * 3
        next_month = start.month + months
        next_year = start.year + (next_month - 1) // 12
        next_month = ((next_month - 1) % 12) + 1
        try:
            next_payment = start.replace(year=next_year, month=next_month)
        except ValueError:
            import calendar
            last_day = calendar.monthrange(next_year, next_month)[1]
            next_payment = start.replace(year=next_year, month=next_month, day=last_day)
        while next_payment <= today:
            # Следующий квартал
            next_month += 3
            if next_month > 12:
                next_month -= 12
                next_year += 1
            try:
                next_payment = start.replace(year=next_year, month=next_month)
            except ValueError:
                import calendar
                last_day = calendar.monthrange(next_year, next_month)[1]
                next_payment = start.replace(year=next_year, month=next_month, day=last_day)
        return next_payment
    elif period == 'yearly':
        years = today.year - start.year
        next_year = start.year + years
        try:
            next_payment = start.replace(year=next_year)
        except ValueError:
            # 29 февраля и невисокосный год
            next_payment = start.replace(year=next_year, day=28)
        if next_payment <= today:
            try:
                next_payment = start.replace(year=next_year + 1)
            except ValueError:
                next_payment = start.replace(year=next_year + 1, day=28)
        return next_payment
    
    return start

def days_until_payment(next_payment_date: datetime.date) -> int:
    """Количество дней до следующего платежа"""
    today = datetime.date.today()
    delta = next_payment_date - today
    return delta.days

def format_subscription_info(subscription: Dict) -> str:
    """Форматирование информации о подписке"""
    next_payment = calculate_next_payment_date(subscription['start_date'], subscription['period'])
    days_left = days_until_payment(next_payment)
    
    status_text = SUBSCRIPTION_STATUSES.get(subscription['status'], subscription['status'])
    period_text = SUBSCRIPTION_PERIODS.get(subscription['period'], subscription['period'])
    
    info = f"📋 <b>{subscription['name']}</b>\n"
    info += f"💰 Цена: {subscription['price']} ₽\n"
    info += f"📅 Периодичность: {period_text}\n"
    info += f"📆 Следующий платеж: {next_payment.strftime('%d.%m.%Y')}\n"
    info += f"⏰ Осталось дней: {days_left}\n"
    info += f"📊 Статус: {status_text}\n"
    
    if subscription['comment']:
        info += f"💬 Комментарий: {subscription['comment']}\n"
    
    return info

def create_subscriptions_dataframe(subscriptions: List[Dict]) -> pd.DataFrame:
    """Создание DataFrame для экспорта"""
    data = []
    for sub in subscriptions:
        next_payment = calculate_next_payment_date(sub['start_date'], sub['period'])
        days_left = days_until_payment(next_payment)
        
        data.append({
            'ID': sub['id'],
            'Название': sub['name'],
            'Цена (₽)': sub['price'],
            'Периодичность': SUBSCRIPTION_PERIODS.get(sub['period'], sub['period']),
            'Дата начала': sub['start_date'],
            'Следующий платеж': next_payment.strftime('%d.%m.%Y'),
            'Дней до платежа': days_left,
            'Статус': SUBSCRIPTION_STATUSES.get(sub['status'], sub['status']),
            'Комментарий': sub['comment'] or '',
            'Уведомления': 'Включены' if sub['notifications_enabled'] else 'Отключены'
        })
    
    return pd.DataFrame(data)

def create_expense_chart(subscriptions: List[Dict], user_id: int) -> str:
    """Создание графика расходов"""
    if not subscriptions:
        return "Нет данных для создания графика"
    
    # Группировка по периодичности
    period_data = {}
    for sub in subscriptions:
        period = SUBSCRIPTION_PERIODS.get(sub['period'], sub['period'])
        if period not in period_data:
            period_data[period] = 0
        period_data[period] += sub['price']
    
    # Создание графика
    plt.figure(figsize=(10, 6))
    periods = list(period_data.keys())
    amounts = list(period_data.values())
    
    plt.bar(periods, amounts, color=['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7'])
    plt.title('Расходы по подпискам по периодичности', fontsize=14, fontweight='bold')
    plt.xlabel('Периодичность')
    plt.ylabel('Сумма (₽)')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Сохранение графика
    chart_path = f'charts/expenses_chart_{user_id}.png'
    plt.savefig(chart_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return chart_path

def export_to_excel(subscriptions: List[Dict], user_id: int, db) -> str:
    """Экспорт данных в Excel"""
    if not subscriptions:
        return "Нет данных для экспорта"
    
    # Создание DataFrame
    df = create_subscriptions_dataframe(subscriptions)
    
    # Создание файла Excel
    filename = f'exports/subscriptions_{user_id}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # Лист с подписками
        df.to_excel(writer, sheet_name='Подписки', index=False)
        
        # Лист с аналитикой
        analytics_data = []
        
        # Общие расходы
        total_monthly = db.get_total_expenses(user_id, 'monthly')
        total_yearly = db.get_total_expenses(user_id, 'yearly')
        total_all = db.get_total_expenses(user_id, 'total')
        
        analytics_data.append(['Общие расходы за месяц', f'{total_monthly:.2f} ₽'])
        analytics_data.append(['Общие расходы за год', f'{total_yearly:.2f} ₽'])
        analytics_data.append(['Общие расходы всего', f'{total_all:.2f} ₽'])
        analytics_data.append(['', ''])
        
        # Расходы по категориям
        expenses_by_category = db.get_expenses_by_category(user_id)
        analytics_data.append(['Расходы по периодичности:', ''])
        for period, amount in expenses_by_category:
            period_name = SUBSCRIPTION_PERIODS.get(period, period)
            analytics_data.append([period_name, f'{amount:.2f} ₽'])
        
        analytics_df = pd.DataFrame(analytics_data, columns=['Показатель', 'Значение'])
        analytics_df.to_excel(writer, sheet_name='Аналитика', index=False)
        
        # Лист со сводной таблицей
        pivot_data = []
        for sub in subscriptions:
            next_payment = calculate_next_payment_date(sub['start_date'], sub['period'])
            pivot_data.append({
                'Месяц': next_payment.strftime('%Y-%m'),
                'Подписка': sub['name'],
                'Сумма': sub['price'],
                'Периодичность': SUBSCRIPTION_PERIODS.get(sub['period'], sub['period'])
            })
        
        pivot_df = pd.DataFrame(pivot_data)
        pivot_df.to_excel(writer, sheet_name='Сводная таблица', index=False)
    
    return filename

def parse_date_flexible(date_string: str) -> str | None:
    """
    Гибкий парсер даты. Возвращает строку в формате 'ГГГГ-ММ-ДД' или None, если не удалось распознать.
    Поддерживает форматы: 'ГГГГ-ММ-ДД', 'ДД.ММ.ГГГГ', 'Д.М.ГГГГ', 'ДД/ММ/ГГГГ', 'ДД-ММ-ГГГГ', 'ДД.ММ.ГГ', 'Д.М.ГГ'.
    """
    import re
    from datetime import datetime
    date_string = date_string.strip()
    formats = [
        '%Y-%m-%d',
        '%d.%m.%Y',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%d.%m.%y',
        '%d/%m/%y',
        '%d-%m-%y',
    ]
    # Удаляем лишние пробелы
    date_string = re.sub(r'\s+', '', date_string)
    for fmt in formats:
        try:
            dt = datetime.strptime(date_string, fmt)
            # Если год двухзначный, корректируем
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None

def validate_date(date_string: str) -> bool:
    """Проверка корректности даты (гибко)"""
    return parse_date_flexible(date_string) is not None

def validate_price(price_string: str) -> bool:
    """Проверка корректности цены"""
    try:
        price = float(price_string)
        return price >= 0
    except ValueError:
        return False 