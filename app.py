"""
뉴트리-스캐너 메인 서버
- 9개 화면 라우팅
- API 엔드포인트
"""

from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import os
from pathlib import Path
import json
from datetime import datetime

# 내부 모듈
from database import Database
from analyzer import SafetyAnalyzer
from ocr_openai import OpenAIVisionExtractor

# FastAPI 앱
app = FastAPI(title="뉴트리-스캐너")

# 템플릿 (절대 경로로 설정)
from pathlib import Path
BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# DB 초기화
db = Database()
db.initialize()

# ========== 자동 데이터 임포트 ==========
def auto_import_data():
    """서버 시작 시 데이터가 없으면 자동 임포트"""
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # daily_intake 테이블 데이터 확인
    cursor.execute("SELECT COUNT(*) FROM daily_intake")
    count = cursor.fetchone()[0]
    
    if count == 0:
        print("📊 데이터가 없습니다. 자동 임포트를 시작합니다...")
        
        import csv
        import os
        
        # 1. 기본 KDRI 데이터 임포트
        kdri_file = BASE_DIR / "KDRI_2025_AppDB_RNI_Adults30plus_FULL.csv"
        if kdri_file.exists():
            import_kdri_csv(str(kdri_file), cursor)
        
        # 2. 다량영양소 데이터 임포트
        macro_file = BASE_DIR / "KDRI_2025_MACRONUTRIENTS.csv"
        if macro_file.exists():
            import_kdri_csv(str(macro_file), cursor)
        
        # 3. 질환-영양소 상호작용 데이터 임포트
        interaction_file = BASE_DIR / "disease_nutrient_interactions.csv"
        if interaction_file.exists():
            import_interactions(str(interaction_file), cursor)
        
        conn.commit()
        
        # 최종 확인
        cursor.execute("SELECT COUNT(*) FROM daily_intake")
        final_count = cursor.fetchone()[0]
        print(f"✅ 데이터 임포트 완료! (총 {final_count}개)")
    else:
        print(f"✅ 기존 데이터 사용 (총 {count}개)")

