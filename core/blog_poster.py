import os
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
NAVER_BLOG_WRITE_URL = 'https://blog.naver.com/BlogPost.nhn'


def _build_driver(headless: bool = False) -> webdriver.Chrome:
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
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def post_to_blog(naver_id: str, naver_pw: str, title: str, body: str, images: list[str] | None = None) -> dict:
    """네이버 블로그에 포스팅을 게시합니다."""
    logger.info(f'블로그 포스팅 시작: {title}')
    driver = _build_driver(headless=False)
    wait = WebDriverWait(driver, 20)

    try:
        _login(driver, wait, naver_id, naver_pw)
        post_url = _write_post(driver, wait, naver_id, title, body, images or [])
        logger.info(f'포스팅 완료: {post_url}')
        return {'success': True, 'post_url': post_url}
    except Exception as e:
        logger.error(f'포스팅 실패: {e}')
        return {'success': False, 'error': str(e)}
    finally:
        driver.quit()


def _login(driver: webdriver.Chrome, wait: WebDriverWait, naver_id: str, naver_pw: str) -> None:
    driver.get(NAVER_LOGIN_URL)
    wait.until(EC.presence_of_element_located((By.ID, 'id')))

    id_field = driver.find_element(By.ID, 'id')
    pw_field = driver.find_element(By.ID, 'pw')

    id_field.clear()
    for ch in naver_id:
        id_field.send_keys(ch)
        time.sleep(0.05)

    pw_field.clear()
    for ch in naver_pw:
        pw_field.send_keys(ch)
        time.sleep(0.05)

    driver.find_element(By.ID, 'log.login').click()
    time.sleep(3)

    if 'nidlogin' in driver.current_url:
        raise RuntimeError('네이버 로그인에 실패했습니다. ID/PW를 확인하세요.')
    logger.info('네이버 로그인 성공')


def _write_post(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    naver_id: str,
    title: str,
    body: str,
    images: list[str],
) -> str:
    write_url = f'https://blog.naver.com/{naver_id}/postwrite'
    driver.get(write_url)
    time.sleep(3)

    # 스마트에디터 ONE iframe으로 전환
    wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, 'mainFrame')))
    time.sleep(2)

    # 제목 입력
    try:
        title_el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.se-title-input')))
        title_el.click()
        title_el.send_keys(title)
    except Exception:
        logger.warning('제목 필드를 찾지 못했습니다.')

    # 본문 입력
    try:
        body_el = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.se-content')))
        body_el.click()
        driver.execute_script(
            "arguments[0].innerText = arguments[1]", body_el, body
        )
    except Exception:
        logger.warning('본문 필드를 찾지 못했습니다.')

    time.sleep(1)

    # 발행 버튼
    driver.switch_to.default_content()
    try:
        publish_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.publish_btn, .btn_publish')))
        publish_btn.click()
        time.sleep(2)

        confirm_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.btn_confirm, .confirm')))
        confirm_btn.click()
        time.sleep(3)
    except Exception as e:
        logger.warning(f'발행 버튼 처리 중 오류: {e}')

    return driver.current_url
