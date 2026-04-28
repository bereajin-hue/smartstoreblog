import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from utils.logger import get_logger

logger = get_logger(__name__)

_IMAGE_BASE = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')

_SESSION_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/123.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
}


class SmartStoreScraper:

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_SESSION_HEADERS)
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            logger.info('스크래퍼용 Chrome(헤드리스) 시작 중...')
            options = Options()
            options.add_argument('--headless=new')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument(
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
            )
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1280,900')
            self._driver = webdriver.Chrome(options=options)  # selenium-manager 자동 관리
            logger.info('스크래퍼 Chrome 시작 완료')
        return self._driver

    def quit(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def validate_url(self, url: str) -> bool:
        return 'smartstore.naver.com' in url

    def parse_product(self, url: str) -> dict:
        if not self.validate_url(url):
            raise ValueError(f'스마트스토어 URL이 아닙니다: {url}')

        logger.info(f'상품 파싱 시작 (Selenium): {url}')
        driver = self._get_driver()
        driver.get(url)
        time.sleep(4)  # JS 렌더링 대기

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # JSON-LD에서 구조화된 데이터 추출 시도
        ld = self._parse_json_ld(soup)

        product = {
            'product_name':       self._product_name(soup, ld),
            'price':              self._price(soup, ld),
            'original_price':     self._original_price(soup),
            'discount_rate':      self._discount_rate(soup),
            'store_name':         self._store_name(soup, ld),
            'category':           self._category(soup, ld),
            'description':        self._description(soup, ld),
            'tags':               self._tags(soup),
            'shipping_info':      self._shipping_info(soup),
            'detail_image_urls':  self._detail_image_urls(soup, url, ld),
            'thumbnail_url':      self._thumbnail_url(soup, ld),
            'product_url':        url,
        }

        logger.info(
            f'파싱 완료 - {product["product_name"]} | '
            f'{product["price"]} | 이미지 {len(product["detail_image_urls"])}장'
        )
        return product

    def download_images(self, image_urls: list, product_name: str) -> list[str]:
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', product_name)[:50]
        save_dir = os.path.join(_IMAGE_BASE, safe_name)
        os.makedirs(save_dir, exist_ok=True)

        _CONTENT_TYPE_EXT = {
            'image/jpeg': 'jpg', 'image/png': 'png',
            'image/webp': 'webp', 'image/gif': 'gif',
        }

        paths: list[str] = []
        for i, url in enumerate(image_urls[:3]):
            try:
                resp = self._session.get(url, timeout=10)
                resp.raise_for_status()
                ct = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()
                if ct not in _CONTENT_TYPE_EXT:
                    ct = self._guess_ct(url)
                ext = _CONTENT_TYPE_EXT.get(ct, 'jpg')
                path = os.path.join(save_dir, f'{i:02d}.{ext}')
                with open(path, 'wb') as f:
                    f.write(resp.content)
                paths.append(path)
                logger.info(f'이미지 저장: {path}')
            except Exception as e:
                logger.warning(f'이미지 다운로드 실패 ({url}): {e}')
        return paths

    def _guess_ct(self, url: str) -> str:
        lower = url.lower().split('?')[0]
        if lower.endswith('.png'):  return 'image/png'
        if lower.endswith('.webp'): return 'image/webp'
        if lower.endswith('.gif'):  return 'image/gif'
        return 'image/jpeg'

    # ── JSON-LD 파싱 ──────────────────────────────────────────────────────────

    def _parse_json_ld(self, soup: BeautifulSoup) -> dict:
        for tag in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(tag.string or '')
                if isinstance(data, list):
                    data = next((d for d in data if d.get('@type') == 'Product'), {})
                if data.get('@type') == 'Product':
                    return data
            except Exception:
                pass
        return {}

    # ── 파싱 헬퍼 ─────────────────────────────────────────────────────────────

    def _product_name(self, soup: BeautifulSoup, ld: dict) -> str:
        if ld.get('name'):
            return ld['name']
        for sel in [
            ('h3', re.compile(r'productName', re.I)),
            ('h2', re.compile(r'product.*name|title', re.I)),
        ]:
            tag = soup.find(sel[0], {'class': sel[1]})
            if tag:
                return tag.get_text(strip=True)
        og = soup.find('meta', {'property': 'og:title'})
        return og['content'].strip() if og else ''

    def _price(self, soup: BeautifulSoup, ld: dict) -> str:
        if ld.get('offers'):
            offers = ld['offers']
            if isinstance(offers, list):
                offers = offers[0]
            price = offers.get('price', '')
            if price:
                return f'{int(float(price)):,}원'
        for cls in [re.compile(r'salePrice|sale_price', re.I), re.compile(r'price', re.I)]:
            tag = soup.find('span', {'class': cls})
            if tag:
                n = re.sub(r'[^\d]', '', tag.get_text())
                if n:
                    return f'{int(n):,}원'
        return ''

    def _original_price(self, soup: BeautifulSoup) -> str:
        tag = soup.find('span', {'class': re.compile(r'costPrice|original.*price|before.*price', re.I)})
        if tag:
            n = re.sub(r'[^\d]', '', tag.get_text())
            if n:
                return f'{int(n):,}원'
        return ''

    def _discount_rate(self, soup: BeautifulSoup) -> str:
        tag = soup.find('span', {'class': re.compile(r'discount|rate|percent', re.I)})
        if tag:
            m = re.search(r'\d+', tag.get_text(strip=True))
            if m:
                return f'{m.group()}%'
        return ''

    def _store_name(self, soup: BeautifulSoup, ld: dict) -> str:
        if ld.get('brand', {}).get('name'):
            return ld['brand']['name']
        tag = soup.find('a', {'class': re.compile(r'storeName|store.*name', re.I)})
        if tag:
            return tag.get_text(strip=True)
        og_site = soup.find('meta', {'property': 'og:site_name'})
        return og_site['content'].strip() if og_site else ''

    def _category(self, soup: BeautifulSoup, ld: dict) -> str:
        if ld.get('category'):
            return ld['category']
        breadcrumb = soup.find('ol', {'class': re.compile(r'breadcrumb|category', re.I)})
        if breadcrumb:
            items = [li.get_text(strip=True) for li in breadcrumb.find_all('li')]
            return ' > '.join(items) if items else ''
        return ''

    def _description(self, soup: BeautifulSoup, ld: dict) -> str:
        if ld.get('description'):
            return ld['description']
        for attr in [{'name': 'description'}, {'property': 'og:description'}]:
            tag = soup.find('meta', attr)
            if tag and tag.get('content'):
                return tag['content'].strip()
        return ''

    def _tags(self, soup: BeautifulSoup) -> list[str]:
        tag = soup.find('meta', {'name': 'keywords'})
        if tag and tag.get('content'):
            return [t.strip() for t in tag['content'].split(',') if t.strip()]
        return []

    def _shipping_info(self, soup: BeautifulSoup) -> str:
        tag = soup.find(class_=re.compile(r'shipping|delivery', re.I))
        if tag:
            return tag.get_text(separator=' ', strip=True)[:100]
        return ''

    def _detail_image_urls(self, soup: BeautifulSoup, base_url: str, ld: dict) -> list[str]:
        parsed = urlparse(base_url)
        seen: set[str] = set()
        urls: list[str] = []

        def _add(src: str) -> None:
            if not src:
                return
            if src.startswith('//'):
                src = f'{parsed.scheme}:{src}'
            elif not src.startswith('http'):
                src = f'{parsed.scheme}://{parsed.netloc}/{src.lstrip("/")}'
            if src not in seen and self._is_product_image(src):
                seen.add(src)
                urls.append(src)

        # JSON-LD 이미지 우선
        for img_url in (ld.get('image') or []):
            if isinstance(img_url, str):
                _add(img_url)
            elif isinstance(img_url, dict):
                _add(img_url.get('url', ''))

        og = soup.find('meta', {'property': 'og:image'})
        if og:
            _add(og.get('content', ''))

        for img in soup.find_all('img', src=True):
            _add(img['src'])
            if len(urls) >= 10:
                break

        return urls

    def _thumbnail_url(self, soup: BeautifulSoup, ld: dict) -> str:
        imgs = ld.get('image', [])
        if imgs:
            first = imgs[0] if isinstance(imgs[0], str) else imgs[0].get('url', '')
            if first:
                return first
        og = soup.find('meta', {'property': 'og:image'})
        if og:
            return og.get('content', '')
        img = soup.find('img', src=True)
        return img['src'] if img else ''

    def _is_product_image(self, url: str) -> bool:
        lower = url.lower()
        exclude = ['logo', 'icon', 'banner', 'button', 'blank', 'pixel', 'loading', 'spinner']
        return not any(p in lower for p in exclude)