def parse_age_range(age_str):
    """연령대 문자열 파싱"""
    import re
    age_str = age_str.replace("세", "").strip()
    
    if "이상" in age_str:
        num = re.search(r'\d+', age_str)
        if num:
            return int(num.group()), 120
    
    match = re.match(r'(\d+)\s*[-~]\s*(\d+)', age_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    
    num = re.search(r'\d+', age_str)
    if num:
        age = int(num.group())
        return age, age + 9
    
    return 30, 120

def import_kdri_csv(filepath, cursor):
    """KDRI CSV 파일 임포트"""
    import csv
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:  # utf-8-sig로 BOM 자동 제거
        reader = csv.DictReader(f)
        success = 0
        
        for row in reader:
            try:
                gender = row['성별'].strip()
                age_range = row['연령대'].strip()
                nutrient = row['영양소'].strip()
                amount = float(row['1일_권장섭취량'].strip())
                unit = row['단위'].strip()
                
                age_min, age_max = parse_age_range(age_range)
                
                # 최소/최대값 계산 (부동소수점 반올림)
                min_amount = round(amount * 0.5, 2)
                max_amount = round(amount * 1.5, 2)
                
                original_text = f"KDRI 2025 - {gender} {age_range}: {amount}{unit}"
                
                cursor.execute("""
                    INSERT INTO daily_intake 
                    (ingredient, age_min, age_max, gender, min_amount, recommended_amount, max_amount, unit, original_text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (nutrient, age_min, age_max, gender, min_amount, amount, max_amount, unit, original_text))
                
                success += 1
            except Exception as e:
                pass
        
        print(f"  📁 {Path(filepath).name}: {success}개 임포트")

def import_interactions(filepath, cursor):
    """질환-영양소 상호작용 데이터 임포트"""
    import csv
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:  # utf-8-sig로 BOM 자동 제거
        reader = csv.DictReader(f)
        success = 0
        
        for row in reader:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO disease_interactions 
                    (nutrient, disease, category, reason, risk_level)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    row.get('nutrient', ''),
                    row.get('disease', ''),
                    row.get('category', ''),
                    row.get('reason', ''),
                    row.get('risk_level', 'warning')
                ))
                success += 1
            except:
                pass
        
        print(f"  📁 질환-영양소 상호작용: {success}개 임포트")

# 서버 시작 시 자동 임포트 실행
auto_import_data()

# 분석기
analyzer = SafetyAnalyzer(db)
ocr = OpenAIVisionExtractor(api_key=os.getenv("OPENAI_API_KEY"))  # OpenAI GPT-4 Vision 사용!

# 업로드 폴더
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Static 파일
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ========== 화면 라우팅 ==========

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """메인 대시보드"""
    user = db.get_current_user()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "user": user
    })


@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """프로필 설정 (화면 1)"""
    user = db.get_current_user()
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": user
    })


@app.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request):
    """스캔 화면 (화면 2-1)"""
    user = db.get_current_user()
    if not user:
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "error": "먼저 프로필을 설정해주세요"
        })
    
    return templates.TemplateResponse("scan.html", {
        "request": request,
        "user": user
    })


@app.get("/scan/confirm", response_class=HTMLResponse)
async def scan_confirm_page(request: Request):
    """영양정보 확인 화면 (화면 2-2)"""
    user = db.get_current_user()
    if not user:
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "error": "먼저 프로필을 설정해주세요"
        })
    
    return templates.TemplateResponse("scan_confirm.html", {
        "request": request,
        "user": user,
        "view_mode": False
    })


@app.get("/scan/view", response_class=HTMLResponse)
async def scan_view_page(request: Request, scan_id: int):
    """저장된 스캔 성분 보기 (이력에서 접근)"""
    user = db.get_current_user()
    if not user:
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "error": "먼저 프로필을 설정해주세요"
        })
    
    scan = db.get_scan_by_id(scan_id)
    if not scan:
        return templates.TemplateResponse("history.html", {
            "request": request,
            "user": user,
            "history": [],
            "error": "스캔 데이터를 찾을 수 없습니다"
        })
    
    # 이미지 파일이 있으면 base64로 변환
    image_url = None
    if scan.get("image_path"):
        import base64
        from pathlib import Path
        image_path = Path(scan["image_path"])
        if image_path.exists():
            with open(image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
                # 확장자에 따라 MIME 타입 결정
                ext = image_path.suffix.lower()
                mime_type = "image/jpeg" if ext in [".jpg", ".jpeg"] else "image/png"
                image_url = f"data:{mime_type};base64,{image_base64}"
    
    # scan에 image_url 추가
    scan["image_url"] = image_url
    
    return templates.TemplateResponse("scan_confirm.html", {
        "request": request,
        "user": user,
        "view_mode": True,
        "scan_id": scan_id,
        "saved_scan": scan
    })


@app.get("/analysis/safety", response_class=HTMLResponse)
async def analysis_safety_page(request: Request, scan_id: int):
    """안전 신호등 (화면 3-1)"""
    user = db.get_current_user()
    # scan_id로 스캔 결과 가져오기
    scan = db.get_scan_by_id(scan_id)
    
    if not scan:
        # scan_id가 없으면 최근 스캔 사용
        history = db.get_scan_history(user["id"], 1)
        if not history:
            return templates.TemplateResponse("scan.html", {
                "request": request,
                "error": "스캔 이력이 없습니다"
            })
        scan = history[0]
    
    return templates.TemplateResponse("analysis_safety.html", {
        "request": request,
        "user": user,
        "scan": scan,
        "scan_id": scan.get("id", scan_id),
        "safety_result": scan.get("safety_result", {"overall_risk": "safe", "warnings": [], "recommendations": []})
    })


@app.get("/analysis/dri", response_class=HTMLResponse)
async def analysis_dri_page(request: Request, scan_id: int = None):
    """1일 권장량 분석 (화면 3-2)"""
    user = db.get_current_user()
    
    if scan_id:
        scan = db.get_scan_by_id(scan_id)
    else:
        history = db.get_scan_history(user["id"], 1)
        scan = history[0] if history else None
    
    if not scan:
        return templates.TemplateResponse("scan.html", {
            "request": request,
            "error": "스캔 이력이 없습니다"
        })
    
    return templates.TemplateResponse("analysis_dri.html", {
        "request": request,
        "user": user,
        "scan": scan,
        "scan_id": scan.get("id", scan_id),
        "dri_results": scan.get("dri_result", [])
    })


@app.get("/analysis/detail", response_class=HTMLResponse)
async def analysis_detail_page(request: Request):
    """상세 정보 (화면 3-3)"""
    user = db.get_current_user()
    history = db.get_scan_history(user["id"], 1)
    
    if not history:
        return templates.TemplateResponse("scan.html", {
            "request": request,
            "error": "스캔 이력이 없습니다"
        })
    
    scan = history[0]
    
    return templates.TemplateResponse("analysis_detail.html", {
        "request": request,
        "user": user,
        "scan": scan
    })


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, date: str = None):
    """스캔 이력 (화면 4-1)"""
    user = db.get_current_user()
    
    if not user:
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "error": "먼저 프로필을 설정해주세요"
        })
    
    history = db.get_scan_history(user["id"], 30)
    
    # 날짜 필터링
    selected_date = None
    if date:
        selected_date = date
        history = [h for h in history if h["scan_date"][:10] == date]
    
    return templates.TemplateResponse("history.html", {
        "request": request,
        "user": user,
        "history": history,
        "selected_date": selected_date
    })


@app.get("/report", response_class=HTMLResponse)
async def report_page(request: Request):
    """월간 리포트 (화면 4-2)"""
    user = db.get_current_user()
    
    if not user:
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "error": "먼저 프로필을 설정해주세요"
        })
    
    # 이번 달 통계
    now = datetime.now()
    stats = db.get_monthly_stats(user["id"], now.year, now.month)
    history = db.get_scan_history(user["id"], 30)
    
    # 이번 달 데이터만 필터링
    month_history = [h for h in history if h["scan_date"][:7] == f"{now.year}-{now.month:02d}"]
    
    # 통계 계산
    total_scans = len(month_history)
    scan_days = len(set([h["scan_date"][:10] for h in month_history]))
    
    # 알림 통계 계산
    danger_count = 0
    warning_count = 0
    safe_count = 0
    total_ingredients = 0
    warning_ingredients = 0
    
    # 날짜별 위험도 저장
    date_risk_map = {}  # {날짜: 위험도}
    danger_dates = []
    warning_dates = []
    
    for scan in month_history:
        total_ingredients += len(scan.get("ingredients", []))
        scan_date = scan["scan_date"][:10]
        day_num = int(scan_date.split("-")[2])  # 일자만 추출
        
        if scan.get("safety_result"):
            risk = scan["safety_result"].get("overall_risk", "safe")
            if risk == "danger":
                danger_count += 1
                date_risk_map[scan_date] = "danger"
                if f"{now.month}/{day_num}" not in danger_dates:
                    danger_dates.append(f"{now.month}/{day_num}")
            elif risk == "warning":
                warning_count += 1
                if scan_date not in date_risk_map or date_risk_map[scan_date] != "danger":
                    date_risk_map[scan_date] = "warning"
                if f"{now.month}/{day_num}" not in warning_dates:
                    warning_dates.append(f"{now.month}/{day_num}")
            else:
                safe_count += 1
                if scan_date not in date_risk_map:
                    date_risk_map[scan_date] = "safe"
            
            # 주의 성분 수
            warnings = scan["safety_result"].get("warnings", [])
            warning_ingredients += len(warnings)
    
    # 안전 비율 계산
    safe_percent = round((safe_count / total_scans * 100) if total_scans > 0 else 0)
    
    # 달력 데이터 생성
    import calendar
    cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
    month_days = cal.monthdayscalendar(now.year, now.month)
    
    # 스캔한 날짜 목록
    scan_dates = set([h["scan_date"][:10] for h in month_history])
    
    calendar_days = []
    for week in month_days:
        for day in week:
            if day == 0:
                calendar_days.append({
                    "day": "", 
                    "is_empty": True, 
                    "is_today": False, 
                    "has_scan": False,
                    "risk": None,
                    "date_str": ""
                })
            else:
                date_str = f"{now.year}-{now.month:02d}-{day:02d}"
                calendar_days.append({
                    "day": day,
                    "is_empty": False,
                    "is_today": day == now.day,
                    "has_scan": date_str in scan_dates,
                    "risk": date_risk_map.get(date_str),
                    "date_str": date_str
                })
    
    return templates.TemplateResponse("report.html", {
        "request": request,
        "user": user,
        "stats": stats,
        "history": month_history,
        "current_year": now.year,
        "current_month": now.month,
        "total_scans": total_scans,
        "scan_days": scan_days,
        "danger_count": danger_count,
        "warning_count": warning_count,
        "safe_count": safe_count,
        "safe_percent": safe_percent,
        "danger_dates": danger_dates,
        "warning_dates": warning_dates,
        "total_products": total_scans,
        "total_ingredients": total_ingredients,
        "warning_ingredients": warning_ingredients,
        "calendar_days": calendar_days
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """설정 (화면 4-3)"""
    user = db.get_current_user()
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user
    })


# ========== API 엔드포인트 ==========

@app.get("/api/users")
async def get_all_users():
    """모든 사용자 목록 반환 (자동완성용)"""
    users = db.get_all_users()
    return users

@app.post("/api/profile")
async def save_profile(request: Request):
    """프로필 저장 (JSON 또는 Form 데이터)"""
    
    try:
        # JSON 요청 처리
        data = await request.json()
        name = data.get("name")
        age = int(data.get("age", 0))
        gender = data.get("gender", "")
        diseases = data.get("diseases", "[]")
        guardian_name = data.get("guardian_name", "")
        guardian_phone = data.get("guardian_phone", "")
        guardian_email = data.get("guardian_email", "")
        guardian_relation = data.get("guardian_relation", "")
        
        # diseases가 문자열이면 JSON 파싱
        if isinstance(diseases, str):
            import json
            try:
                disease_list = json.loads(diseases)
            except:
                disease_list = [d.strip() for d in diseases.split(",") if d.strip()]
        else:
            disease_list = diseases
            
    except:
        # Form 데이터 처리 (fallback)
        form = await request.form()
        name = form.get("name")
        age = int(form.get("age", 0))
        gender = form.get("gender", "")
        diseases = form.get("diseases", "")
        guardian_name = form.get("guardian_name", "")
        guardian_phone = form.get("guardian_phone", "")
        guardian_email = form.get("guardian_email", "")
        guardian_relation = form.get("guardian_relation", "")
        disease_list = [d.strip() for d in diseases.split(",") if d.strip()]
    
    # 나이 검증 (50세 이상만)
    if age < 50:
        return {"success": False, "message": "본 서비스는 50세 이상 성인 전용입니다."}
    
    user_id = db.save_user_profile(
        name=name,
        age=age,
        gender=gender if gender else None,
        diseases=disease_list,
        guardian_name=guardian_name if guardian_name else None,
        guardian_phone=guardian_phone if guardian_phone else None,
        guardian_email=guardian_email if guardian_email else None,
        guardian_relation=guardian_relation if guardian_relation else None
    )
    
    # 새 사용자를 현재 사용자로 자동 설정 (v13 NEW!)
    db.set_current_user_id(user_id)
    
    return {
        "success": True,
        "user_id": user_id,
        "message": "프로필이 저장되었습니다"
    }


@app.post("/api/profile/update")
async def update_profile(request: Request):
    """프로필 수정 (v13 NEW!)"""
    
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        name = data.get("name")
        age = int(data.get("age", 0))
        gender = data.get("gender", "")
        diseases = data.get("diseases", "[]")
        guardian_name = data.get("guardian_name", "")
        guardian_phone = data.get("guardian_phone", "")
        guardian_email = data.get("guardian_email", "")
        guardian_relation = data.get("guardian_relation", "")
        
        # diseases가 문자열이면 JSON 파싱
        if isinstance(diseases, str):
            import json
            try:
                disease_list = json.loads(diseases)
            except:
                disease_list = [d.strip() for d in diseases.split(",") if d.strip()]
        else:
            disease_list = diseases
            
    except Exception as e:
        return {"success": False, "message": f"데이터 파싱 오류: {str(e)}"}
    
    # 나이 검증 (50세 이상만)
    if age < 50:
        return {"success": False, "message": "본 서비스는 50세 이상 성인 전용입니다."}
    
    success = db.update_user_profile(
        user_id=user_id,
        name=name,
        age=age,
        gender=gender if gender else None,
        diseases=disease_list,
        guardian_name=guardian_name if guardian_name else None,
        guardian_phone=guardian_phone if guardian_phone else None,
        guardian_email=guardian_email if guardian_email else None,
        guardian_relation=guardian_relation if guardian_relation else None
    )
    
    if success:
        # 수정한 사용자를 현재 사용자로 설정 (v13 NEW!)
        db.set_current_user_id(user_id)
        return {
            "success": True,
            "user_id": user_id,
            "message": "프로필이 수정되었습니다"
        }
    else:
        return {
            "success": False,
            "message": "프로필 수정에 실패했습니다"
        }


@app.get("/api/profiles/search")
async def search_profiles(q: str = ""):
    """프로필 검색 API (동명이인 모두 반환) - v13 NEW!"""
    if q:
        profiles = db.search_users_by_name(q)
    else:
        profiles = db.get_all_users()
    return {"profiles": profiles}


# ========== 사용자 전환 API (v13 NEW!) ==========

@app.post("/api/user/switch")
async def switch_user(request: Request):
    """사용자 전환 - 선택한 사용자로 변경"""
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        
        # 해당 사용자가 존재하는지 확인
        user = db.get_user_profile(user_id)
        if not user:
            return {"success": False, "message": "사용자를 찾을 수 없습니다"}
        
        # 현재 사용자로 설정
        db.set_current_user_id(user_id)
        
        return {
            "success": True,
            "user_id": user_id,
            "user_name": user["name"],
            "message": f"{user['name']}님으로 전환되었습니다"
        }
    except Exception as e:
        return {"success": False, "message": f"오류: {str(e)}"}


@app.get("/api/user/current")
async def get_current_user_api():
    """현재 사용자 조회 API"""
    user = db.get_current_user()
    if user:
        return {"success": True, "user": user}
    return {"success": False, "message": "등록된 사용자가 없습니다"}


@app.get("/api/users/all")
async def get_all_users_api():
    """모든 등록된 사용자 목록 조회 API"""
    users = db.get_all_users()
    return {"success": True, "users": users}


# ========== 건강관리기관 연동 API (v13 NEW!) ==========

@app.post("/api/institutions/connect")
async def connect_institution(request: Request):
    """건강관리기관 연동"""
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        name = data.get("name")
        inst_type = data.get("type", "hospital")
        phone = data.get("phone", "")
        email = data.get("email", "")
        
        # 기존 연동 확인
        existing = db.get_institution_by_name(user_id, name)
        
        if existing:
            # 기존 연동 업데이트
            success = db.update_health_institution(
                inst_id=existing["id"],
                phone=phone,
                email=email,
                is_connected=1
            )
            return {"success": success, "message": f"{name} 연동 정보가 업데이트되었습니다"}
        else:
            # 새 연동 추가
            inst_id = db.add_health_institution(
                user_id=user_id,
                name=name,
                inst_type=inst_type,
                phone=phone,
                email=email
            )
            return {"success": True, "inst_id": inst_id, "message": f"{name}이(가) 연동되었습니다"}
            
    except Exception as e:
        return {"success": False, "message": f"오류: {str(e)}"}


@app.get("/api/institutions/{user_id}")
async def get_institutions(user_id: int):
    """사용자의 연동된 기관 목록"""
    institutions = db.get_health_institutions(user_id)
    return {"success": True, "institutions": institutions}


@app.post("/api/institutions/disconnect")
async def disconnect_institution(request: Request):
    """건강관리기관 연동 해제"""
    try:
        data = await request.json()
        inst_id = int(data.get("inst_id"))
        
        success = db.delete_health_institution(inst_id)
        return {"success": success, "message": "연동이 해제되었습니다"}
        
    except Exception as e:
        return {"success": False, "message": f"오류: {str(e)}"}


# ========== 이메일 전송 API (v13 NEW!) ==========

@app.post("/api/email/send-report")
async def send_email_report(request: Request):
    """보호자에게 리포트 이메일 전송"""
    try:
        data = await request.json()
        user_id = int(data.get("user_id"))
        to_email = data.get("to_email")
        to_name = data.get("to_name", "보호자")
        user_name = data.get("user_name", "사용자")
        
        # 최근 스캔 기록 가져오기
        history = db.get_scan_history(user_id, limit=5)
        
        # 이메일 내용 구성
        email_subject = f"[뉴트리-스캐너] {user_name}님의 영양제 분석 리포트"
        
        # 스캔 결과 요약
        danger_count = 0
        warning_count = 0
        safe_count = 0
        
        for scan in history:
            safety = scan.get("safety_result", {})
            if safety.get("danger_items"):
                danger_count += 1
            elif safety.get("warning_items"):
                warning_count += 1
            else:
                safe_count += 1
        
        # 종합 판정
        if danger_count > 0:
            summary = f"⚠️ 위험 {danger_count}건 발견 - 전문가 상담 권장"
        elif warning_count > 0:
            summary = f"⚡ 주의 {warning_count}건 - 섭취량 조절 권장"
        else:
            summary = "✅ 모두 안전 - 현재 패턴 유지"
        
        # 이메일 본문 HTML
        email_body = f"""
        <html>
        <body style="font-family: 'Noto Sans KR', sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #20B2AA, #2E8B7A); padding: 20px; text-align: center; color: white;">
                <h1 style="margin: 0;">🤖💊 뉴트리-스캐너</h1>
                <p>영양제 분석 리포트</p>
            </div>
            
            <div style="padding: 20px;">
                <p>안녕하세요, <strong>{to_name}</strong>님.</p>
                <p><strong>{user_name}</strong>님의 최근 영양제 분석 결과를 알려드립니다.</p>
                
                <div style="background: #f8f9fa; padding: 15px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="color: #20B2AA; margin-top: 0;">📊 최근 분석 요약</h3>
                    <p>총 {len(history)}건 스캔</p>
                    <ul>
                        <li>✅ 안전: {safe_count}건</li>
                        <li>⚡ 주의: {warning_count}건</li>
                        <li>⚠️ 위험: {danger_count}건</li>
                    </ul>
                    <p style="font-weight: bold;">{summary}</p>
                </div>
                
                <p style="color: #888; font-size: 12px;">
                    본 메일은 뉴트리-스캐너 앱에서 자동 발송되었습니다.<br>
                    자세한 내용은 앱에서 확인해주세요.
                </p>
            </div>
        </body>
        </html>
        """
        
        # 실제 이메일 전송 (SMTP 설정 필요)
        # 현재는 시뮬레이션 모드
        email_sent = send_email_smtp(to_email, email_subject, email_body)
        
        if email_sent:
            print(f"📧 이메일 전송 완료: {to_email}")
            return {"success": True, "message": f"{to_email}로 리포트가 전송되었습니다"}
        else:
            return {"success": True, "message": f"이메일 전송 시뮬레이션 완료 (실제 전송은 SMTP 설정 필요)"}
        
    except Exception as e:
        print(f"❌ 이메일 전송 오류: {e}")
        return {"success": False, "message": f"전송 실패: {str(e)}"}


def send_email_smtp(to_email, subject, body):
    """
    실제 이메일 전송 함수 (SMTP)
    - 실제 사용 시 SMTP 서버 설정 필요
    """
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # SMTP 설정 (Gmail 예시)
        # 실제 사용 시 환경변수나 설정 파일에서 가져오기
        SMTP_SERVER = "smtp.gmail.com"
        SMTP_PORT = 587
        SMTP_USER = ""  # 발신 이메일
        SMTP_PASSWORD = ""  # 앱 비밀번호
        
        if not SMTP_USER or not SMTP_PASSWORD:
            print("⚠️ SMTP 설정이 없습니다. 시뮬레이션 모드로 동작합니다.")
            print(f"   받는이: {to_email}")
            print(f"   제목: {subject}")
            return False
        
        # 이메일 구성
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        
        html_part = MIMEText(body, 'html', 'utf-8')
        msg.attach(html_part)
        
        # 전송
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        return True
        
    except Exception as e:
        print(f"❌ SMTP 오류: {e}")
        return False


@app.post("/api/scan")
async def scan_supplement_preview(
    image: UploadFile = File(...),
    user_id: int = Form(None)
):
    """영양제 스캔 - OCR만 수행 (분석 전 확인용)"""
    
    # 사용자 ID 없으면 최신 사용자
    if not user_id:
        user = db.get_current_user()
        if not user:
            return JSONResponse(
                status_code=400,
                content={"error": "프로필을 먼저 설정해주세요"}
            )
        user_id = user["id"]
    
    # 이미지 저장
    image_path = UPLOAD_DIR / image.filename
    with open(image_path, "wb") as f:
        content = await image.read()
        f.write(content)
    
    print(f"📸 이미지 저장: {image_path}")
    
    # OCR 처리
    ocr_text = ocr.extract_text(str(image_path))
    print(f"📝 추출된 텍스트: {len(ocr_text)}자")
    
    # 성분 파싱
    ingredients = ocr.parse_ingredients(ocr_text)
    print(f"💊 인식된 성분: {len(ingredients)}개")
    
    # 이미지를 base64로 인코딩 (프론트엔드 전송용)
    import base64
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    return {
        "success": True,
        "image_url": f"data:image/jpeg;base64,{image_base64}",
        "image_path": str(image_path),
        "ocr_text": ocr_text,
        "ingredients": ingredients,
        "user_id": user_id
    }


@app.post("/api/scan/confirm")
async def scan_supplement_confirm(
    image: UploadFile = File(...),
    ingredients: str = Form(...),
    user_id: int = Form(None)
):
    """영양제 스캔 확인 후 최종 분석"""
    
    # 사용자 ID 없으면 최신 사용자
    if not user_id:
        user = db.get_current_user()
        if not user:
            return JSONResponse(
                status_code=400,
                content={"error": "프로필을 먼저 설정해주세요"}
            )
        user_id = user["id"]
    
    # 이미지 저장
    image_path = UPLOAD_DIR / image.filename
    with open(image_path, "wb") as f:
        content = await image.read()
        f.write(content)
    
    # 성분 데이터 파싱
    ingredients_data = json.loads(ingredients)
    print(f"💊 확인된 성분: {len(ingredients_data)}개")
    
    # 사용자 프로필
    user_profile = db.get_user_profile(user_id)
    print(f"👤 사용자 프로필: {user_profile}")
    print(f"👤 성별: {user_profile.get('gender') if user_profile else 'None'}")
    
    # 안전성 분석
    safety_result = analyzer.analyze_safety(ingredients_data, user_profile)
    
    # 1일 권장량 분석
    dri_result = analyzer.analyze_daily_intake(ingredients_data, user_profile)
    
    # 종합 조언
    advice = analyzer.generate_advice(safety_result, dri_result, user_profile)
    
    # 결과 저장
    product_name = "영양제"  # TODO: OCR에서 제품명 추출
    scan_id = db.save_scan_result(
        user_id=user_id,
        image_path=str(image_path),
        product_name=product_name,
        ingredients=ingredients_data,
        safety_result=safety_result,
        dri_result=dri_result
    )
    
    return {
        "success": True,
        "scan_id": scan_id,
        "ingredients": ingredients_data,
        "safety": safety_result,
        "daily_intake": dri_result,
        "advice": advice
    }


@app.get("/api/history/{user_id}")
async def get_history(user_id: int, limit: int = 30):
    """스캔 이력 조회"""
    history = db.get_scan_history(user_id, limit)
    return {
        "success": True,
        "history": history
    }


@app.get("/api/report/{user_id}/{year}/{month}")
async def get_monthly_report(user_id: int, year: int, month: int):
    """월간 리포트"""
    stats = db.get_monthly_stats(user_id, year, month)
    history = db.get_scan_history(user_id, 30)
    
    return {
        "success": True,
        "stats": stats,
        "history": history
    }


# ========== 서버 실행 ==========

if __name__ == "__main__":
    import webbrowser
    import threading
    import time
    
    print("=" * 60)
    print("🤖💊 뉴트리-스캐너 웹 앱 시작!")
    print("=" * 60)
    print("📱 자동으로 브라우저가 열립니다...")
    print("📱 수동 접속: http://localhost:8003")
    print()
    print("📋 화면 목록:")
    print("  1. http://localhost:8003/profile - 프로필 설정")
    print("  2. http://localhost:8003/scan - 스캔")
    print("  3. http://localhost:8003/analysis/safety - 안전 신호등")
    print("  4. http://localhost:8003/analysis/dri - 1일 권장량")
    print("  5. http://localhost:8003/analysis/detail - 상세 정보")
    print("  6. http://localhost:8003/history - 이력")
    print("  7. http://localhost:8003/report - 월간 리포트")
    print("  8. http://localhost:8003/settings - 설정")
    print("=" * 60)
    
    # 2초 후 자동으로 브라우저 열기
    def open_browser():
        time.sleep(2)
        print("🌐 브라우저 열기...")
        webbrowser.open('http://localhost:8003')
    
    # 별도 쓰레드에서 브라우저 열기
    threading.Thread(target=open_browser, daemon=True).start()
    
    uvicorn.run(app, host="0.0.0.0", port=8003)