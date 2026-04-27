import os
import google.generativeai as genai
from dotenv import load_dotenv
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError('GEMINI_API_KEY 환경변수가 설정되지 않았습니다.')
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel('gemini-1.5-flash')
        logger.info('Gemini 모델 초기화 완료')
    return _model


def generate_blog_post(product: dict, tone: str = 'friendly', keywords: list[str] | None = None) -> dict:
    """상품 정보를 바탕으로 블로그 포스팅을 생성합니다."""
    logger.info(f'블로그 포스팅 생성 시작: {product.get("title", "")}')

    keyword_str = ', '.join(keywords) if keywords else product.get('title', '')

    prompt = f"""
당신은 네이버 블로그 마케팅 전문가입니다.
아래 상품 정보를 바탕으로 SEO에 최적화된 네이버 블로그 포스팅을 작성해주세요.

[상품 정보]
- 상품명: {product.get('title', '')}
- 가격: {product.get('price', '')}
- 설명: {product.get('description', '')}
- 상품 URL: {product.get('url', '')}
- 키워드: {keyword_str}

[작성 조건]
- 말투: {_tone_description(tone)}
- 분량: 800~1200자
- 구성: 도입부(흥미 유발) → 상품 특징(3가지 이상) → 사용 후기 형식 → 구매 안내
- 네이버 블로그 SEO를 위해 키워드를 자연스럽게 포함
- 제목은 클릭률을 높이는 매력적인 문구로 작성
- HTML 태그 없이 순수 텍스트로 작성

[출력 형식]
제목: (제목 내용)
---
(본문 내용)
"""

    model = _get_model()
    response = model.generate_content(prompt)
    text = response.text.strip()

    title, body = _parse_response(text, product.get('title', ''))
    logger.info(f'블로그 포스팅 생성 완료: {title}')
    return {'title': title, 'body': body}


def _tone_description(tone: str) -> str:
    tones = {
        'friendly': '친근하고 편안한 말투 (~해요, ~예요)',
        'formal': '정중하고 전문적인 말투 (~합니다, ~입니다)',
        'excited': '열정적이고 흥미로운 말투 (감탄사 적절히 사용)',
    }
    return tones.get(tone, tones['friendly'])


def _parse_response(text: str, fallback_title: str) -> tuple[str, str]:
    lines = text.split('\n')
    title = fallback_title
    body_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('제목:'):
            title = stripped.replace('제목:', '').strip()
            body_start = i + 1
            break

    body_lines = []
    for line in lines[body_start:]:
        if line.strip() == '---':
            continue
        body_lines.append(line)

    body = '\n'.join(body_lines).strip()
    return title, body
