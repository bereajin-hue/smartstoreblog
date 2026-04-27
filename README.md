# 네이버 블로그 자동 포스터

네이버 스마트스토어 상품 URL을 입력하면 Gemini AI가 블로그 포스팅을 작성하고
Selenium이 네이버 블로그에 자동으로 게시하는 자동화 도구입니다.

```
브라우저 (index.html)  ←→  Flask API (app.py)  ←→  Selenium / Gemini
      UI / 조작              localhost:5000           자동화 엔진
```

---

## 설치

### 1. Python 3.11 이상 확인

```bash
python --version
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 환경변수 설정 (선택)

```bash
cp .env.example .env
# .env 파일을 열어 GEMINI_API_KEY 등을 입력
```

> API 키는 `.env` 파일 대신 UI의 **설정 탭**에서 입력해도 됩니다.

---

## 실행

```bash
python app.py
```

- Flask 서버가 `http://127.0.0.1:5000` 에서 시작됩니다.
- **1초 후 기본 브라우저가 자동으로 열립니다.**
- 로그는 `data/app.log` 에 저장됩니다 (UI 로그 탭에서도 확인 가능).

---

## 최초 설정

브라우저에서 **설정 탭**을 열고 아래 항목을 입력한 뒤 각각 저장합니다.

| 항목 | 설명 |
|------|------|
| 네이버 아이디 | 블로그 게시에 사용할 네이버 계정 ID |
| 비밀번호 | 네이버 계정 비밀번호 |
| 블로그 ID | `blog.naver.com/` 뒤의 영문 ID |
| Gemini API Key | [Google AI Studio](https://aistudio.google.com)에서 발급 |
| 네이버 Client ID / Secret | 네이버 Open API 사용 시 (선택) |

입력값은 **Fernet 암호화**되어 `data/credentials.enc` 에 로컬 저장됩니다.

---

## 사용 방법

1. **URL 목록 탭** — 스마트스토어 상품 URL 추가 (최대 10개)
2. **포스팅 설정** — 글자 수·이미지 수·페르소나 선택
3. **포스팅 실행 탭** — 시작 버튼 클릭
4. **로그 보기 탭** — 실시간 진행 로그 확인

---

## 캡차 / 2차 인증 안내

최초 로그인 또는 세션 만료 시 네이버 보안 창이 뜰 수 있습니다.

- Selenium이 여는 **Chrome 창을 닫지 마세요.**
- 캡차 또는 2차 인증이 표시되면 **직접 완료**해 주세요.
- 완료 후 자동으로 다음 단계가 진행됩니다.
- 로그인 성공 후 세션 쿠키가 `data/session_cookies.pkl` 에 저장되어  
  이후 실행 시 재로그인 없이 사용할 수 있습니다.

---

## 폴더 구조

```
naver-blog-autoposter/
├── app.py                    # Flask API 서버 진입점
├── frontend/
│   └── index.html            # 단일 페이지 UI
├── core/
│   ├── credential_manager.py # 암호화 자격증명 관리
│   ├── smartstore_scraper.py # 스마트스토어 상품 파싱
│   ├── gemini_writer.py      # Gemini AI 포스팅 생성
│   └── blog_poster.py        # Selenium 블로그 게시
├── utils/
│   └── logger.py             # 로거 (콘솔 + 파일)
├── data/                     # 런타임 생성 (gitignore)
│   ├── app.log
│   ├── credentials.enc
│   ├── session_cookies.pkl
│   └── images/
├── .env.example
└── requirements.txt
```

---

## 주의사항

- 본 도구는 **개인 학습 및 자동화 연구** 목적으로 제작되었습니다.
- 네이버 블로그 및 스마트스토어 **이용약관**을 반드시 준수하세요.
- 과도한 자동 게시는 계정 제재로 이어질 수 있습니다.
- API 키와 계정 정보가 외부에 유출되지 않도록 주의하세요.  
  `data/` 폴더는 `.gitignore` 에 의해 git 추적에서 제외됩니다.
