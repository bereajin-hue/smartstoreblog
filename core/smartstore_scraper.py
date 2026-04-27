import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from utils.logger import get_logger

logger = get_logger(__name__)

IMAGE_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'images')

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/123.0.0.0 Safari/537.36'
    )
}


class SmartStoreScraper:

    def parse_product(self, url: str) -> dict:
        """네이버 스마트스토어 상품 페이지에서 정보를 파싱합니다."""
        logger.info(f'상품 페이지 파싱 시작: {url}')
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'lxml')

        title = self._extract_title(soup)
        price = self._extract_price(soup)
        description = self._extract_description(soup)
        image_urls = self._extract_image_urls(soup, url)

        logger.info(f'파싱 완료 - 상품명: {title}, 이미지 수: {len(image_urls)}')
        return {
            'url': url,
            'title': title,
            'price': price,
            'description': description,
            'images': image_urls,
        }

    def download_images(self, image_urls: list[str], max_count: int = 3) -> list[str]:
        """이미지 URL 목록에서 최대 max_count장을 로컬에 저장하고 경로 목록을 반환합니다."""
        os.makedirs(IMAGE_DIR, exist_ok=True)
        paths = []
        for i, url in enumerate(image_urls[:max_count]):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=10)
                resp.raise_for_status()
                ext = self._guess_ext(url)
                filename = f'img_{i}{ext}'
                path = os.path.join(IMAGE_DIR, filename)
                with open(path, 'wb') as f:
                    f.write(resp.content)
                paths.append(path)
                logger.info(f'이미지 다운로드: {filename}')
            except Exception as e:
                logger.warning(f'이미지 다운로드 실패 ({url}): {e}')
        return paths

    # ── 내부 파싱 헬퍼 ────────────────────────────────────────────────────────

    def _extract_title(self, soup: BeautifulSoup) -> str:
        tag = soup.find('h3', {'class': re.compile(r'productName', re.I)})
        if tag:
            return tag.get_text(strip=True)
        tag = soup.find('meta', {'property': 'og:title'})
        if tag:
            return tag.get('content', '').strip()
        return ''

    def _extract_price(self, soup: BeautifulSoup) -> str:
        tag = soup.find('span', {'class': re.compile(r'price|Price', re.I)})
        if tag:
            numbers = re.sub(r'[^\d]', '', tag.get_text())
            if numbers:
                return f'{int(numbers):,}원'
        return ''

    def _extract_description(self, soup: BeautifulSoup) -> str:
        tag = (
            soup.find('meta', {'name': 'description'})
            or soup.find('meta', {'property': 'og:description'})
        )
        if tag:
            return tag.get('content', '').strip()
        return ''

    def _extract_image_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        images: list[str] = []

        og = soup.find('meta', {'property': 'og:image'})
        if og and og.get('content'):
            images.append(og['content'])

        parsed = urlparse(base_url)
        for img in soup.find_all('img', src=True):
            src = img['src']
            if src.startswith('//'):
                src = f'{parsed.scheme}:{src}'
            elif not src.startswith('http'):
                src = f'{parsed.scheme}://{parsed.netloc}{src}'
            if src not in images and self._is_product_image(src):
                images.append(src)
            if len(images) >= 10:
                break

        return images

    def _is_product_image(self, url: str) -> bool:
        exclude = ['logo', 'icon', 'banner', 'button', 'blank', 'pixel', 'loading']
        lower = url.lower()
        return not any(p in lower for p in exclude)

    def _guess_ext(self, url: str) -> str:
        lower = url.lower().split('?')[0]
        for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
            if lower.endswith(ext):
                return ext
        return '.jpg'
