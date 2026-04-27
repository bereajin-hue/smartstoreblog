import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from core.credential_manager import save_credentials, load_credentials, delete_credentials
from core.smartstore_scraper import scrape_product
from core.gemini_writer import generate_blog_post
from core.blog_poster import post_to_blog
from utils.logger import get_logger

load_dotenv()
logger = get_logger(__name__)

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)


# ── 정적 파일 ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')


# ── 자격증명 ───────────────────────────────────────────────────────────────────

@app.route('/api/credentials', methods=['GET'])
def get_credentials():
    creds = load_credentials()
    safe = {k: ('●' * 6 if 'pw' in k.lower() or 'password' in k.lower() else v) for k, v in creds.items()}
    return jsonify({'ok': True, 'data': safe})


@app.route('/api/credentials', methods=['POST'])
def set_credentials():
    data = request.get_json(force=True)
    if not data:
        return jsonify({'ok': False, 'error': '요청 데이터가 없습니다.'}), 400
    save_credentials(data)
    return jsonify({'ok': True, 'message': '자격증명이 저장되었습니다.'})


@app.route('/api/credentials', methods=['DELETE'])
def remove_credentials():
    delete_credentials()
    return jsonify({'ok': True, 'message': '자격증명이 삭제되었습니다.'})


# ── 상품 파싱 ──────────────────────────────────────────────────────────────────

@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.get_json(force=True)
    url = (data or {}).get('url', '').strip()
    if not url:
        return jsonify({'ok': False, 'error': '상품 URL을 입력하세요.'}), 400
    try:
        product = scrape_product(url)
        return jsonify({'ok': True, 'data': product})
    except Exception as e:
        logger.error(f'스크래핑 오류: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── 블로그 포스팅 생성 ──────────────────────────────────────────────────────────

@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.get_json(force=True) or {}
    product = data.get('product')
    if not product:
        return jsonify({'ok': False, 'error': '상품 정보가 없습니다.'}), 400

    tone = data.get('tone', 'friendly')
    keywords = data.get('keywords', [])

    try:
        post = generate_blog_post(product, tone=tone, keywords=keywords)
        return jsonify({'ok': True, 'data': post})
    except Exception as e:
        logger.error(f'포스팅 생성 오류: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── 블로그 게시 ────────────────────────────────────────────────────────────────

@app.route('/api/post', methods=['POST'])
def post():
    data = request.get_json(force=True) or {}
    title = data.get('title', '').strip()
    body = data.get('body', '').strip()
    images = data.get('images', [])

    if not title or not body:
        return jsonify({'ok': False, 'error': '제목과 본문이 필요합니다.'}), 400

    creds = load_credentials()
    naver_id = creds.get('naver_id', '')
    naver_pw = creds.get('naver_pw', '')

    if not naver_id or not naver_pw:
        return jsonify({'ok': False, 'error': '네이버 로그인 정보를 먼저 저장하세요.'}), 400

    try:
        result = post_to_blog(naver_id, naver_pw, title, body, images)
        if result['success']:
            return jsonify({'ok': True, 'post_url': result.get('post_url', '')})
        return jsonify({'ok': False, 'error': result.get('error', '알 수 없는 오류')}), 500
    except Exception as e:
        logger.error(f'블로그 게시 오류: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── 전체 자동화 파이프라인 ──────────────────────────────────────────────────────

@app.route('/api/automate', methods=['POST'])
def automate():
    data = request.get_json(force=True) or {}
    url = data.get('url', '').strip()
    tone = data.get('tone', 'friendly')
    keywords = data.get('keywords', [])

    if not url:
        return jsonify({'ok': False, 'error': '상품 URL을 입력하세요.'}), 400

    try:
        logger.info('전체 자동화 파이프라인 시작')
        product = scrape_product(url)
        post = generate_blog_post(product, tone=tone, keywords=keywords)

        creds = load_credentials()
        naver_id = creds.get('naver_id', '')
        naver_pw = creds.get('naver_pw', '')

        if not naver_id or not naver_pw:
            return jsonify({
                'ok': False,
                'error': '네이버 로그인 정보를 먼저 저장하세요.',
                'product': product,
                'post': post,
            }), 400

        result = post_to_blog(naver_id, naver_pw, post['title'], post['body'], product.get('images', []))
        return jsonify({
            'ok': result['success'],
            'product': product,
            'post': post,
            'post_url': result.get('post_url', ''),
            'error': result.get('error', ''),
        })
    except Exception as e:
        logger.error(f'자동화 파이프라인 오류: {e}')
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    logger.info('Flask 서버 시작 - http://localhost:5000')
    app.run(host='0.0.0.0', port=5000, debug=True)
