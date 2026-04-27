import os
import json
from cryptography.fernet import Fernet
from utils.logger import get_logger

logger = get_logger(__name__)

_BASE = os.path.join(os.path.dirname(__file__), '..')


class CredentialManager:
    key_path = os.path.join(_BASE, 'data', '.secret_key')
    cred_path = os.path.join(_BASE, 'data', 'credentials.enc')

    def _get_fernet(self) -> Fernet:
        os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
        if os.path.exists(self.key_path):
            with open(self.key_path, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, 'wb') as f:
                f.write(key)
            os.chmod(self.key_path, 0o600)
            logger.info('새 암호화 키를 생성했습니다.')
        return Fernet(key)

    def save(self, data: dict) -> None:
        fernet = self._get_fernet()
        encrypted = fernet.encrypt(json.dumps(data, ensure_ascii=False).encode('utf-8'))
        with open(self.cred_path, 'wb') as f:
            f.write(encrypted)
        logger.info('자격증명을 저장했습니다.')

    def load(self) -> dict:
        if not os.path.exists(self.cred_path):
            return {}
        fernet = self._get_fernet()
        try:
            with open(self.cred_path, 'rb') as f:
                encrypted = f.read()
            return json.loads(fernet.decrypt(encrypted).decode('utf-8'))
        except Exception as e:
            logger.error(f'자격증명 복호화 실패: {e}')
            return {}

    def has_credentials(self) -> bool:
        if not os.path.exists(self.cred_path):
            return False
        data = self.load()
        return bool(data.get('naver_id') and data.get('naver_pw'))
