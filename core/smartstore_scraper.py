import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
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
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


class SmartStoreScraper:

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_SESSION_HEADERS)

    # ── 공개 API ──────────────────────────────────────────────────────────────

    def validate_url(self, url: str) -> bool:
        return 'smartstore.naver.com' in url

    def parse_product(self, url: str) -> dict:
        if not self.validate_url(url):
            raise ValueError(f'스마트스토어 URL이 아닙니다: {url}')

        logger.info(f'상품 파싱 시작: {url}')
        try:
            resp = self._session.get(url, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f'상품 페이지 요청 실패: {e}')
            raise

        soup = BeautifulSoup(resp.text, 'html.parser')

        try:
            product = {
                'product_name':       self._product_name(soup),
                'price':              self._price(soup),
                'original_price':     self._original_price(soup),
                'discount_rate':      self._discount_rate(soup),
                'store_name':         self._store_name(soup),
                'category':           self._category(soup),
                'description':        self._description(soup),
                'tags':               self._tags(soup),
                'shipping_info':      self._shipping_info(soup),
                'detail_image_urls':  self._detail_image_urls(soup, url),
                'thumbnail_url':      self._thumbnail_url(soup),
                'product_url':        url,
            }
        except Exception as e:
            logger.error(f'상품 파싱 중 오류 ({url}): {e}')
            raise

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
            'image/jpeg': 'jpg',
            'image/png':  'png',
            'image/webp': 'webp',
            'image/gif':  'gif',
        }

        paths: list[str] = []
        for i, url in enumerate(image_urls[:3]):
            try:
                resp = self._session.get(url, timeout=10)
                resp.raise_for_status()

                # Content-Type으로 확장자 결정 (Pillow 불필요)
                ct = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()
                if ct not in _CONTENT_TYPE_EXT:
                    # Content-Type 없으면 URL 끝에서 추측
                    ct = self._guess_ct(url)
                ext = _CONTENT_TYPE_EXT.get(ct, 'jpg')

                filename = f'{i:02d}.{ext}'
                path = os.path.join(save_dir, filename)
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

    # ── 파싱 헬퍼 ─────────────────────────────────────────────────────────────

    def _product_name(self, soup: BeautifulSoup) -> str:
        for sel in [
            ('h3', re.compile(r'productName', re.I)),
            ('h2', re.compile(r'product.*name|title', re.I)),
        ]:
            tag = soup.find(sel[0], {'class': sel[1]})
            if tag:
                return tag.get_text(strip=True)
        og = soup.find('meta', {'property': 'og:title'})
        return og['content'].strip() if og else ''

    def _price(self, soup: BeautifulSoup) -> str:
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
            text = tag.get_text(strip=True)
            m = re.search(r'\d+', text)
            if m:
                return f'{m.group()}%'
        return ''

    def _store_name(self, soup: BeautifulSoup) -> str:
        tag = soup.find('a', {'class': re.compile(r'storeName|store.*name', re.I)})
        if tag:
            return tag.get_text(strip=True)
        og_site = soup.find('meta', {'property': 'og:site_name'})
        return og_site['content'].strip() if og_site else ''

    def _category(self, soup: BeautifulSoup) -> str:
        breadcrumb = soup.find('ol', {'class': re.compile(r'breadcrumb|category', re.I)})
        if breadcrumb:
            items = [li.get_text(strip=True) for li in breadcrumb.find_all('li')]
            return ' > '.join(items) if items else ''
        return ''

    def _description(self, soup: BeautifulSoup) -> str:
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
            text = tag.get_text(separator=' ', strip=True)
            return text[:100]
        return ''

    def _detail_image_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
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

        og = soup.find('meta', {'property': 'og:image'})
        if og:
            _add(og.get('content', ''))

        for img in soup.find_all('img', src=True):
            _add(img['src'])
            if len(urls) >= 10:
                break

        return urls

    def _thumbnail_url(self, soup: BeautifulSoup) -> str:
        og = soup.find('meta', {'property': 'og:image'})
        if og:
            return og.get('content', '')
        img = soup.find('img', src=True)
        return img['src'] if img else ''

    def _is_product_image(self, url: str) -> bool:
        lower = url.lower()
        exclude = ['logo', 'icon', 'banner', 'button', 'blank', 'pixel', 'loading', 'spinner']
        return not any(p in lower for p in exclude)
