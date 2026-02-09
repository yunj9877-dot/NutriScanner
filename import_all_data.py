"""
뉴트리-스캐너 데이터 임포트
1. 식약처 영양소 데이터 (NS_dataset_final.txt)
2. 질환-영양성분 상호작용 (disease_nutrient_interactions.csv)
"""

import re
import sqlite3


def parse_amount_range(text):
    """권장량 텍스트에서 최소값, 최대값, 단위 추출"""
    # 괄호 안 내용 제거
    text = re.sub(r'\([^)]*\)', '', text).strip()
    text = re.sub(r'이상|이하', '', text).strip()
    
    # 숫자와 ~ 패턴
    pattern = r'([\d.]+)\s*~\s*([\d.]+)\s*([a-zA-Zμ가-힣]+)'
    match = re.search(pattern, text)
    
    if match:
        min_val = float(match.group(1))
        max_val = float(match.group(2))
        unit = match.group(3).strip()
        unit = unit.replace('μg', 'mcg')
        unit = re.sub(r'\s+.*', '', unit)
        return min_val, max_val, unit
    
    # 단일 값
    pattern_single = r'([\d.]+)\s*([a-zA-Zμ가-힣]+)'
    match_single = re.search(pattern_single, text)
    
    if match_single:
        val = float(match_single.group(1))
        unit = match_single.group(2).strip()
        unit = unit.replace('μg', 'mcg')
        unit = re.sub(r'\s+.*', '', unit)
        return val, val, unit
    
    return None, None, None


def normalize_unit(amount, unit):
    """단위를 mg으로 통일"""
    unit_lower = unit.lower()
    
    if unit_lower == 'g':
        return amount * 1000
    elif unit_lower in ['mcg', 'μg', 'ug']:
        return amount / 1000
    elif unit_lower == 'mg':
        return amount
    else:
        return amount


def import_nutrient_data(db_path="data/nutri_scanner.db"):
    """식약처 영양소 데이터 임포트"""
    
    # 파일 읽기
    with open("NS_dataset_final.txt", 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 기존 데이터 삭제
    cursor.execute("DELETE FROM daily_intake")
    cursor.execute("DELETE FROM ingredients_db")
    
    success_count = 0
    fail_count = 0
    
    print("📊 식약처 영양소 데이터 임포트 중...")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        parts = line.split(',', 1)
        if len(parts) != 2:
            fail_count += 1
            continue
        
        ingredient_name = parts[0].strip()
        amount_text = parts[1].strip().strip('"')
        
        # 권장량 파싱
        min_val, max_val, unit = parse_amount_range(amount_text)
        
        if min_val is None:
            print(f"  ⚠️ 파싱 실패: {ingredient_name}")
            fail_count += 1
            continue
        
        # 단위 통일
        if unit.lower() in ['g', 'mg', 'mcg', 'μg', 'ug']:
            min_mg = normalize_unit(min_val, unit)
            max_mg = normalize_unit(max_val, unit)
            normalized_unit = 'mg'
        else:
            min_mg = min_val
            max_mg = max_val
            normalized_unit = unit
        
        recommended = (min_mg + max_mg) / 2
        
        # ingredients_db 삽입
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO ingredients_db (name, category, description)
                VALUES (?, ?, ?)
            """, (ingredient_name, "식약처 인정", amount_text))
        except Exception as e:
            pass
        
        # daily_intake 삽입
        try:
            cursor.execute("""
                INSERT INTO daily_intake 
                (ingredient, age_min, age_max, min_amount, recommended_amount, max_amount, unit, original_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (ingredient_name, 19, 100, min_mg, recommended, max_mg, normalized_unit, amount_text))
            
            success_count += 1
            
        except Exception as e:
            print(f"  ⚠️ 삽입 실패: {ingredient_name} - {e}")
            fail_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"  ✅ 영양소 데이터: {success_count}개 성공, {fail_count}개 실패\n")
    return success_count, fail_count


def import_disease_interactions(db_path="data/nutri_scanner.db"):
    """질환-영양성분 상호작용 데이터 임포트"""
    
    # 파일 읽기
    with open("disease_nutrient_interactions.csv", 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 기존 데이터 삭제
    cursor.execute("DELETE FROM disease_interactions")
    
    success_count = 0
    fail_count = 0
    
    print("🏥 질환-영양성분 상호작용 데이터 임포트 중...")
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        parts = line.split(',')
        if len(parts) < 3:
            fail_count += 1
            continue
        
        nutrient = parts[0].strip()
        disease = parts[1].strip()
        category = parts[2].strip()
        reason = parts[3].strip() if len(parts) > 3 else ""
        
        # 위험도 판정
        if category == "주의":
            risk_level = "warning"
        else:
            risk_level = "safe"
        
        try:
            cursor.execute("""
                INSERT INTO disease_interactions (nutrient, disease, category, reason, risk_level)
                VALUES (?, ?, ?, ?, ?)
            """, (nutrient, disease, category, reason, risk_level))
            
            success_count += 1
            
        except Exception as e:
            print(f"  ⚠️ 삽입 실패: {nutrient} - {disease} - {e}")
            fail_count += 1
    
    conn.commit()
    conn.close()
    
    print(f"  ✅ 상호작용 데이터: {success_count}개 성공, {fail_count}개 실패\n")
    return success_count, fail_count


def main():
    """메인 실행"""
    print("=" * 60)
    print("🤖💊 뉴트리-스캐너 데이터 임포트")
    print("=" * 60)
    print()
    
    # 0. 데이터베이스 초기화 (테이블 생성)
    from database import NutriDatabase
    db = NutriDatabase()
    db.initialize()
    print()
    
    # 1. 영양소 데이터
    nutrient_ok, nutrient_fail = import_nutrient_data()
    
    # 2. 질환-영양성분 상호작용
    disease_ok, disease_fail = import_disease_interactions()
    
    print("=" * 60)
    print(f"📊 최종 결과:")
    print(f"  • 영양소 데이터: {nutrient_ok}개")
    print(f"  • 상호작용 데이터: {disease_ok}개")
    print(f"  • 총 성공: {nutrient_ok + disease_ok}개")
    print("=" * 60)
    print("✅ 데이터 임포트 완료!")


if __name__ == "__main__":
    main()
