"""
KDRI 2025 한국인 영양소 섭취기준 데이터 임포트
- 성별/연령대별 정확한 권장섭취량
- 11개 주요 영양소
- 프로필 기반 맞춤 분석 가능
"""

import csv
import sqlite3


def normalize_unit(unit):
    """단위 정규화"""
    unit = unit.strip().lower()
    
    # µg → mcg
    if unit in ['µg', 'μg', 'ug']:
        return 'mcg'
    
    # µg RAE → mcg
    if 'µg' in unit or 'μg' in unit or 'rae' in unit:
        return 'mcg'
    
    # 기타
    return unit


def parse_age_range(age_str):
    """연령대 문자열을 min/max로 변환"""
    age_str = age_str.strip()
    
    if '30-49' in age_str:
        return 30, 49
    elif '50-64' in age_str:
        return 50, 64
    elif '65-74' in age_str:
        return 65, 74
    elif '75세 이상' in age_str or '75' in age_str:
        return 75, 100
    else:
        return 19, 100  # 기본값


def import_kdri_data(db_path="data/nutri_scanner.db"):
    """KDRI 2025 데이터 임포트"""
    
    print("=" * 60)
    print("KDRI 2025 한국인 영양소 섭취기준 임포트")
    print("=" * 60)
    
    # 두 파일 모두 읽기
    all_data = []
    
    # 기본 파일
    try:
        with open("KDRI_2025_AppDB_RNI_Adults30plus_FULL.csv", 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            all_data.extend(list(reader))
            print(f"📊 기본 영양소 데이터 로드: {len(all_data)}개")
    except FileNotFoundError:
        print("⚠️ KDRI_2025_AppDB_RNI_Adults30plus_FULL.csv 파일 없음")
    
    # 추가 파일 (탄수화물, 지방 등)
    try:
        with open("KDRI_2025_MACRONUTRIENTS.csv", 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            macro_data = list(reader)
            all_data.extend(macro_data)
            print(f"📊 추가 기본 영양소 데이터 로드: {len(macro_data)}개")
    except FileNotFoundError:
        print("⚠️ KDRI_2025_MACRONUTRIENTS.csv 파일 없음 (선택사항)")
    
    print(f"📊 총 {len(all_data)}개 데이터 로드")
    
    # DB 연결
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 기존 KDRI 데이터 삭제
    cursor.execute("DELETE FROM daily_intake WHERE original_text LIKE 'KDRI%'")
    print(f"🗑️ 기존 KDRI 데이터 삭제")
    
    # 성별 컬럼 추가 (없으면)
    try:
        cursor.execute("ALTER TABLE daily_intake ADD COLUMN gender TEXT")
        print("✅ gender 컬럼 추가")
    except:
        pass  # 이미 있음
    
    success_count = 0
    fail_count = 0
    
    for row in all_data:
        gender = row['성별'].strip()  # 남자/여자
        age_range = row['연령대'].strip()  # 30-49세 등
        nutrient = row['영양소'].strip()  # 비타민C 등
        amount_str = row['1일_권장섭취량'].strip()  # 100
        unit = row['단위'].strip()  # mg
        
        # 연령 범위 파싱
        age_min, age_max = parse_age_range(age_range)
        
        # 단위 정규화
        normalized_unit = normalize_unit(unit)
        
        # 함량 변환
        try:
            amount = float(amount_str)
        except:
            print(f"  ⚠️ 숫자 변환 실패: {nutrient} {amount_str}")
            fail_count += 1
            continue
        
        # 단위 통일 (mg 기준)
        if normalized_unit == 'g':
            amount_mg = amount * 1000
            final_unit = 'mg'
        elif normalized_unit == 'mcg':
            amount_mg = amount / 1000
            final_unit = 'mg'
        elif normalized_unit == 'kcal':
            amount_mg = amount
            final_unit = 'kcal'
        else:
            amount_mg = amount
            final_unit = normalized_unit
        
        # 최소/최대값 (권장량의 50% ~ 150%)
        min_amount = amount_mg * 0.5
        max_amount = amount_mg * 1.5
        
        # original_text
        original_text = f"KDRI 2025 - {gender} {age_range}: {amount}{unit}"
        
        # DB 삽입
        try:
            cursor.execute("""
                INSERT INTO daily_intake 
                (ingredient, age_min, age_max, gender, min_amount, recommended_amount, max_amount, unit, original_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nutrient, 
                age_min, 
                age_max, 
                gender,
                min_amount, 
                amount_mg, 
                max_amount, 
                final_unit, 
                original_text
            ))
            
            success_count += 1
            
        except Exception as e:
            print(f"  ⚠️ 삽입 실패: {nutrient} ({gender}, {age_range}) - {e}")
            fail_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ KDRI 2025 데이터: {success_count}개 성공, {fail_count}개 실패")
    print(f"📊 성별/연령대별 맞춤 분석 가능!")
    print("=" * 60)
    
    return success_count, fail_count


if __name__ == "__main__":
    import_kdri_data()
