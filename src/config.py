import os
import logging
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')  

DATABASE_NAME = 'github_tracker.db'
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DATABASE_NAME)

LOG_LEVEL = logging.INFO
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = 'github_tracker.log'

GITHUB_API_URL = 'https://api.github.com'
GITHUB_API_VERSION = '2022-11-28'

CHECK_INTERVAL_MINUTES = 5  
MAX_REPOS_PER_USER = 10  
MAX_EVENTS_PER_REPO = 10  

def setup_logging():
    """Настройка логирования"""
    logging.basicConfig(
        level=LOG_LEVEL,
        format=LOG_FORMAT,
        handlers=[
            logging.FileHandler(LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

logger = setup_logging()