# 🤖💊 뉴트리-스캐너 v13

고령자를 위한 AI 기반 영양제 안전성 분석 시스템

## ✨ v13 업데이트 내용

### 1. 프로필 관리 시스템 개선
- **프로필 수정 시 기존 데이터 유지** - 빈 화면이 아닌 기존 정보가 채워진 상태로 수정
- **동명이인 구분 지원** - 이름 + 나이 + 질환으로 구분
- **프로필 검색 기능** - 이름으로 프로필 검색
- **프로필-스캔이력 연결** - 각 프로필별로 스캔 이력 분리 저장

### 2. 보호자 정보 개선
- **관계 선택 드롭다운** - 딸, 아들, 배우자, 요양보호사, 기타 선택
- **이메일 필드 추가** - 전화번호 + 이메일 모두 입력 가능
- **설정 화면 연동** - 보호자 정보가 알림 설정에서 표시

### 3. 건강관리기관 연동 (NEW!)
- **서울요양센터** - 전화/이메일로 연동
- **국민건강보험공단** - 전화/이메일로 연동
- **기관 추가** - 새로운 기관 등록 가능
- **모달 UI** - 클릭 시 연동 정보 입력 모달

## 📁 파일 구조

```
NS-v13/
├── app.py                  # FastAPI 메인 서버
├── database.py             # 데이터베이스 (개선됨!)
├── analyzer.py             # 안전성 분석 모듈
├── ocr_openai.py           # OpenAI GPT-4 Vision OCR
├── import_all_data.py      # 데이터 임포트
├── requirements.txt
├── templates/
│   ├── index.html          # 메인 대시보드
│   ├── profile.html        # 프로필 설정 (개선됨!)
│   ├── scan.html           # 스캔 화면
│   ├── scan_confirm.html   # 성분 확인/수정
│   ├── analysis_safety.html # 안전 신호등
│   ├── analysis_dri.html   # 1일 권장량
│   ├── analysis_detail.html # 상세 정보
│   ├── history.html        # 스캔 이력
│   ├── report.html         # 월간 리포트
│   └── settings.html       # 알림/연동 설정 (개선됨!)
├── static/css/
├── data/
│   └── nutri_scanner.db    # SQLite DB
└── uploads/                # 스캔 이미지 저장
```

## 🚀 실행 방법

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 서버 실행
python app.py

# 3. 브라우저 자동 열림
# http://localhost:8003
```

## 🔧 새로운 API (v13)

| API | 설명 |
|-----|------|
| `POST /api/profile/update` | 프로필 수정 |
| `GET /api/profiles/search?q=` | 프로필 검색 |
| `POST /api/institutions/connect` | 기관 연동 |
| `GET /api/institutions/{user_id}` | 연동 기관 목록 |
| `POST /api/institutions/disconnect` | 기관 연동 해제 |

## 📱 화면 목록

1. `/profile` - 프로필 설정 (보호자 관계 드롭다운, 이메일 추가)
2. `/scan` - 영양제 스캔
3. `/scan/confirm` - 성분 확인/수정
4. `/analysis/safety` - 안전 신호등
5. `/analysis/dri` - 1일 권장량 분석
6. `/analysis/detail` - 상세 성분 정보
7. `/history` - 스캔 이력
8. `/report` - 월간 리포트
9. `/settings` - 알림/보호자/기관 연동 설정

## ⚙️ OpenAI API 키 설정

`app.py` 파일에서 API 키 설정 (약 162번째 줄):
```python
ocr = OpenAIVisionExtractor(api_key="your-api-key-here")
```

---
Made with ❤️ for seniors
