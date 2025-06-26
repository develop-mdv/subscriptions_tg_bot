import sqlite3
import datetime
from typing import List, Dict, Optional, Tuple
from config import DATABASE_PATH

class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица подписок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    comment TEXT,
                    start_date TEXT NOT NULL,
                    period TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    notifications_enabled BOOLEAN DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица истории списаний
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscription_id INTEGER,
                    payment_date TEXT NOT NULL,
                    amount REAL NOT NULL,
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions (id)
                )
            ''')
            
            conn.commit()
    
    def add_subscription(self, user_id: int, name: str, price: float, comment: str, 
                        start_date: str, period: str) -> int:
        """Добавление новой подписки"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO subscriptions (user_id, name, price, comment, start_date, period)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, name, price, comment, start_date, period))
            conn.commit()
            return cursor.lastrowid
    
    def get_user_subscriptions(self, user_id: int, status: str = 'active') -> List[Dict]:
        """Получение подписок пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM subscriptions 
                WHERE user_id = ? AND status = ?
                ORDER BY start_date DESC
            ''', (user_id, status))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_subscription(self, subscription_id: int) -> Optional[Dict]:
        """Получение конкретной подписки"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscriptions WHERE id = ?', (subscription_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_subscription(self, subscription_id: int, **kwargs) -> bool:
        """Обновление подписки"""
        if not kwargs:
            return False
        
        set_clause = ', '.join([f"{key} = ?" for key in kwargs.keys()])
        values = list(kwargs.values()) + [subscription_id]
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(f'UPDATE subscriptions SET {set_clause} WHERE id = ?', values)
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_subscription(self, subscription_id: int) -> bool:
        """Удаление подписки"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM subscriptions WHERE id = ?', (subscription_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def get_subscriptions_for_notification(self) -> List[Dict]:
        """Получение подписок для отправки уведомлений"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM subscriptions 
                WHERE status = 'active' AND notifications_enabled = 1
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_total_expenses(self, user_id: int, period: str = 'monthly') -> float:
        """Получение общих расходов за период"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if period == 'monthly':
                cursor.execute('''
                    SELECT SUM(price) FROM subscriptions 
                    WHERE user_id = ? AND status = 'active' AND period = 'monthly'
                ''', (user_id,))
            elif period == 'yearly':
                cursor.execute('''
                    SELECT SUM(price) FROM subscriptions 
                    WHERE user_id = ? AND status = 'active' AND period = 'yearly'
                ''', (user_id,))
            else:  # total
                cursor.execute('''
                    SELECT SUM(price) FROM subscriptions 
                    WHERE user_id = ? AND status = 'active'
                ''', (user_id,))
            
            result = cursor.fetchone()
            return result[0] or 0.0
    
    def get_expenses_by_category(self, user_id: int) -> List[Tuple[str, float]]:
        """Получение расходов по категориям (периодичности)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT period, SUM(price) FROM subscriptions 
                WHERE user_id = ? AND status = 'active'
                GROUP BY period
            ''', (user_id,))
            return cursor.fetchall()
    
    def get_total_expenses_all_time(self, user_id: int) -> float:
        """Получение суммы всех трат пользователя за все время по истории платежей"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT SUM(amount) FROM payment_history
                WHERE subscription_id IN (
                    SELECT id FROM subscriptions WHERE user_id = ?
                )
            ''', (user_id,))
            result = cursor.fetchone()
            return result[0] or 0.0
    
    def get_total_expenses_active_periods(self, user_id: int) -> float:
        """Сумма всех трат по всем подпискам пользователя за периоды активности (от start_date до текущей даты)"""
        import datetime
        from dateutil.relativedelta import relativedelta
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM subscriptions WHERE user_id = ?
            ''', (user_id,))
            subs = cursor.fetchall()
        total = 0.0
        today = datetime.date.today()
        for sub in subs:
            start = datetime.datetime.strptime(sub['start_date'], '%Y-%m-%d').date()
            # Если появится поле end_date, использовать его:
            # end = sub['end_date'] if sub['end_date'] else today
            end = today
            if end < start:
                continue
            period = sub['period']
            price = sub['price']
            # Считаем количество полных периодов
            if period == 'daily':
                n = (end - start).days + 1
            elif period == 'weekly':
                n = ((end - start).days) // 7 + 1
            elif period == 'monthly':
                n = (end.year - start.year) * 12 + (end.month - start.month)
                if end.day >= start.day:
                    n += 1
            elif period == 'quarterly':
                n = ((end.year - start.year) * 12 + (end.month - start.month)) // 3
                if end.day >= start.day:
                    n += 1
            elif period == 'yearly':
                n = end.year - start.year
                if (end.month, end.day) >= (start.month, start.day):
                    n += 1
            else:
                n = 0
            if n > 0:
                total += price * n
        return total 