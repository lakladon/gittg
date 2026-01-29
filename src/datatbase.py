import sqlite3
import logging
from datetime import datetime
from config import DATABASE_PATH, logger

class Database:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self.init_database()
    
    def get_connection(self):
        """Создание соединения с базой данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Инициализация таблиц базы данных"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица отслеживаемых репозиториев
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS repositories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    owner TEXT NOT NULL,
                    repo_name TEXT NOT NULL,
                    full_name TEXT NOT NULL UNIQUE,
                    last_commit_sha TEXT,
                    last_commit_date TIMESTAMP,
                    last_pr_number INTEGER,
                    last_pr_date TIMESTAMP,
                    last_release_tag TEXT,
                    last_release_date TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, full_name)
                )
            ''')
            
            # Таблица событий (история)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    repo_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (repo_id) REFERENCES repositories (id)
                )
            ''')
            
            # Индексы для ускорения запросов
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_repos_user ON repositories(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_repos_full_name ON repositories(full_name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_repo ON events(repo_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at)')
            
            conn.commit()
            logger.info("База данных инициализирована успешно")
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")
        finally:
            if conn:
                conn.close()
    
    def add_user(self, telegram_id, username=None, first_name=None, last_name=None):
        """Добавление нового пользователя"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (telegram_id, username, first_name, last_name))
            
            conn.commit()
            logger.info(f"Пользователь {telegram_id} добавлен/обновлен")
            
            # Получаем ID пользователя
            cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
            result = cursor.fetchone()
            
            return result['id'] if result else None
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_user(self, telegram_id):
        """Получение пользователя по Telegram ID"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM users WHERE telegram_id = ?', (telegram_id,))
            result = cursor.fetchone()
            
            return dict(result) if result else None
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def add_repository(self, user_id, owner, repo_name, full_name):
        """Добавление репозитория для отслеживания"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Проверяем лимит репозиториев
            cursor.execute('SELECT COUNT(*) as count FROM repositories WHERE user_id = ?', (user_id,))
            count = cursor.fetchone()['count']
            
            from config import MAX_REPOS_PER_USER
            if count >= MAX_REPOS_PER_USER:
                return False, "Превышен лимит отслеживаемых репозиториев"
            
            # Добавляем репозиторий
            cursor.execute('''
                INSERT OR REPLACE INTO repositories 
                (user_id, owner, repo_name, full_name, is_active)
                VALUES (?, ?, ?, ?, 1)
            ''', (user_id, owner, repo_name, full_name))
            
            conn.commit()
            logger.info(f"Репозиторий {full_name} добавлен для пользователя {user_id}")
            
            return True, "Репозиторий добавлен для отслеживания"
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления репозитория: {e}")
            return False, "Ошибка при добавлении репозитория"
        finally:
            if conn:
                conn.close()
    
    def remove_repository(self, user_id, full_name):
        """Удаление репозитория из отслеживания"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM repositories 
                WHERE user_id = ? AND full_name = ?
            ''', (user_id, full_name))
            
            conn.commit()
            deleted = cursor.rowcount > 0
            
            if deleted:
                logger.info(f"Репозиторий {full_name} удален для пользователя {user_id}")
            
            return deleted
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка удаления репозитория: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def get_user_repositories(self, user_id):
        """Получение всех репозиториев пользователя"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM repositories 
                WHERE user_id = ? AND is_active = 1
                ORDER BY created_at DESC
            ''', (user_id,))
            
            return [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения репозиториев пользователя: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def get_all_tracked_repositories(self):
        """Получение всех отслеживаемых репозиториев"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT r.*, u.telegram_id 
                FROM repositories r
                JOIN users u ON r.user_id = u.id
                WHERE r.is_active = 1
            ''')
            
            return [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения всех репозиториев: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def update_repository_data(self, repo_id, update_data):
        """Обновление данных репозитория"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            set_clauses = []
            values = []
            
            for key, value in update_data.items():
                set_clauses.append(f"{key} = ?")
                values.append(value)
            
            values.append(repo_id)
            
            query = f'''
                UPDATE repositories 
                SET {', '.join(set_clauses)}
                WHERE id = ?
            '''
            
            cursor.execute(query, values)
            conn.commit()
            
            return cursor.rowcount > 0
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка обновления данных репозитория: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def add_event(self, repo_id, event_type, event_data):
        """Добавление события в историю"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO events (repo_id, event_type, event_data)
                VALUES (?, ?, ?)
            ''', (repo_id, event_type, event_data))
            
            conn.commit()
            
            # Удаляем старые события (оставляем только последние N)
            from config import MAX_EVENTS_PER_REPO
            cursor.execute('''
                DELETE FROM events 
                WHERE id NOT IN (
                    SELECT id FROM events 
                    WHERE repo_id = ? 
                    ORDER BY created_at DESC 
                    LIMIT ?
                ) AND repo_id = ?
            ''', (repo_id, MAX_EVENTS_PER_REPO, repo_id))
            
            conn.commit()
            
            return True
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления события: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def get_recent_events(self, repo_id, limit=5):
        """Получение последних событий репозитория"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM events 
                WHERE repo_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (repo_id, limit))
            
            return [dict(row) for row in cursor.fetchall()]
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения событий: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def get_repository_by_full_name(self, full_name):
        """Получение репозитория по полному имени"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM repositories WHERE full_name = ?', (full_name,))
            result = cursor.fetchone()
            
            return dict(result) if result else None
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения репозитория: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def get_statistics(self):
        """Получение статистики по боту"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*) as user_count FROM users')
            user_count = cursor.fetchone()['user_count']
            
            cursor.execute('SELECT COUNT(*) as repo_count FROM repositories WHERE is_active = 1')
            repo_count = cursor.fetchone()['repo_count']
            
            cursor.execute('SELECT COUNT(*) as event_count FROM events')
            event_count = cursor.fetchone()['event_count']
            
            return {
                'users': user_count,
                'repositories': repo_count,
                'events': event_count
            }
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {'users': 0, 'repositories': 0, 'events': 0}
        finally:
            if conn:
                conn.close()

# Создание экземпляра базы данных
db = Database()