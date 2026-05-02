import os
import re
import threading
import webbrowser
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from core.credential_manager import CredentialManager
from core.smartstore_scraper import SmartStoreScraper
from core.claude_writer import ClaudeWriter
from core.blog_poster import NaverBlogPoster
from utils.logger import get_logger

# .env 로드 (모듈 임포트 전에 환경변수 준비)
load_dotenv()

logger = get_logger(__name__)

app = Flask(__name__, static_folder='frontend', static_url_path='')
CORS(app)

LOG_FILE = os.path.join(os.path.dirname(__file__), 'data', 'app.log')

# 전역 포스팅 작업 상태
posting_job: dict = {
    'running': False,
    'stop_event': threading.Event(),
    'thread': None,
    'current_url': '',
    'progress': 0,
    'step': '',
    'done_count': 0,
    'total_count': 0,
}


# ── 정적 파일 ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')


# ── 자격증명 ───────────────────────────────────────────────────────────────────

@app.route('/api/credentials/save', methods=['POST'])
def credentials_save():
    try:
        new_data = request.get_json(force=True) or {}
        if not new_data:
            return jsonify({'success': False, 'error': '요청 데이터가 없습니다.'}), 400

        # 기존 값에 새 값을 병합 (카드별 개별 저장 지원)
        cm = CredentialManager()
        existing = cm.load()
        existing.update({k: v for k, v in new_data.items() if v})
        cm.save(existing)
        logger.info(f'자격증명 저장 완료: {list(new_data.keys())}')
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'자격증명 저장 오류: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/credentials/load', methods=['GET'])
def credentials_load():
    try:
        creds = CredentialManager().load()
        masked = {
            k: ('••••••••' if any(w in k.lower() for w in ('pw', 'password', 'secret', 'key')) else v)
            for k, v in creds.items()
        }
        return jsonify(masked)
    except Exception as e:
        logger.error(f'자격증명 로드 오류: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ── 포스팅 제어 ────────────────────────────────────────────────────────────────

@app.route('/api/posting/start', methods=['POST'])
def posting_start():
    try:
        if posting_job['running']:
            return jsonify({'success': False, 'error': '이미 포스팅이 실행 중입니다.'}), 409

        data = request.get_json(force=True) or {}
        urls = data.get('urls', [])
        if not urls:
            return jsonify({'success': False, 'error': 'URL 목록이 비어 있습니다.'}), 400

        posting_job['stop_event'].clear()
        posting_job['done_count'] = 0
        posting_job['total_count'] = len(urls)
        posting_job['progress'] = 0
        posting_job['step'] = '시작 중...'
        posting_job['current_url'] = ''

        t = threading.Thread(target=_run_posting, args=(urls,), daemon=True)
        posting_job['thread'] = t
        posting_job['running'] = True
        t.start()

        logger.info(f'포스팅 작업 시작 - 총 {len(urls)}개 URL')
        return jsonify({'success': True, 'message': '포스팅 시작됨'})
    except Exception as e:
        logger.error(f'포스팅 시작 오류: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/posting/stop', methods=['POST'])
def posting_stop():
    try:
        posting_job['stop_event'].set()
        logger.info('포스팅 중단 요청')
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'포스팅 중단 오류: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/posting/status', methods=['GET'])
def posting_status():
    return jsonify({
        'running': posting_job['running'],
        'current_url': posting_job['current_url'],
        'progress': posting_job['progress'],
        'step': posting_job['step'],
        'done_count': posting_job['done_count'],
        'total_count': posting_job['total_count'],
    })


# ── 로그 ───────────────────────────────────────────────────────────────────────

@app.route('/api/logs', methods=['GET'])
def get_logs():
    try:
        level_filter = request.args.get('level', 'ALL').upper()
        limit = min(int(request.args.get('limit', 200)), 1000)

        if not os.path.exists(LOG_FILE):
            return jsonify({'logs': []})

        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 최신 줄부터 limit 개 처리
        recent = lines[-limit:] if len(lines) > limit else lines

        log_pattern = re.compile(
            r'\[(?P<time>[^\]]+)\]\s+(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+(?P<msg>.*)'
        )
        entries = []
        for line in recent:
            line = line.strip()
            if not line:
                continue
            m = log_pattern.match(line)
            if m:
                entry = m.groupdict()
            else:
                entry = {'time': '', 'level': 'INFO', 'msg': line}

            if level_filter == 'ALL' or entry['level'] == level_filter:
                entries.append(entry)

        return jsonify({'logs': entries})
    except Exception as e:
        logger.error(f'로그 조회 오류: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/logs', methods=['DELETE'])
def clear_logs():
    try:
        if os.path.exists(LOG_FILE):
            open(LOG_FILE, 'w').close()
        logger.info('로그 파일 초기화')
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f'로그 삭제 오류: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


# ── 포스팅 워커 ────────────────────────────────────────────────────────────────

