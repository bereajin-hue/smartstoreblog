import json
import re
import google.generativeai as genai
from utils.logger import get_logger

logger = get_logger(__name__)

_PROMPT_TEMPLATE = """당신은 패션·라이프스타일 전문 블로거입니다.
아래 상품 정보를 바탕으로 네이버 블로그 포스팅을 작성해주세요.

[상품 정보]
- 상품명: {product_name}
- 판매가: {price}
- 정가: {original_price}
- 할인율: {discount_rate}
- 스토어: {store_name}
- 카테고리: {category}
- 설명: {description}
- 상품 URL: {product_url}

[작성 규칙]
- 1000자 내외
- 전문가 어조, 읽기 쉽게
- 이모지는 문단 시작에만 사용 (3~5개)
- 구성: 도입 → 주요기능/장점 → 가격정보 → CTA
- 마지막 줄 반드시 포함: 👉 [지금 바로 구매하기]({product_url})
- 반환은 아래 JSON만 출력하고 다른 텍스트는 절대 포함하지 마세요

[출력 JSON 형식]
{{
  "title": "블로그 포스팅 제목",
  "body": "포스팅 본문 전체",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"]
}}"""


class GeminiWriter:

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError('Gemini API 키가 설정되지 않았습니다.')
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel('gemini-1.5-flash')
        logger.info('GeminiWriter 초기화 완료')

    def generate_post(self, product_info: dict) -> dict:
        """상품 정보를 받아 {title, body, tags} 딕셔너리를 반환합니다."""
        name = product_info.get('product_name', '')
        logger.info(f'포스팅 생성 시작: {name}')

        prompt = _PROMPT_TEMPLATE.format(
            product_name=name,
            price=product_info.get('price', ''),
            original_price=product_info.get('original_price', ''),
            discount_rate=product_info.get('discount_rate', ''),
            store_name=product_info.get('store_name', ''),
            category=product_info.get('category', ''),
            description=product_info.get('description', ''),
            product_url=product_info.get('product_url', ''),
        )

        try:
            response = self._model.generate_content(prompt)
            raw = response.text.strip()
        except Exception as e:
            logger.error(f'Gemini API 호출 실패: {e}')
            raise

        result = self._parse_json(raw)
        logger.info(f'포스팅 생성 완료: {result.get("title", "")}')
        return result

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _parse_json(self, raw: str) -> dict:
        # 코드 블록 마크다운 제거
        cleaned = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # JSON 블록만 추출 재시도
            m = re.search(r'\{.*\}', cleaned, re.DOTALL)
            if not m:
                logger.error(f'JSON 파싱 실패. 원본 응답:\n{raw}')
                raise ValueError('Gemini 응답에서 JSON을 추출할 수 없습니다.')
            try:
                data = json.loads(m.group())
            except json.JSONDecodeError as e:
                logger.error(f'JSON 파싱 실패: {e}\n원본:\n{raw}')
                raise ValueError(f'Gemini 응답 JSON 파싱 오류: {e}') from e

        title = str(data.get('title', '')).strip()
        body = str(data.get('body', '')).strip()
        tags = [str(t).strip() for t in data.get('tags', []) if str(t).strip()][:5]

        if not title or not body:
            logger.error(f'필수 필드 누락 (title/body). 원본:\n{raw}')
            raise ValueError('Gemini 응답에 title 또는 body가 없습니다.')

        return {'title': title, 'body': body, 'tags': tags}
