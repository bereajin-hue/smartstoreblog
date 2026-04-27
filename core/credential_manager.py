import os
import json
from cryptography.fernet import Fernet
from utils.logger import get_logger

logger = get_logger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
KEY_FILE = os.path.join(DATA_DIR, '.secret_key')
CRED_FILE = os.path.join(DATA_DIR, 'credentials.enc')


def _get_or_create_key() -> bytes:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, 'rb') as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_FILE, 'wb') as f:
        f.write(key)
    os.chmod(KEY_FILE, 0o600)
    logger.info('새 암호화 키를 생성했습니다.')
    return key


def save_credentials(data: dict) -> None:
    key = _get_or_create_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(json.dumps(data).encode('utf-8'))
    with open(CRED_FILE, 'wb') as f:
        f.write(encrypted)
    logger.info('자격증명을 저장했습니다.')


def load_credentials() -> dict:
    if not os.path.exists(CRED_FILE):
        return {}
    key = _get_or_create_key()
    fernet = Fernet(key)
    with open(CRED_FILE, 'rb') as f:
        encrypted = f.read()
    try:
        return json.loads(fernet.decrypt(encrypted).decode('utf-8'))
    except Exception:
        logger.error('자격증명 복호화에 실패했습니다.')
        return {}


def delete_credentials() -> None:
    if os.path.exists(CRED_FILE):
        os.remove(CRED_FILE)
        logger.info('자격증명을 삭제했습니다.')
