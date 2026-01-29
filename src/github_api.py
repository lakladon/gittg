import requests
import logging
from datetime import datetime, timedelta
from config import GITHUB_API_URL, GITHUB_TOKEN, logger

class GitHubAPI:
    def __init__(self):
        self.base_url = GITHUB_API_URL
        self.headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'GitHub-Tracker-Bot'
        }
        
        if GITHUB_TOKEN:
            self.headers['Authorization'] = f'token {GITHUB_TOKEN}'
    
    def get_repository_info(self, owner, repo_name):
        """Получение информации о репозитории"""
        try:
            url = f"{self.base_url}/repos/{owner}/{repo_name}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.warning(f"Репозиторий {owner}/{repo_name} не найден")
                return None
            else:
                logger.error(f"Ошибка API GitHub: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к GitHub API: {e}")
            return None
    
    def get_latest_commit(self, owner, repo_name, branch='main'):
        """Получение последнего коммита"""
        try:
            url = f"{self.base_url}/repos/{owner}/{repo_name}/commits/{branch}"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Не удалось получить коммит: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения коммита: {e}")
            return None
    
    def get_recent_commits(self, owner, repo_name, since=None):
        """Получение недавних коммитов"""
        try:
            url = f"{self.base_url}/repos/{owner}/{repo_name}/commits"
            params = {'per_page': 10}
            
            if since:
                params['since'] = since.isoformat()
            
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Не удалось получить коммиты: {response.status_code}")
                return []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения коммитов: {e}")
            return []
    
    def get_pull_requests(self, owner, repo_name, state='open'):
        """Получение пулл-реквестов"""
        try:
            url = f"{self.base_url}/repos/{owner}/{repo_name}/pulls"
            params = {'state': state, 'per_page': 10}
            
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Не удалось получить PR: {response.status_code}")
                return []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения PR: {e}")
            return []
    
    def get_latest_release(self, owner, repo_name):
        """Получение последнего релиза"""
        try:
            url = f"{self.base_url}/repos/{owner}/{repo_name}/releases/latest"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                # Релизов нет
                return None
            else:
                logger.warning(f"Не удалось получить релиз: {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения релиза: {e}")
            return None
    
    def get_issues(self, owner, repo_name, state='open'):
        """Получение issues"""
        try:
            url = f"{self.base_url}/repos/{owner}/{repo_name}/issues"
            params = {'state': state, 'per_page': 10}
            
            response = requests.get(url, headers=self.headers, params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Не удалось получить issues: {response.status_code}")
                return []
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка получения issues: {e}")
            return []
    
    def check_rate_limit(self):
        """Проверка лимита запросов к GitHub API"""
        try:
            url = f"{self.base_url}/rate_limit"
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                return data['resources']['core']
            return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка проверки лимита: {e}")
            return None
    
    def validate_repository(self, owner, repo_name):
        """Валидация существования репозитория"""
        repo_info = self.get_repository_info(owner, repo_name)
        return repo_info is not None

# Создание экземпляра GitHub API
github_api = GitHubAPI()