def _update_status(step: str, done: int, total: int, current_url: str = '') -> None:
    posting_job['step'] = step
    posting_job['done_count'] = done
    posting_job['current_url'] = current_url
    posting_job['progress'] = int(done / total * 100) if total else 0


def _run_posting(urls: list[str]) -> None:
    total = len(urls)
    creds = CredentialManager().load()
    naver_id = creds.get('naver_id', '')
    naver_pw = creds.get('naver_pw', '')
    blog_id = creds.get('blog_id', '')
    claude_key = creds.get('claude_key', '')

    scraper = None
    try:
        # 자격증명 사전 검증
        missing = [k for k, v in [('네이버 ID', naver_id), ('비밀번호', naver_pw),
                                   ('블로그 ID', blog_id), ('Claude API 키', claude_key)] if not v]
        if missing:
            logger.error(f'자격증명 미설정: {", ".join(missing)} — 설정 탭에서 저장하세요.')
            return

        scraper = SmartStoreScraper()
        writer = ClaudeWriter(api_key=claude_key)

        for idx, url in enumerate(urls):
            if posting_job['stop_event'].is_set():
                logger.info('포스팅 중단됨 (사용자 요청)')
                break

            logger.info(f'[{idx + 1}/{total}] 처리 시작: {url}')

            # 1. 상품 파싱
            _update_status('상품 정보 파싱 중...', idx, total, url)
            try:
                product_info = scraper.parse_product(url)
                logger.info(f'상품 파싱 완료: {product_info.get("product_name", "")}')
            except Exception as e:
                logger.error(f'상품 파싱 실패 ({url}): {e}')
                continue

            if posting_job['stop_event'].is_set():
                break

            # 2. 이미지 다운로드 (최대 3장)
            _update_status('이미지 다운로드 중...', idx, total, url)
            try:
                image_paths = scraper.download_images(
                    product_info.get('detail_image_urls', []),
                    product_info.get('product_name', 'product'),
                )
                logger.info(f'이미지 {len(image_paths)}장 다운로드 완료')
            except Exception as e:
                logger.warning(f'이미지 다운로드 실패 ({url}): {e}')
                image_paths = []

            if posting_job['stop_event'].is_set():
                break

            # 3. 포스팅 생성
            _update_status('AI 포스팅 작성 중...', idx, total, url)
            try:
                post = writer.generate_post(product_info)
                logger.info(f'포스팅 생성 완료: {post.get("title", "")}')
            except Exception as e:
                logger.error(f'포스팅 생성 실패 ({url}): {e}')
                continue

            if posting_job['stop_event'].is_set():
                break

            # 4. 블로그 게시 (URL마다 새 Chrome 인스턴스)
            _update_status('블로그에 게시 중...', idx, total, url)
            poster = None
            try:
                logger.info('Chrome 브라우저를 시작합니다... (잠시 기다려 주세요)')
                poster = NaverBlogPoster()
                logger.info('Chrome 브라우저 시작 완료')
                if not poster.login(naver_id, naver_pw):
                    raise RuntimeError('네이버 로그인 실패')
                success = poster.post_to_blog(
                    blog_id=blog_id,
                    title=post['title'],
                    body=post['body'],
                    tags=post.get('tags', []),
                    image_paths=image_paths,
                )
                if not success:
                    raise RuntimeError('블로그 게시 실패')
                logger.info(f'게시 완료: {url}')
            except Exception as e:
                logger.error(f'블로그 게시 실패 ({url}): {e}')
                continue
            finally:
                if poster is not None:
                    poster.quit()

            posting_job['done_count'] = idx + 1
            _update_status(f'{idx + 1}번째 포스팅 완료', idx + 1, total, url)

    except Exception as e:
        logger.error(f'포스팅 워커 예외: {e}')
    finally:
        if scraper is not None:
            try:
                scraper.quit()
            except Exception:
                pass
        posting_job['running'] = False
        posting_job['progress'] = 100 if posting_job['done_count'] == total else posting_job['progress']
        posting_job['step'] = '완료' if not posting_job['stop_event'].is_set() else '중단됨'
        logger.info(
            f'포스팅 작업 종료 - 완료: {posting_job["done_count"]}/{total}'
        )


# ── 진입점 ─────────────────────────────────────────────────────────────────────

def _ensure_dirs() -> None:
    base = os.path.dirname(__file__)
    for path in [
        os.path.join(base, 'data'),
        os.path.join(base, 'data', 'images'),
    ]:
        os.makedirs(path, exist_ok=True)


def _open_browser() -> None:
    webbrowser.open('http://127.0.0.1:5000')


if __name__ == '__main__':
    _ensure_dirs()
    logger.info('서버 시작: http://127.0.0.1:5000')
    # use_reloader=False — 브라우저가 두 번 열리는 것 방지
    threading.Timer(1.0, _open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)
