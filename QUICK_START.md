# ⚡ 3분 빠른 시작

## 1단계: 설치 (1분)

```bash
pip install fastapi uvicorn python-multipart jinja2 Pillow openpyxl openai
```

---

## 2단계: API 키 설정 (30초)

**app.py 파일 열기**

**30번째 줄 찾기:**
```python
ocr = OpenAIVisionExtractor()
```

**변경:**
```python
ocr = OpenAIVisionExtractor(api_key="sk-proj-당신의실제API키")
```

**저장: Ctrl + S**

---

## 3단계: 데이터 임포트 (1분)

```bash
python import_all_data.py
python import_kdri_data.py
```

**성공 메시지:**
```
✅ 영양소 데이터: 68개 성공
✅ KDRI 2025 데이터: 89개 성공
```

---

## 4단계: 서버 시작 (30초)

```bash
python app.py
```

**성공 메시지:**
```
✅ OpenAI GPT-4 Vision 준비 완료!
🤖💊 뉴트리-스캐너 웹 앱 시작!
```

**브라우저 자동 열림: http://localhost:8001**

---

## ✅ 완료!

**이제 영양 성분표를 스캔하세요!** 📸

---

## 🆘 문제 발생?

### "OpenAI API 키 오류"
→ app.py의 API 키 확인

### "데이터가 없어요"
→ import_kdri_data.py 다시 실행

### "서버가 안 열려요"
→ 포트 8001이 사용 중인지 확인

---

**3분이면 끝!** 🚀
