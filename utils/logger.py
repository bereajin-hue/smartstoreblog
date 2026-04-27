import logging
import os
from logging.handlers import RotatingFileHandler

_LOG_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'app.log')
_FMT = '[%(asctime)s] [%(levelname)s] %(message)s'
_DATE_FMT = '%Y-%m-%d %H:%M:%S'

_logger: logging.Logger | None = None


def get_logger(name: str | None = None) -> logging.Logger:
    """
    name이 주어지면 해당 이름의 자식 로거를 반환합니다.
    루트 'AutoPoster' 로거는 최초 1회만 핸들러를 등록합니다.
    """
    global _logger

    # 루트 AutoPoster 로거 초기화 (최초 1회)
    if _logger is None:
        _logger = logging.getLogger('AutoPoster')
        _logger.setLevel(logging.DEBUG)
        _logger.propagate = False

        formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

        # 콘솔 핸들러
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        _logger.addHandler(console)

        # 파일 핸들러 (5 MB × 3개 롤오버)
        os.makedirs(os.path.dirname(_LOG_FILE), exist_ok=True)
        file_handler = RotatingFileHandler(
            _LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8',
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        _logger.addHandler(file_handler)

    if name and name != 'AutoPoster':
        return _logger.getChild(name)
    return _logger
