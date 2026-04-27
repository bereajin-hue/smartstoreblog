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


def scrape_product(url: str) -> dict:
    """네이버 스마트스토어 상품 페이지에서 정보를 파싱합니다."""
    logger.info(f'상품 페이지 파싱 시작: {url}')
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'lxml')

    title = _extract_title(soup)
    price = _extract_price(soup)
    description = _extract_description(soup)
    images = _extract_images(soup, url)

    logger.info(f'파싱 완료 - 상품명: {title}, 이미지 수: {len(images)}')
    return {
        'url': url,
        'title': title,
        'price': price,
        'description': description,
        'images': images,
    }


def _extract_title(soup: BeautifulSoup) -> str:
    selectors = [
        ('meta', {'property': 'og:title'}),
    ]
    tag = soup.find('h3', {'class': re.compile(r'productName')})
    if tag:
        return tag.get_text(strip=True)
    tag = soup.find('meta', {'property': 'og:title'})
    if tag:
        return tag.get('content', '').strip()
    return ''


def _extract_price(soup: BeautifulSoup) -> str:
    tag = soup.find('span', {'class': re.compile(r'price|Price')})
    if tag:
        text = tag.get_text(strip=True)
        numbers = re.sub(r'[^\d]', '', text)
        if numbers:
            return f'{int(numbers):,}원'
    return ''


def _extract_description(soup: BeautifulSoup) -> str:
    tag = soup.find('meta', {'name': 'description'}) or soup.find('meta', {'property': 'og:description'})
    if tag:
        return tag.get('content', '').strip()
    return ''


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[str]:
    os.makedirs(IMAGE_DIR, exist_ok=True)
    images = []

    og_image = soup.find('meta', {'property': 'og:image'})
    if og_image:
        src = og_image.get('content', '')
        if src:
            images.append(src)

    for img in soup.find_all('img', src=True):
        src = img['src']
        if not src.startswith('http'):
            parsed = urlparse(base_url)
            src = f'{parsed.scheme}://{parsed.netloc}{src}'
        if src not in images and _is_product_image(src):
            images.append(src)
        if len(images) >= 10:
            break

    return images


def _is_product_image(url: str) -> bool:
    exclude_patterns = ['logo', 'icon', 'banner', 'button', 'blank', 'pixel']
    lower = url.lower()
    return not any(p in lower for p in exclude_patterns)
