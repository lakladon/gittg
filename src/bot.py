#TEST
import asyncio
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ParseMode

from config import BOT_TOKEN, logger, CHECK_INTERVAL_MINUTES
from database import db
from github_api import github_api

class GitHubTrackerBot:
    def __init__(self):
        self.application = None
    
    def run(self):
        """Запуск бота"""
        try:
            logger.info("Запуск GitHub Tracker Bot...")
            
            # Создаем приложение
            self.application = Application.builder().token(BOT_TOKEN).build()
            
            # Добавляем обработчики команд
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(CommandHandler("add", self.add_repo_command))
            self.application.add_handler(CommandHandler("remove", self.remove_repo_command))
            self.application.add_handler(CommandHandler("list", self.list_repos_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("check", self.check_now_command))
            
            # Обработчик для текстовых сообщений (для добавления репозитория)
            self.application.add_handler(MessageHandler(
                filters.TEXT & ~filters.COMMAND, self.handle_text
            ))
            
            # Обработчик callback запросов
            self.application.add_handler(CallbackQueryHandler(self.handle_callback))
            
            # Настраиваем периодическую проверку
            self.setup_periodic_check()
            
            # Запускаем бота
            logger.info("Бот запущен")
            self.application.run_polling(allowed_updates=Update.ALL_TYPES)
            
        except Exception as e:
            logger.error(f"Ошибка запуска бота: {e}")
    
    def setup_periodic_check(self):
        """Настройка периодической проверки репозиториев"""
        job_queue = self.application.job_queue
        
        if job_queue:
            # Проверка каждые N минут
            job_queue.run_repeating(
                self.check_all_repositories,
                interval=CHECK_INTERVAL_MINUTES * 60,
                first=10
            )
            logger.info(f"Периодическая проверка настроена на каждые {CHECK_INTERVAL_MINUTES} минут")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user = update.effective_user
        user_id = user.id
        
        # Добавляем пользователя в базу
        db_user_id = db.add_user(
            telegram_id=user_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
        welcome_message = (
            f"👋 Привет, {user.first_name}!\n\n"
            "🤖 Я бот для отслеживания GitHub репозиториев.\n\n"
            "📊 Я могу уведомлять вас о:\n"
            "• Новых коммитах\n"
            "• Пулл-реквестах\n"
            "• Релизах\n"
            "• Issues\n\n"
            "🛠️ Доступные команды:\n"
            "/add - Добавить репозиторий\n"
            "/remove - Удалить репозиторий\n"
            "/list - Список отслеживаемых репозиториев\n"
            "/status - Статус репозитория\n"
            "/check - Проверить сейчас\n"
            "/stats - Статистика\n"
            "/help - Помощь\n\n"
            "📝 Чтобы добавить репозиторий, отправьте ссылку или в формате: owner/repo"
        )
        
        await update.message.reply_text(welcome_message)
        logger.info(f"Пользователь {user_id} запустил бота")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /help"""
        help_message = (
            "📖 Помощь по использованию бота:\n\n"
            "🛠️ Команды:\n"
            "/add <репозиторий> - Добавить репозиторий для отслеживания\n"
            "/remove <репозиторий> - Удалить репозиторий из отслеживания\n"
            "/list - Показать все отслеживаемые репозитории\n"
            "/status <репозиторий> - Показать статус репозитория\n"
            "/check - Принудительная проверка всех репозиториев\n"
            "/stats - Статистика бота\n"
            "/help - Эта справка\n\n"
            "📝 Форматы добавления репозитория:\n"
            "• https://github.com/owner/repo\n"
            "• owner/repo\n"
            "• github.com/owner/repo\n\n"
            "⏱️ Проверка обновлений происходит автоматически каждые 5 минут."
        )
        
        await update.message.reply_text(help_message)
    
    async def add_repo_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /add"""
        user = update.effective_user
        user_info = db.get_user(user.id)
        
        if not user_info:
            await update.message.reply_text("Сначала запустите бота командой /start")
            return
        
        if not context.args:
            await update.message.reply_text(
                "Укажите репозиторий для добавления.\n"
                "Пример: /add octocat/Hello-World\n"
                "Или отправьте ссылку: https://github.com/octocat/Hello-World"
            )
            return
        
        repo_input = ' '.join(context.args)
        await self.process_add_repository(update, user_info['id'], repo_input)
    
    async def remove_repo_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /remove"""
        user = update.effective_user
        user_info = db.get_user(user.id)
        
        if not user_info:
            await update.message.reply_text("Сначала запустите бота командой /start")
            return
        
        if not context.args:
            # Показываем список репозиториев для удаления
            repos = db.get_user_repositories(user_info['id'])
            
            if not repos:
                await update.message.reply_text("У вас нет отслеживаемых репозиториев.")
                return
            
            keyboard = []
            for repo in repos:
                keyboard.append([
                    InlineKeyboardButton(
                        repo['full_name'],
                        callback_data=f"remove_{repo['full_name']}"
                    )
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Выберите репозиторий для удаления:",
                reply_markup=reply_markup
            )
            return
        
        repo_input = ' '.join(context.args)
        repo_full_name = self.extract_repo_info(repo_input)
        
        if not repo_full_name:
            await update.message.reply_text("Неверный формат репозитория.")
            return
        
        # Удаляем репозиторий
        success = db.remove_repository(user_info['id'], repo_full_name)
        
        if success:
            await update.message.reply_text(f"✅ Репозиторий {repo_full_name} удален из отслеживания.")
            logger.info(f"Пользователь {user.id} удалил репозиторий {repo_full_name}")
        else:
            await update.message.reply_text(f"❌ Репозиторий {repo_full_name} не найден в вашем списке.")
    
    async def list_repos_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /list"""
        user = update.effective_user
        user_info = db.get_user(user.id)
        
        if not user_info:
            await update.message.reply_text("Сначала запустите бота командой /start")
            return
        
        repos = db.get_user_repositories(user_info['id'])
        
        if not repos:
            await update.message.reply_text("У вас нет отслеживаемых репозиториев.")
            return
        
        message = "📋 Ваши отслеживаемые репозитории:\n\n"
        
        for i, repo in enumerate(repos, 1):
            last_update = ""
            if repo['last_commit_date']:
                last_update = f"\n📅 Последний коммит: {repo['last_commit_date']}"
            
            message += f"{i}. **{repo['full_name']}**{last_update}\n"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /status"""
        user = update.effective_user
        user_info = db.get_user(user.id)
        
        if not user_info:
            await update.message.reply_text("Сначала запустите бота командой /start")
            return
        
        if not context.args:
            await update.message.reply_text("Укажите репозиторий для проверки статуса.")
            return
        
        repo_input = ' '.join(context.args)
        repo_full_name = self.extract_repo_info(repo_input)
        
        if not repo_full_name:
            await update.message.reply_text("Неверный формат репозитория.")
            return
        
        # Получаем информацию о репозитории
        owner, repo_name = repo_full_name.split('/')
        repo_info = github_api.get_repository_info(owner, repo_name)
        
        if not repo_info:
            await update.message.reply_text(f"Репозиторий {repo_full_name} не найден.")
            return
        
        # Формируем сообщение со статусом
        message = (
            f"📊 **Статус репозитория {repo_full_name}**\n\n"
            f"⭐ Stars: {repo_info.get('stargazers_count', 0)}\n"
            f"🍴 Forks: {repo_info.get('forks_count', 0)}\n"
            f"👀 Watchers: {repo_info.get('watchers_count', 0)}\n"
            f"📝 Описание: {repo_info.get('description', 'Нет описания')}\n"
            f"🌍 Язык: {repo_info.get('language', 'Не указан')}\n"
            f"📅 Создан: {repo_info.get('created_at', '')}\n"
            f"🔄 Последнее обновление: {repo_info.get('updated_at', '')}\n"
        )
        
        # Проверяем, отслеживается ли репозиторий
        tracked_repo = db.get_repository_by_full_name(repo_full_name)
        if tracked_repo and tracked_repo['user_id'] == user_info['id']:
            message += "\n✅ **Отслеживается вами**"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /stats"""
        stats = db.get_statistics()
        
        # Проверяем лимит GitHub API
        rate_limit = github_api.check_rate_limit()
        rate_info = ""
        if rate_limit:
            remaining = rate_limit.get('remaining', 0)
            limit = rate_limit.get('limit', 0)
            reset_time = datetime.fromtimestamp(rate_limit.get('reset', 0))
            rate_info = (
                f"\n\n📊 **GitHub API лимит:**\n"
                f"🔄 Использовано: {limit - remaining}/{limit}\n"
                f"⏰ Сброс: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        
        message = (
            f"📈 **Статистика бота:**\n\n"
            f"👥 Пользователей: {stats['users']}\n"
            f"📚 Отслеживаемых репозиториев: {stats['repositories']}\n"
            f"📝 Событий в истории: {stats['events']}"
            f"{rate_info}"
        )
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    async def check_now_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /check"""
        user = update.effective_user
        
        await update.message.reply_text("🔄 Начинаю проверку репозиториев...")
        
        # Выполняем проверку
        checked_count = await self.check_all_repositories(context)
        
        await update.message.reply_text(
            f"✅ Проверка завершена!\n"
            f"Обработано репозиториев: {checked_count}"
        )
        logger.info(f"Пользователь {user.id} выполнил принудительную проверку")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        user = update.effective_user
        text = update.message.text.strip()
        user_info = db.get_user(user.id)
        
        if not user_info:
            await update.message.reply_text("Сначала запустите бота командой /start")
            return
        
        # Проверяем, похоже ли сообщение на репозиторий
        if any(pattern in text.lower() for pattern in ['github.com', '/']):
            await self.process_add_repository(update, user_info['id'], text)
        else:
            await update.message.reply_text(
                "Отправьте ссылку на GitHub репозиторий или используйте команду /add"
            )
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка callback запросов"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user = query.from_user
        user_info = db.get_user(user.id)
        
        if not user_info:
            await query.message.reply_text("Сначала запустите бота командой /start")
            return
        
        if data.startswith('remove_'):
            repo_full_name = data.replace('remove_', '')
            success = db.remove_repository(user_info['id'], repo_full_name)
            
            if success:
                await query.edit_message_text(f"✅ Репозиторий {repo_full_name} удален из отслеживания.")
            else:
                await query.edit_message_text(f"❌ Ошибка при удалении репозитория.")
    
    def extract_repo_info(self, text):
        """Извлечение информации о репозитории из текста"""
        # Паттерны для извлечения
        patterns = [
            r'github\.com/([^/\s]+)/([^/\s]+)',
            r'^([^/\s]+)/([^/\s]+)$'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.strip())
            if match:
                owner = match.group(1).strip()
                repo = match.group(2).strip().replace('.git', '')
                return f"{owner}/{repo}"
        
        return None
    
    async def process_add_repository(self, update, user_id, repo_input):
        """Обработка добавления репозитория"""
        repo_full_name = self.extract_repo_info(repo_input)
        
        if not repo_full_name:
            await update.message.reply_text(
                "Неверный формат репозитория.\n"
                "Используйте: owner/repo\n"
                "Или ссылку: https://github.com/owner/repo"
            )
            return
        
        # Проверяем существование репозитория
        owner, repo_name = repo_full_name.split('/')
        
        await update.message.reply_text(f"🔍 Проверяю репозиторий {repo_full_name}...")
        
        if not github_api.validate_repository(owner, repo_name):
            await update.message.reply_text(f"❌ Репозиторий {repo_full_name} не найден на GitHub.")
            return
        
        # Добавляем в базу
        success, message = db.add_repository(user_id, owner, repo_name, repo_full_name)
        
        if success:
            # Получаем начальные данные
            await self.check_repository_initial(user_id, repo_full_name)
            await update.message.reply_text(f"✅ {message}")
            logger.info(f"Добавлен репозиторий {repo_full_name} для пользователя {user_id}")
        else:
            await update.message.reply_text(f"❌ {message}")
    
    async def check_repository_initial(self, user_id, repo_full_name):
        """Первоначальная проверка репозитория"""
        try:
            owner, repo_name = repo_full_name.split('/')
            
            # Получаем данные
            latest_commit = github_api.get_latest_commit(owner, repo_name)
            latest_release = github_api.get_latest_release(owner, repo_name)
            prs = github_api.get_pull_requests(owner, repo_name, 'open')
            
            # Находим ID репозитория в базе
            repo_info = db.get_repository_by_full_name(repo_full_name)
            if not repo_info or repo_info['user_id'] != user_id:
                return
            
            # Обновляем данные
            update_data = {}
            
            if latest_commit:
                update_data['last_commit_sha'] = latest_commit.get('sha')
                update_data['last_commit_date'] = latest_commit['commit']['author']['date']
            
            if latest_release:
                update_data['last_release_tag'] = latest_release.get('tag_name')
                update_data['last_release_date'] = latest_release.get('published_at')
            
            if prs:
                latest_pr = prs[0]
                update_data['last_pr_number'] = latest_pr.get('number')
                update_data['last_pr_date'] = latest_pr.get('created_at')
            
            if update_data:
                db.update_repository_data(repo_info['id'], update_data)
                
        except Exception as e:
            logger.error(f"Ошибка при начальной проверке {repo_full_name}: {e}")
    
    async def check_all_repositories(self, context: ContextTypes.DEFAULT_TYPE = None):
        """Проверка всех отслеживаемых репозиториев"""
        try:
            repos = db.get_all_tracked_repositories()
            
            if not repos:
                return 0
            
            logger.info(f"Начинаю проверку {len(repos)} репозиториев")
            checked_count = 0
            
            for repo in repos:
                try:
                    await self.check_repository_updates(repo, context)
                    checked_count += 1
                    
                    # Небольшая задержка чтобы не превысить лимиты API
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Ошибка при проверке репозитория {repo['full_name']}: {e}")
            
            logger.info(f"Проверка завершена. Обработано: {checked_count}/{len(repos)}")
            return checked_count
            
        except Exception as e:
            logger.error(f"Ошибка при массовой проверке репозиториев: {e}")
            return 0
    
    async def check_repository_updates(self, repo, context: ContextTypes.DEFAULT_TYPE = None):
        """Проверка обновлений конкретного репозитория"""
        try:
            owner, repo_name = repo['full_name'].split('/')
            telegram_id = repo['telegram_id']
            
            # Проверяем новые коммиты
            if repo['last_commit_date']:
                since_date = datetime.fromisoformat(repo['last_commit_date'].replace('Z', '+00:00'))
            else:
                since_date = datetime.now() - timedelta(days=7)
            
            new_commits = github_api.get_recent_commits(owner, repo_name, since_date)
            
            if new_commits and len(new_commits) > 0:
                # Исключаем текущий коммит
                new_commits = [c for c in new_commits 
                              if c.get('sha') != repo.get('last_commit_sha')]
                
                if new_commits:
                    latest_commit = new_commits[0]
                    
                    # Обновляем в базе
                    db.update_repository_data(repo['id'], {
                        'last_commit_sha': latest_commit.get('sha'),
                        'last_commit_date': latest_commit['commit']['author']['date']
                    })
                    
                    # Отправляем уведомление
                    for commit in reversed(new_commits):  # В хронологическом порядке
                        await self.send_commit_notification(
                            telegram_id, repo['full_name'], commit, context
                        )
                        
                        # Добавляем в историю
                        db.add_event(
                            repo['id'],
                            'commit',
                            f"New commit: {commit.get('sha', '')[:7]} - {commit['commit']['message']}"
                        )
            
            # Проверяем новые релизы
            latest_release = github_api.get_latest_release(owner, repo_name)
            
            if latest_release and latest_release.get('tag_name') != repo.get('last_release_tag'):
                # Обновляем в базе
                db.update_repository_data(repo['id'], {
                    'last_release_tag': latest_release.get('tag_name'),
                    'last_release_date': latest_release.get('published_at')
                })
                
                # Отправляем уведомление
                await self.send_release_notification(
                    telegram_id, repo['full_name'], latest_release, context
                )
                
                # Добавляем в историю
                db.add_event(
                    repo['id'],
                    'release',
                    f"New release: {latest_release.get('tag_name')}"
                )
            
            # Проверяем новые PR
            prs = github_api.get_pull_requests(owner, repo_name, 'open')
            
            if prs:
                latest_pr = prs[0]
                if latest_pr.get('number') != repo.get('last_pr_number'):
                    # Обновляем в базе
                    db.update_repository_data(repo['id'], {
                        'last_pr_number': latest_pr.get('number'),
                        'last_pr_date': latest_pr.get('created_at')
                    })
                    
                    # Отправляем уведомление о новом PR
                    if repo.get('last_pr_number') is not None:
                        await self.send_pr_notification(
                            telegram_id, repo['full_name'], latest_pr, context
                        )
                        
                        # Добавляем в историю
                        db.add_event(
                            repo['id'],
                            'pull_request',
                            f"New PR: #{latest_pr.get('number')} - {latest_pr.get('title')}"
                        )
            
        except Exception as e:
            logger.error(f"Ошибка при проверке обновлений для {repo['full_name']}: {e}")
    
    async def send_commit_notification(self, telegram_id, repo_full_name, commit, context):
        """Отправка уведомления о коммите"""
        try:
            message = (
                f"🔄 **Новый коммит в {repo_full_name}**\n\n"
                f"👤 Автор: {commit['commit']['author']['name']}\n"
                f"📝 Сообщение: {commit['commit']['message']}\n"
                f"📅 Дата: {commit['commit']['author']['date']}\n"
                f"🔗 [Посмотреть коммит]({commit.get('html_url', '')})"
            )
            
            if context and context.bot:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о коммите: {e}")
    
    async def send_release_notification(self, telegram_id, repo_full_name, release, context):
        """Отправка уведомления о релизе"""
        try:
            message = (
                f"🎉 **Новый релиз {release['tag_name']} в {repo_full_name}**\n\n"
                f"🏷️ Версия: {release['tag_name']}\n"
                f"📝 Название: {release.get('name', 'Без названия')}\n"
                f"📅 Дата: {release['published_at']}\n"
                f"📋 Описание:\n{release.get('body', 'Без описания')[:500]}...\n\n"
                f"🔗 [Скачать релиз]({release.get('html_url', '')})"
            )
            
            if context and context.bot:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN
                )
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о релизе: {e}")
    
    async def send_pr_notification(self, telegram_id, repo_full_name, pr, context):
        """Отправка уведомления о PR"""
        try:
            message = (
                f"🔀 **Новый Pull Request в {repo_full_name}**\n\n"
                f"#️⃣ Номер: #{pr['number']}\n"
                f"📝 Название: {pr['title']}\n"
                f"👤 Автор: {pr['user']['login']}\n"
                f"📅 Создан: {pr['created_at']}\n"
                f"🔄 Состояние: {pr['state']}\n\n"
                f"🔗 [Посмотреть PR]({pr.get('html_url', '')})"
            )
            
            if context and context.bot:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о PR: {e}")

# Запуск бота
if __name__ == "__main__":
    bot = GitHubTrackerBot()
    bot.run()
