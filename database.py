"""
뉴트리-스캐너 데이터베이스 관리 (v13 개선판)
- 사용자 프로필 (수정/검색 기능 추가)
- 영양소 정보
- 질환-영양성분 상호작용
- 스캔 이력
- 1일 권장량
- 건강관리기관 연동 (NEW!)
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path


class NutriDatabase:
    def __init__(self, db_path="data/nutri_scanner.db"):
        """데이터베이스 초기화"""
        Path("data").mkdir(exist_ok=True)
        self.db_path = db_path
        self.conn = None
    
    def get_connection(self):
        """DB 연결"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        return self.conn
    
    def initialize(self):
        """테이블 생성"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 1. 사용자 프로필 (guardian_email 추가, updated_at 추가)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                age INTEGER,
                gender TEXT,
                diseases TEXT,
                guardian_name TEXT,
                guardian_phone TEXT,
                guardian_email TEXT,
                guardian_relation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # guardian_email 컬럼 추가 (기존 DB 호환)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN guardian_email TEXT")
        except:
            pass
        
        # updated_at 컬럼 추가 (기존 DB 호환)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        except:
            pass
        
        # 6. 건강관리기관 연동 테이블 (NEW!)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_institutions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT NOT NULL,
                type TEXT,
                phone TEXT,
                email TEXT,
                is_connected INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # 2. 스캔 이력
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                image_path TEXT,
                product_name TEXT,
                ingredients TEXT,
                safety_result TEXT,
                dri_result TEXT,
                scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        
        # 3. 영양 성분 정보
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ingredients_db (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                category TEXT,
                description TEXT
            )
        """)
        
        # 4. 1일 권장량
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_intake (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ingredient TEXT,
                age_min INTEGER,
                age_max INTEGER,
                min_amount REAL,
                recommended_amount REAL,
                max_amount REAL,
                unit TEXT,
                gender TEXT,
                original_text TEXT
            )
        """)
        
        # 5. 질환-영양성분 상호작용
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS disease_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nutrient TEXT NOT NULL,
                disease TEXT NOT NULL,
                category TEXT,
                reason TEXT,
                risk_level TEXT
            )
        """)
        
        conn.commit()
        print("✅ 데이터베이스 초기화 완료")
        
        # 7. 앱 설정 테이블 (현재 사용자 ID 저장용) - v13 NEW!
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    
    # ========== 앱 설정 관리 (v13 NEW!) ==========
    
    def set_current_user_id(self, user_id):
        """현재 사용자 ID 설정"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO app_settings (key, value) VALUES ('current_user_id', ?)
        """, (str(user_id),))
        conn.commit()
        print(f"✅ 현재 사용자 변경: ID {user_id}")
    
    def get_current_user_id(self):
        """현재 사용자 ID 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # app_settings 테이블 존재 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='app_settings'")
        if not cursor.fetchone():
            return None
        
        cursor.execute("SELECT value FROM app_settings WHERE key = 'current_user_id'")
        row = cursor.fetchone()
        if row and row[0]:
            return int(row[0])
        return None
    
    def get_current_user(self):
        """
        현재 선택된 사용자 조회 (v13 NEW!)
        - current_user_id가 설정되어 있으면 해당 사용자 반환
        - 없으면 가장 최근 생성된 사용자 반환
        """
        current_id = self.get_current_user_id()
        
        if current_id:
            user = self.get_user_profile(current_id)
            if user:
                return user
        
        # current_user_id가 없거나 해당 사용자가 없으면 latest 반환
        return self.get_latest_user()
    
    # ========== 사용자 관리 ==========
    
    def _normalize_gender(self, gender):
        """
        성별 표준화 함수 - 모든 성별 표현을 '남자' 또는 '여자'로 통일
        """
        if not gender:
            return None
        
        gender = str(gender).strip()
        
        # 남성 계열
        if gender in ['남자', '남성', 'male', 'Male', 'MALE', 'M', 'm', '남']:
            return '남자'
        # 여성 계열  
        elif gender in ['여자', '여성', 'female', 'Female', 'FEMALE', 'F', 'f', '여']:
            return '여자'
        
        return gender  # 알 수 없는 경우 그대로 반환
    
    def save_user_profile(self, name, age, diseases, gender=None, 
                         guardian_name=None, guardian_phone=None, guardian_email=None, guardian_relation=None):
        """사용자 프로필 저장 (새로 생성)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 성별 표준화 (남성→남자, 여성→여자)
        normalized_gender = self._normalize_gender(gender)
        
        diseases_json = json.dumps(diseases, ensure_ascii=False) if isinstance(diseases, list) else diseases
        
        cursor.execute("""
            INSERT INTO users (name, age, gender, diseases, guardian_name, guardian_phone, guardian_email, guardian_relation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, age, normalized_gender, diseases_json, guardian_name, guardian_phone, guardian_email, guardian_relation))
        
        conn.commit()
        return cursor.lastrowid
    
    def update_user_profile(self, user_id, name, age, diseases, gender=None,
                           guardian_name=None, guardian_phone=None, guardian_email=None, guardian_relation=None):
        """
        기존 프로필 수정 (v13 NEW!)
        - 기존 데이터를 유지하면서 업데이트
        - 연결된 스캔 이력은 그대로 유지
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        normalized_gender = self._normalize_gender(gender)
        diseases_json = json.dumps(diseases, ensure_ascii=False) if isinstance(diseases, list) else diseases
        
        # guardian_email 컬럼 존재 여부 확인
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'guardian_email' in columns and 'updated_at' in columns:
            # 새 컬럼이 있는 경우
            cursor.execute("""
                UPDATE users 
                SET name = ?, age = ?, gender = ?, diseases = ?, 
                    guardian_name = ?, guardian_phone = ?, guardian_email = ?, guardian_relation = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (name, age, normalized_gender, diseases_json, 
                  guardian_name, guardian_phone, guardian_email, guardian_relation, user_id))
        elif 'guardian_email' in columns:
            # guardian_email만 있고 updated_at은 없는 경우
            cursor.execute("""
                UPDATE users 
                SET name = ?, age = ?, gender = ?, diseases = ?, 
                    guardian_name = ?, guardian_phone = ?, guardian_email = ?, guardian_relation = ?
                WHERE id = ?
            """, (name, age, normalized_gender, diseases_json, 
                  guardian_name, guardian_phone, guardian_email, guardian_relation, user_id))
        else:
            # 기존 DB (새 컬럼 없음)
            cursor.execute("""
                UPDATE users 
                SET name = ?, age = ?, gender = ?, diseases = ?, 
                    guardian_name = ?, guardian_phone = ?, guardian_relation = ?
                WHERE id = ?
            """, (name, age, normalized_gender, diseases_json, 
                  guardian_name, guardian_phone, guardian_relation, user_id))
        
        conn.commit()
        success = cursor.rowcount > 0
        
        if success:
            print(f"✅ 프로필 수정 완료: {name} (ID: {user_id})")
        return success
    
    def delete_user_profile(self, user_id):
        """프로필 삭제 (연결된 스캔 이력, 기관 연동도 함께 삭제)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM scans WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM health_institutions WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        
        conn.commit()
        return cursor.rowcount > 0
    
    def search_users_by_name(self, name):
        """
        이름으로 프로필 검색 (동명이인 모두 반환!) - v13 NEW!
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # updated_at 컬럼 존재 여부 확인
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'updated_at' in columns:
            cursor.execute("""
                SELECT * FROM users 
                WHERE name LIKE ?
                ORDER BY updated_at DESC
            """, (f"%{name}%",))
        else:
            cursor.execute("""
                SELECT * FROM users 
                WHERE name LIKE ?
                ORDER BY id DESC
            """, (f"%{name}%",))
        
        rows = cursor.fetchall()
        
        users = []
        for row in rows:
            row_columns = row.keys()
            diseases = row["diseases"]
            if diseases:
                try:
                    diseases = json.loads(diseases)
                except:
                    diseases = [d.strip() for d in diseases.split(',') if d.strip()]
            else:
                diseases = []
            
            users.append({
                "id": row["id"],
                "name": row["name"],
                "age": row["age"],
                "gender": row["gender"],
                "diseases": diseases,
                "guardian_name": row["guardian_name"],
                "guardian_phone": row["guardian_phone"],
                "guardian_email": row["guardian_email"] if "guardian_email" in row_columns else None,
                "guardian_relation": row["guardian_relation"]
            })
        
        return users
        
        return users
    
    def get_user_profile(self, user_id):
        """사용자 프로필 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        
        if row:
            # 컬럼 이름 목록 가져오기
            columns = row.keys()
            
            return {
                "id": row["id"],
                "name": row["name"],
                "age": row["age"],
                "gender": self._normalize_gender(row["gender"]),  # 읽을 때도 표준화
                "diseases": json.loads(row["diseases"]) if row["diseases"] else [],
                "guardian_name": row["guardian_name"],
                "guardian_phone": row["guardian_phone"],
                "guardian_email": row["guardian_email"] if "guardian_email" in columns else None,
                "guardian_relation": row["guardian_relation"]
            }
        return None
    
    def get_latest_user(self):
        """최신 사용자 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        
        if row:
            return self.get_user_profile(row["id"])
        return None
    
    def get_all_users(self):
        """모든 사용자 목록 조회 (자동완성용)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users ORDER BY name")
        rows = cursor.fetchall()
        
        users = []
        for row in rows:
            columns = row.keys()
            users.append({
                "id": row["id"],
                "name": row["name"],
                "age": row["age"],
                "gender": row["gender"],
                "diseases": json.loads(row["diseases"]) if row["diseases"] else [],
                "guardian_name": row["guardian_name"],
                "guardian_phone": row["guardian_phone"],
                "guardian_email": row["guardian_email"] if "guardian_email" in columns else None,
                "guardian_relation": row["guardian_relation"]
            })
        return users
    
    # ========== 건강관리기관 연동 (v13 NEW!) ==========
    
    def add_health_institution(self, user_id, name, inst_type, phone=None, email=None):
        """건강관리기관 연동 추가"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO health_institutions (user_id, name, type, phone, email)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, name, inst_type, phone, email))
        
        conn.commit()
        return cursor.lastrowid
    
    def update_health_institution(self, inst_id, phone=None, email=None, is_connected=1):
        """건강관리기관 연동 정보 수정"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE health_institutions 
            SET phone = ?, email = ?, is_connected = ?
            WHERE id = ?
        """, (phone, email, is_connected, inst_id))
        
        conn.commit()
        return cursor.rowcount > 0
    
    def get_health_institutions(self, user_id):
        """사용자의 연동된 건강관리기관 목록"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM health_institutions 
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    
    def get_institution_by_name(self, user_id, name):
        """특정 기관 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM health_institutions 
            WHERE user_id = ? AND name = ?
        """, (user_id, name))
        
        row = cursor.fetchone()
        return dict(row) if row else None
    
    def delete_health_institution(self, inst_id):
        """건강관리기관 연동 삭제"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM health_institutions WHERE id = ?", (inst_id,))
        conn.commit()
        return cursor.rowcount > 0
    
    # ========== 영양소 정보 ==========
    
    def get_ingredient_info(self, ingredient_name):
        """성분 정보 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM ingredients_db 
            WHERE name LIKE ?
        """, (f"%{ingredient_name}%",))
        
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    
    def get_daily_intake(self, ingredient, age, gender=None):
        """
        1일 권장량 조회 (성별/연령 기반)
        
        Args:
            ingredient: 영양소 이름
            age: 나이
            gender: 성별 (어떤 형태든 자동 변환됨)
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 성별 표준화 (남성→남자, 여성→여자 등)
        db_gender = self._normalize_gender(gender)
        
        # 검색 패턴 생성 (원본 + 변형들)
        search_patterns = [ingredient]
        
        # 비타민 띄어쓰기 변형 추가
        import re
        if '비타민' in ingredient:
            # "비타민D" → "비타민 D" 추가
            if ' ' not in ingredient:
                spaced = re.sub(r'(비타민)([A-Za-z0-9])', r'\1 \2', ingredient)
                if spaced != ingredient:
                    search_patterns.append(spaced)
            # "비타민 D" → "비타민D" 추가
            else:
                no_space = ingredient.replace(' ', '')
                if no_space != ingredient:
                    search_patterns.append(no_space)
        
        for search_name in search_patterns:
            # 1. 성별 + 연령 매칭
            if db_gender:
                cursor.execute("""
                    SELECT * FROM daily_intake 
                    WHERE ingredient LIKE ?
                    AND age_min <= ? AND age_max >= ?
                    AND gender = ?
                    ORDER BY original_text DESC
                    LIMIT 1
                """, (f"%{search_name}%", age, age, db_gender))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
            
            # 2. 성별 무관 데이터
            cursor.execute("""
                SELECT * FROM daily_intake 
                WHERE ingredient LIKE ?
                AND age_min <= ? AND age_max >= ?
                AND (gender IS NULL OR gender = '')
                ORDER BY original_text DESC
                LIMIT 1
            """, (f"%{search_name}%", age, age))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            # 3. Fallback - 성별 상관없이 연령만 매칭
            cursor.execute("""
                SELECT * FROM daily_intake 
                WHERE ingredient LIKE ?
                AND age_min <= ? AND age_max >= ?
                ORDER BY original_text DESC
                LIMIT 1
            """, (f"%{search_name}%", age, age))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
        
        return None
    
    # ========== 질환-영양성분 상호작용 ==========
    
    def check_disease_interaction(self, nutrient, disease):
        """
        질환-영양성분 상호작용 확인
        - 공백 변형 자동 처리 (비타민C ↔ 비타민 C)
        """
        import re
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # 검색 패턴 생성 (원본 + 변형들)
        search_patterns = [nutrient]
        
        # 비타민 띄어쓰기 변형 추가
        if '비타민' in nutrient:
            if ' ' not in nutrient:
                spaced = re.sub(r'(비타민)([A-Za-z0-9])', r'\1 \2', nutrient)
                if spaced != nutrient:
                    search_patterns.append(spaced)
            else:
                no_space = nutrient.replace(' ', '')
                if no_space != nutrient:
                    search_patterns.append(no_space)
        
        # 각 패턴으로 검색
        for search_name in search_patterns:
            # 정확한 매칭
            cursor.execute("""
                SELECT * FROM disease_interactions 
                WHERE nutrient = ? AND disease = ?
            """, (search_name, disease))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
            
            # 부분 매칭
            cursor.execute("""
                SELECT * FROM disease_interactions 
                WHERE (nutrient LIKE ? OR ? LIKE '%' || nutrient || '%')
                AND (disease LIKE ? OR ? LIKE '%' || disease || '%')
            """, (f"%{search_name}%", search_name, f"%{disease}%", disease))
            
            row = cursor.fetchone()
            if row:
                return dict(row)
        
        return None
    
    def get_all_interactions_for_diseases(self, diseases):
        """여러 질환에 대한 모든 상호작용 조회"""
        if not diseases:
            return []
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join(['?' for _ in diseases])
        query = f"""
            SELECT * FROM disease_interactions 
            WHERE disease IN ({placeholders})
        """
        
        cursor.execute(query, diseases)
        rows = cursor.fetchall()
        
        return [dict(row) for row in rows]
    
    # ========== 스캔 이력 ==========
    
    def save_scan_result(self, user_id, image_path, product_name, ingredients, safety_result, dri_result):
        """스캔 결과 저장"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO scans 
            (user_id, image_path, product_name, ingredients, safety_result, dri_result)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            image_path,
            product_name,
            json.dumps(ingredients, ensure_ascii=False),
            json.dumps(safety_result, ensure_ascii=False),
            json.dumps(dri_result, ensure_ascii=False)
        ))
        
        conn.commit()
        return cursor.lastrowid
    
    def get_scan_history(self, user_id, limit=30):
        """스캔 이력 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM scans 
            WHERE user_id = ?
            ORDER BY scan_date DESC
            LIMIT ?
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        
        history = []
        for row in rows:
            history.append({
                "id": row["id"],
                "product_name": row["product_name"],
                "scan_date": row["scan_date"],
                "ingredients": json.loads(row["ingredients"]),
                "safety_result": json.loads(row["safety_result"]),
                "dri_result": json.loads(row["dri_result"])
            })
        
        return history
    
    def get_scan_by_id(self, scan_id):
        """특정 스캔 결과 조회"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "id": row["id"],
                "product_name": row["product_name"],
                "scan_date": row["scan_date"],
                "image_path": row["image_path"],
                "ingredients": json.loads(row["ingredients"]),
                "safety_result": json.loads(row["safety_result"]),
                "dri_result": json.loads(row["dri_result"])
            }
        return None
    
    def get_monthly_stats(self, user_id, year, month):
        """월별 통계"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as scan_count,
                   scan_date
            FROM scans 
            WHERE user_id = ?
            AND strftime('%Y', scan_date) = ?
            AND strftime('%m', scan_date) = ?
            GROUP BY DATE(scan_date)
            ORDER BY scan_date
        """, (user_id, str(year), f"{month:02d}"))
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

# 호환성을 위한 별칭
Database = NutriDatabase
