"""
뉴트리-스캐너 분석 엔진
1. 안전성 분석 (질환-영양성분 궁합)
2. 1일 권장량 분석
3. 종합 위험도 판정
"""


class SafetyAnalyzer:
    def __init__(self, database):
        """분석기 초기화"""
        self.db = database
    
    def _format_unit_display(self, unit):
        """
        단위 표시 형식 변환 (mcg → µg)
        """
        if not unit:
            return unit
        return unit.lower().replace('mcg', 'µg').replace('ug', 'µg').replace('μg', 'µg')
    
    def _convert_unit(self, amount, from_unit, to_unit):
        """
        단위 변환 함수
        
        지원 단위: g, mg, mcg(μg, ug)
        
        예시:
        - 24g → mg: 24 * 1000 = 24000mg
        - 16800mcg → mg: 16800 / 1000 = 16.8mg
        """
        from_unit = from_unit.lower().strip()
        to_unit = to_unit.lower().strip()
        
        # μg, ug, µg를 mcg로 통일 (다양한 유니코드 마이크로 기호 처리)
        # µ (U+00B5 micro sign), μ (U+03BC Greek mu) 모두 처리
        if from_unit in ['μg', 'ug', 'µg', '\u00b5g', '\u03bcg']:
            from_unit = 'mcg'
        if to_unit in ['μg', 'ug', 'µg', '\u00b5g', '\u03bcg']:
            to_unit = 'mcg'
        
        # 같은 단위면 그대로 반환
        if from_unit == to_unit:
            return amount
        
        # mg를 기준으로 변환
        # 먼저 from_unit → mg
        if from_unit == 'g':
            amount_in_mg = amount * 1000
        elif from_unit == 'mcg':
            amount_in_mg = amount / 1000
        elif from_unit == 'mg':
            amount_in_mg = amount
        else:
            # 알 수 없는 단위는 그대로 반환
            return amount
        
        # mg → to_unit (부동소수점 오류 방지를 위해 round() 적용)
        if to_unit == 'g':
            return round(amount_in_mg / 1000, 6)
        elif to_unit == 'mcg':
            return round(amount_in_mg * 1000, 6)
        elif to_unit == 'mg':
            return round(amount_in_mg, 6)
        else:
            # 알 수 없는 단위는 mg 값 반환
            return round(amount_in_mg, 6)
    
    def analyze_safety(self, ingredients, user_profile):
        """
        안전성 분석 (질환 기반)
        
        반환: {
            "overall_risk": "safe" | "warning" | "danger",
            "warnings": [...],
            "recommendations": [...]
        }
        """
        
        if not user_profile or not user_profile.get("diseases"):
            return {
                "overall_risk": "safe",
                "warnings": [],
                "recommendations": []
            }
        
        diseases = user_profile["diseases"]
        warnings = []
        recommendations = []
        
        # 각 성분에 대해 질환과의 상호작용 확인
        for ing in ingredients:
            ingredient_name = ing["name"]
            
            for disease in diseases:
                # DB에서 상호작용 조회
                interaction = self.db.check_disease_interaction(ingredient_name, disease)
                
                if interaction:
                    if interaction["category"] == "주의":
                        warnings.append({
                            "ingredient": ingredient_name,
                            "disease": disease,
                            "category": "주의",
                            "reason": interaction["reason"],
                            "risk_level": "warning",
                            "icon": "🟡",
                            "message": f"{ingredient_name}은(는) {disease} 환자에게 주의가 필요합니다"
                        })
                    elif interaction["category"] == "권장":
                        recommendations.append({
                            "ingredient": ingredient_name,
                            "disease": disease,
                            "category": "권장",
                            "reason": interaction["reason"],
                            "risk_level": "safe",
                            "icon": "✅",
                            "message": f"{ingredient_name}은(는) {disease}에 도움이 됩니다"
                        })
        
        # 전체 위험도 판정
        if len(warnings) >= 2:
            overall_risk = "danger"
        elif len(warnings) == 1:
            overall_risk = "warning"
        else:
            overall_risk = "safe"
        
        return {
            "overall_risk": overall_risk,
            "warnings": warnings,
            "recommendations": recommendations
        }
    
    def analyze_daily_intake(self, ingredients, user_profile):
        """
        1일 권장량 대비 섭취량 분석 (성별/연령 기반)
        
        반환: [
            {
                "ingredient": "비타민C",
                "amount": 100,
                "min_recommended": 30,
                "max_recommended": 1000,
                "percentage": 100,
                "status": "적정" | "부족" | "주의" | "과다"
            }
        ]
        """
        
        if not user_profile:
            return []
        
        age = user_profile.get("age", 30)
        gender = user_profile.get("gender", "남자")  # 성별 추가!
        results = []
        
        for ing in ingredients:
            ingredient_name = ing["name"]
            amount = ing["amount"]
            unit = ing["unit"].lower().strip()
            
            # 1일 권장량 조회 (성별/연령 기반!)
            dri = self.db.get_daily_intake(ingredient_name, age, gender)
            
            if dri:
                min_amount = dri.get("min_amount", 0)
                max_amount = dri.get("max_amount", 0)
                recommended = dri.get("recommended_amount", 0)
                
                # 권장량 단위 추출 (DB의 단위)
                dri_unit = dri.get("unit", "mg").lower().strip()
                
                # 섭취량을 권장량 단위로 변환
                amount_converted = self._convert_unit(amount, unit, dri_unit)
                
                # 표시용 단위 (권장량 단위 사용)
                display_unit = dri.get("unit", "mg")
                
                # 상태 판정
                if amount_converted < min_amount:
                    status = "부족"
                    message = f"권장 최소량({min_amount:.1f}{display_unit}) 미만"
                    icon = "⚠️"
                    color = "warning"
                    percentage = (amount_converted / min_amount) * 100 if min_amount > 0 else 0
                    
                elif min_amount <= amount_converted <= max_amount:
                    status = "적정"
                    message = "적정 범위"
                    icon = "✅"
                    color = "success"
                    percentage = (amount_converted / recommended) * 100 if recommended > 0 else 0
                    
                elif amount_converted > max_amount:
                    over_percent = ((amount_converted - max_amount) / max_amount) * 100 if max_amount > 0 else 0
                    
                    if over_percent <= 20:
                        status = "주의"
                        message = f"권장 최대량({max_amount:.1f}{display_unit}) 약간 초과"
                        icon = "🟡"
                        color = "warning"
                    else:
                        status = "과다"
                        message = f"권장 최대량({max_amount:.1f}{display_unit}) 크게 초과"
                        icon = "🔴"
                        color = "danger"
                    
                    percentage = (amount_converted / max_amount) * 100 if max_amount > 0 else 0
                
                results.append({
                    "ingredient": ingredient_name,
                    "amount": amount_converted,  # 변환된 양
                    "unit": self._format_unit_display(display_unit),  # 권장량 단위로 통일 (µg 형식)
                    "original_amount": amount,  # 원래 입력값
                    "original_unit": self._format_unit_display(ing["unit"]),  # 원래 단위 (µg 형식)
                    "min_recommended": min_amount,
                    "recommended": recommended,
                    "max_recommended": max_amount,
                    "percentage": round(percentage, 1),
                    "status": status,
                    "message": message,
                    "icon": icon,
                    "color": color,
                    "original_text": dri.get("original_text", "")
                })
            else:
                # 권장량 정보 없음
                results.append({
                    "ingredient": ingredient_name,
                    "amount": amount,
                    "unit": self._format_unit_display(unit),
                    "amount_mg": None,
                    "min_recommended": None,
                    "recommended": None,
                    "max_recommended": None,
                    "percentage": None,
                    "status": "정보없음",
                    "message": "식약처 기준 정보 없음",
                    "icon": "❓",
                    "color": "secondary",
                    "original_text": ""
                })
        
        return results
    
    def generate_advice(self, safety_result, dri_result, user_profile):
        """
        종합 조언 생성
        """
        advice = []
        
        # 안전성 경고
        if safety_result["warnings"]:
            advice.append({
                "type": "warning",
                "title": "⚠️ 주의 필요",
                "message": f"{len(safety_result['warnings'])}개 성분에 대한 주의가 필요합니다"
            })
        
        # 권장 성분
        if safety_result["recommendations"]:
            advice.append({
                "type": "success",
                "title": "✅ 권장 성분",
                "message": f"{len(safety_result['recommendations'])}개 성분이 건강에 도움이 됩니다"
            })
        
        # 과다 섭취
        excessive = [d for d in dri_result if d["status"] == "과다"]
        if excessive:
            advice.append({
                "type": "danger",
                "title": "🔴 과다 섭취",
                "message": f"{len(excessive)}개 성분이 권장량을 크게 초과합니다"
            })
        
        # 부족
        insufficient = [d for d in dri_result if d["status"] == "부족"]
        if insufficient:
            advice.append({
                "type": "info",
                "title": "ℹ️ 부족",
                "message": f"{len(insufficient)}개 성분이 권장량에 미달합니다"
            })
        
        return advice
