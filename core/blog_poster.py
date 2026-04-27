import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from utils.logger import get_logger

logger = get_logger(__name__)

NAVER_LOGIN_URL = 'https://nid.naver.com/nidlogin.login'


class BlogPoster:

    def __init__(self, headless: bool = False) -> None:
        options = Options()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument(
            'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
        )
        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)
        self._driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        self._wait = WebDriverWait(self._driver, 20)

    def login(self, naver_id: str, naver_pw: str) -> None:
        """네이버 계정으로 로그인합니다."""
        self._driver.get(NAVER_LOGIN_URL)
        self._wait.until(EC.presence_of_element_located((By.ID, 'id')))

        id_field = self._driver.find_element(By.ID, 'id')
        pw_field = self._driver.find_element(By.ID, 'pw')

        id_field.clear()
        for ch in naver_id:
            id_field.send_keys(ch)
            time.sleep(0.04)

        pw_field.clear()
        for ch in naver_pw:
            pw_field.send_keys(ch)
            time.sleep(0.04)

        self._driver.find_element(By.ID, 'log.login').click()
        time.sleep(3)

        if 'nidlogin' in self._driver.current_url:
            raise RuntimeError('네이버 로그인 실패 - ID/PW를 확인하세요.')
        logger.info('네이버 로그인 성공')

    def post_to_blog(
        self,
        blog_id: str,
        title: str,
        body: str,
        image_paths: list[str] | None = None,
    ) -> str:
        """스마트에디터 ONE에 포스팅을 작성하고 발행합니다."""
        write_url = f'https://blog.naver.com/{blog_id}/postwrite'
        self._driver.get(write_url)
        time.sleep(3)

        self._wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'mainFrame')))
        time.sleep(2)

        self._input_title(title)
        self._input_body(body)

        self._driver.switch_to.default_content()
        self._publish()

        post_url = self._driver.current_url
        logger.info(f'포스팅 게시 완료: {post_url}')
        return post_url

    def quit(self) -> None:
        try:
            self._driver.quit()
        except Exception:
            pass

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _input_title(self, title: str) -> None:
        try:
            el = self._wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.se-title-input')))
            el.click()
            el.send_keys(title)
        except Exception as e:
            logger.warning(f'제목 입력 실패: {e}')

    def _input_body(self, body: str) -> None:
        try:
            el = self._wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.se-content')))
            el.click()
            self._driver.execute_script("arguments[0].innerText = arguments[1]", el, body)
        except Exception as e:
            logger.warning(f'본문 입력 실패: {e}')

    def _publish(self) -> None:
        try:
            btn = self._wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.publish_btn, .btn_publish'))
            )
            btn.click()
            time.sleep(2)
            confirm = self._wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.btn_confirm, .confirm'))
            )
            confirm.click()
            time.sleep(3)
        except Exception as e:
            logger.warning(f'발행 처리 중 오류: {e}')
