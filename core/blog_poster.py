import os
import pickle
import time
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from utils.logger import get_logger

logger = get_logger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
_COOKIE_PATH = os.path.join(_DATA_DIR, 'session_cookies.pkl')
_LOGIN_URL      = 'https://nid.naver.com/nidlogin.login'
_BLOG_WRITE_URL = 'https://blog.naver.com/{blog_id}/postwrite'

# 스마트에디터 ONE CSS 셀렉터
_SEL_TITLE   = '.se-title-input'
_SEL_BODY    = '.se-main-container'
_SEL_TAG     = '.se-tag-input'
_SEL_PUBLISH = 'button.publish_btn__c2BTq, button[class*="publish_btn"], .se-publish-btn'
_SEL_CONFIRM = 'button.confirm_btn__lzR-E, button[class*="confirm_btn"]'


class NaverBlogPoster:

    def __init__(self) -> None:
        options = Options()
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument(
            '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/123.0.0.0 Safari/537.36'
        )
        options.add_argument('--window-size=1280,900')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        # headless=False: 캡차/2차인증을 사용자가 브라우저에서 직접 처리

        service = Service(ChromeDriverManager().install())
        self._driver = webdriver.Chrome(service=service, options=options)
        self._driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # 세션 쿠키 자동 로드
        if os.path.exists(_COOKIE_PATH):
            self._load_cookies()

    # ── 로그인 ────────────────────────────────────────────────────────────────

    def login(self, naver_id: str, naver_pw: str) -> bool:
        # 1. 저장된 쿠키로 세션 복원 시도
        if os.path.exists(_COOKIE_PATH):
            if self._validate_session():
                logger.info('저장된 세션으로 로그인 성공')
                return True
            logger.info('저장된 세션 만료 — 재로그인 진행')

        # 2. 로그인 페이지 접속
        self._driver.get(_LOGIN_URL)
        wait = WebDriverWait(self._driver, 15)
        try:
            wait.until(EC.presence_of_element_located((By.ID, 'id')))
        except TimeoutException:
            logger.error('로그인 페이지 로드 실패')
            return False

        # 3. JS로 ID/PW 주입 (키보드 이벤트 우회)
        self._driver.execute_script(
            "document.getElementById('id').value = arguments[0]", naver_id
        )
        self._driver.execute_script(
            "document.getElementById('pw').value = arguments[0]", naver_pw
        )
        time.sleep(0.5)

        # 4. 로그인 버튼 클릭
        try:
            self._driver.find_element(By.ID, 'log.login').click()
        except NoSuchElementException:
            try:
                self._driver.find_element(By.CSS_SELECTOR, '.btn_login').click()
            except NoSuchElementException:
                logger.error('로그인 버튼을 찾을 수 없습니다.')
                return False

        # 5. 최대 90초 대기 — 캡차·2차인증은 사용자가 브라우저에서 직접 처리
        logger.info('캡차가 표시된 경우 브라우저에서 직접 완료해 주세요.')
        try:
            WebDriverWait(self._driver, 90).until(
                lambda d: 'naver.com' in d.current_url and 'nidlogin' not in d.current_url
            )
        except TimeoutException:
            logger.error('로그인 대기 시간 초과 (90초)')
            return False

        # 6. 쿠키 저장
        self._save_cookies()
        logger.info(f'네이버 로그인 성공: {naver_id}')
        return True

    # ── 포스팅 ────────────────────────────────────────────────────────────────

    def post_to_blog(
        self,
        blog_id: str,
        title: str,
        body: str,
        tags: list | None = None,
        image_paths: list | None = None,
    ) -> bool:
        tags = tags or []
        image_paths = image_paths or []
        wait = WebDriverWait(self._driver, 20)

        try:
            # 1. 글쓰기 페이지 접속
            self._driver.get(_BLOG_WRITE_URL.format(blog_id=blog_id))
            time.sleep(3)

            # 2. 스마트에디터 ONE iframe 진입 — 에디터 본문이 실제로 렌더될 때까지 대기
            wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'mainFrame')))
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _SEL_BODY)))

            # 3. 제목 입력
            self._input_title(wait, title)

            # 4. 본문 입력
            self._input_body(wait, body)

            # 5. 이미지 업로드
            if image_paths:
                self._upload_images(wait, image_paths)

            # 6. 태그 입력
            if tags:
                self._input_tags(wait, tags)

            # 7. 발행
            self._driver.switch_to.default_content()
            return self._publish(wait)

        except Exception as e:
            self._save_screenshot(f'error_{_now_str()}')
            logger.error(f'포스팅 중 예외 발생: {e}')
            return False

    def quit(self) -> None:
        try:
            self._save_cookies()
        except Exception:
            pass
        try:
            self._driver.quit()
        except Exception:
            pass

    # ── 세션 쿠키 ─────────────────────────────────────────────────────────────

    def _save_cookies(self) -> None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_COOKIE_PATH, 'wb') as f:
            pickle.dump(self._driver.get_cookies(), f)
        logger.info('세션 쿠키를 저장했습니다.')

    def _load_cookies(self) -> None:
        # 쿠키를 심으려면 같은 도메인에 먼저 접속해야 함
        self._driver.get('https://www.naver.com')
        try:
            with open(_COOKIE_PATH, 'rb') as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                # 만료된 쿠키 키 제거 (selenium 호환)
                cookie.pop('expiry', None)
                try:
                    self._driver.add_cookie(cookie)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f'쿠키 로드 실패: {e}')

    def _validate_session(self) -> bool:
        self._driver.get('https://www.naver.com')
        time.sleep(2)
        # 로그인 상태면 gnb_my_namebadge 또는 MyView 버튼이 존재
        try:
            self._driver.find_element(
                By.CSS_SELECTOR,
                '#gnb_my_namebadge, .MyView-module__gnb_my_namebadge___Q-DWQ'
            )
            return True
        except NoSuchElementException:
            return False

    # ── 에디터 헬퍼 ───────────────────────────────────────────────────────────

    def _input_title(self, wait: WebDriverWait, title: str) -> None:
        try:
            el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, _SEL_TITLE)))
            el.click()
            el.send_keys(title)
            logger.info('제목 입력 완료')
        except Exception as e:
            logger.warning(f'제목 입력 실패: {e}')

    def _input_body(self, wait: WebDriverWait, body: str) -> None:
        try:
            el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, _SEL_BODY)))
            el.click()
            html_body = body.replace('\n', '<br>')
            self._driver.execute_script(
                "arguments[0].innerHTML = arguments[1]", el, html_body
            )
            logger.info('본문 입력 완료')
        except Exception as e:
            logger.warning(f'본문 입력 실패: {e}')

    def _upload_images(self, wait: WebDriverWait, image_paths: list) -> None:
        try:
            # 파일 첨부 input (숨겨진 요소이므로 JS로 display 변경 후 전달)
            file_input = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, 'input[type="file"][accept*="image"]')
            ))
            self._driver.execute_script("arguments[0].style.display='block'", file_input)
            file_input.send_keys('\n'.join(image_paths))
            time.sleep(2)
            logger.info(f'이미지 {len(image_paths)}장 업로드 요청')
        except Exception as e:
            logger.warning(f'이미지 업로드 실패: {e}')

    def _input_tags(self, wait: WebDriverWait, tags: list) -> None:
        try:
            tag_input = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, _SEL_TAG)
            ))
            for tag in tags[:10]:
                tag_input.click()
                tag_input.send_keys(tag)
                from selenium.webdriver.common.keys import Keys
                tag_input.send_keys(Keys.RETURN)
                time.sleep(0.3)
            logger.info(f'태그 {len(tags)}개 입력 완료')
        except Exception as e:
            logger.warning(f'태그 입력 실패: {e}')

    def _publish(self, wait: WebDriverWait) -> bool:
        try:
            # 발행 버튼
            publish_btn = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, _SEL_PUBLISH)
            ))
            publish_btn.click()
            time.sleep(2)

            # 발행 확인 모달 (있을 때만)
            try:
                confirm_btn = WebDriverWait(self._driver, 8).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, _SEL_CONFIRM))
                )
                confirm_btn.click()
            except TimeoutException:
                pass  # 모달 없이 바로 발행되는 케이스

            time.sleep(3)
            logger.info(f'포스팅 발행 완료: {self._driver.current_url}')
            return True
        except Exception as e:
            self._save_screenshot(f'publish_fail_{_now_str()}')
            logger.error(f'발행 실패: {e}')
            return False

    # ── 유틸리티 ─────────────────────────────────────────────────────────────

    def _save_screenshot(self, name: str) -> None:
        os.makedirs(_DATA_DIR, exist_ok=True)
        path = os.path.join(_DATA_DIR, f'{name}.png')
        try:
            self._driver.save_screenshot(path)
            logger.info(f'스크린샷 저장: {path}')
        except Exception as e:
            logger.warning(f'스크린샷 저장 실패: {e}')


def _now_str() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')
