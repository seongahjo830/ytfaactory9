import os
import glob
import re
import time
import shutil
import gspread
from gspread.exceptions import APIError
from oauth2client.service_account import ServiceAccountCredentials
import google.generativeai as genai
import requests
import base64
import random
import openai
import fal_client
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

# .env 파일 지원 (선택적)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==========================================
# 1. 설정 및 경로 정의
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_OUTPUT_DIR = os.path.join(os.path.dirname(CURRENT_DIR), "02_Output")

# ⭐️ 프롬프트 파일 경로: _System\04_Co_Asset\ImagePrompt
PROMPT_BASE_DIR = r"C:\YtFactory9\_System\04_Co_Asset\ImagePrompt"

JSON_KEY_FILE = r"C:\YtFactory9\_System\02_Key\service_account.json"
SHEET_URL_FILE = r"C:\YtFactory9\_System\00_Engine\YtFactory9_URL.txt"

# 워크플로우별 고유 auto_sheet 파일 (환경변수 우선)
ENV_AUTO_SHEET = os.environ.get("YTF_AUTO_SHEET_FILE")
if ENV_AUTO_SHEET and ENV_AUTO_SHEET.strip():
    AUTO_SHEET_FILE = ENV_AUTO_SHEET.strip()
else:
    AUTO_SHEET_FILE = os.path.join(CURRENT_DIR, "_auto_sheet.txt")

# 모델 목록 (성공률 높은 순서로 정렬)
IMAGE_MODELS_CANDIDATES = [
    'imagen-4.0-generate-001',  # 🥇 1순위 (성공률 최고)
    'imagen-3.0-generate-001',   # 🥈 2순위 (유료 계정 필요)
    # 'image-generation-002' 제거 (항상 404 발생)
]

# DeepInfra (Black Forest FLUX) 설정
DEEPINFRA_KEY_FILE = r"C:\YtFactory9\_System\02_Key\KeyKeyDeepInfra.txt"

# Fal 설정
FAL_KEY_FILE = r"C:\YtFactory9\_System\02_Key\KeyKeyFal.txt"
FAL_ROOT_IMAGE_DIR = r"C:\YtFactory9\_System\04_Co_Asset\ImagePrompt\fal_RootImage"

LAST_SUCCESSFUL_KEY = None

# ==========================================
# 1.5. 키 관리자 (KeyManager) 클래스
# ==========================================
class KeyManager:
    """
    API 키의 상태를 3가지로 스마트하게 관리하는 클래스
    - Alive: 사용 가능한 키 (🟢)
    - Waiting: 대기 중인 키 (🟡) - 429 Rate Limit 등
    - Dead: 사용 불가능한 키 (🔴) - 403, Quota Exceeded 등
    """
    
    def __init__(self, api_keys):
        """
        초기화: 모든 키를 alive_keys에 저장
        Args:
            api_keys: API 키 리스트
        """
        self.alive_keys = list(api_keys)  # 사용 가능한 키 리스트
        self.waiting_keys = []  # (key, next_try_time) 튜플 리스트
        self.dead_keys = []  # 영구적으로 사용 불가능한 키 리스트 (실제로는 거의 사용 안 함)
        self.current_index = 0  # Round Robin을 위한 인덱스
        # 키별 모델 가용성 추적: {key: {model_name: 'available'|'unavailable'|'unknown'}}
        self.key_model_availability = {}  # 키별로 어떤 모델이 작동하는지 기록
        self.last_successful_key = None  # 마지막 성공한 키 (우선 사용)
    
    def get_next_key(self):
        """
        다음 사용할 키를 반환 (성공한 키 우선 사용)
        우선순위:
        1. 마지막 성공한 키가 alive_keys에 있으면 우선 반환
        2. alive_keys에 키가 있으면 Round Robin 방식으로 반환
        3. alive_keys가 비어있으면 waiting_keys 확인 (next_try_time이 지났으면 alive로 복귀)
        4. 사용 가능한 키가 없으면 None 반환
        
        Returns:
            str or None: 사용할 키 또는 None
        """
        # 우선순위 1: 마지막 성공한 키가 있으면 우선 사용
        if self.last_successful_key and self.last_successful_key in self.alive_keys:
            return self.last_successful_key
        
        # 우선순위 2: Alive 키 확인 (Round Robin)
        if self.alive_keys:
            key = self.alive_keys[self.current_index % len(self.alive_keys)]
            self.current_index += 1
            return key
        
        # 우선순위 3: Waiting 키 확인 (시간이 지났으면 Alive로 복귀)
        current_time = time.time()
        ready_keys = []
        still_waiting = []
        
        for key, next_try_time in self.waiting_keys:
            if current_time >= next_try_time:
                ready_keys.append(key)  # 시간이 지난 키는 Alive로 복귀
            else:
                still_waiting.append((key, next_try_time))  # 아직 대기 중인 키
        
        # Waiting 키 업데이트
        self.waiting_keys = still_waiting
        
        # 준비된 키가 있으면 Alive로 복귀시키고 첫 번째 키 반환
        if ready_keys:
            self.alive_keys.extend(ready_keys)
            return ready_keys[0]
        
        # 우선순위 4: 사용 가능한 키 없음 (Dead 키는 이제 사용 안 함 - Waiting만 사용)
        # 구버전처럼 모든 키를 다시 시도하는 대신, Waiting 키만 재사용
        return None
    
    def report_status(self, key, status):
        """
        키 사용 결과를 보고받아 상태를 업데이트
        Args:
            key: 상태를 업데이트할 키
            status: 'success', '429', '403', 'quota', 'Invalid' 중 하나
        """
        # Alive에서 제거 (있다면)
        if key in self.alive_keys:
            self.alive_keys.remove(key)
        
        # Waiting에서 제거 (있다면)
        self.waiting_keys = [(k, t) for k, t in self.waiting_keys if k != key]
        
        # Dead에서도 제거 (있다면, 중복 방지)
        if key in self.dead_keys:
            self.dead_keys.remove(key)
        
        # 상태에 따라 적절한 리스트로 이동
        if status == 'success':
            # 성공: Alive 맨 앞에 추가 (우선 사용), 마지막 성공 키로 설정
            self.alive_keys.insert(0, key)
            self.last_successful_key = key
        elif status == '429':
            # Rate Limit: Waiting으로 이동 (현재 시간 + 2초 후 재시도)
            next_try_time = time.time() + 2
            self.waiting_keys.append((key, next_try_time))
        elif status in ['403', 'quota', 'Invalid']:
            # 403/Quota Exceeded: Dead 리스트로 즉시 이동 (이번 실행에서 영구 제외)
            # 재시도 없음, sleep 없음 - 죽은 키는 즉시 버림
            self.dead_keys.append(key)
    
    def mark_model_unavailable(self, key, model_name):
        """
        특정 키에서 특정 모델이 작동하지 않음을 기록
        Args:
            key: API 키
            model_name: 모델명
        """
        if key not in self.key_model_availability:
            self.key_model_availability[key] = {}
        self.key_model_availability[key][model_name] = 'unavailable'
    
    def mark_model_available(self, key, model_name):
        """
        특정 키에서 특정 모델이 작동함을 기록
        Args:
            key: API 키
            model_name: 모델명
        """
        if key not in self.key_model_availability:
            self.key_model_availability[key] = {}
        self.key_model_availability[key][model_name] = 'available'
    
    def get_available_models_for_key(self, key):
        """
        특정 키에서 사용 가능한 모델 리스트 반환 (우선순위 정렬)
        Args:
            key: API 키
        Returns:
            list: 시도할 모델 리스트 (우선순위 순서)
        """
        available_models = []
        unavailable_models = []
        unknown_models = []
        
        key_availability = self.key_model_availability.get(key, {})
        
        for model in IMAGE_MODELS_CANDIDATES:
            status = key_availability.get(model, 'unknown')
            if status == 'available':
                available_models.append(model)
            elif status == 'unavailable':
                unavailable_models.append(model)
            else:  # unknown
                unknown_models.append(model)
        
        # 우선순위: available > unknown > unavailable (unavailable은 제외)
        return available_models + unknown_models
    
    def print_status(self):
        """현재 키 상태를 출력"""
        print(f"🔑 [KeyManager 상태]")
        print(f"   🟢 Alive (사용 가능): {len(self.alive_keys)}개")
        print(f"   🟡 Waiting (대기 중): {len(self.waiting_keys)}개")
        print(f"   🔴 Dead (사용 불가): {len(self.dead_keys)}개")
        if self.alive_keys:
            print(f"   💡 다음 사용할 키: {self.alive_keys[self.current_index % len(self.alive_keys)][:10]}...")

# ==========================================
# 2. 유틸리티 함수 (키 로드 & 템플릿)
# ==========================================
def retry_on_quota_exceeded(func, max_retries=5, wait_time=60):
    """
    구글 시트 API 429 에러(Quota exceeded) 발생 시 재시도하는 헬퍼 함수
    
    Args:
        func: 실행할 함수 (인자 없이 호출 가능한 람다 또는 함수)
        max_retries: 최대 재시도 횟수 (기본값: 5)
        wait_time: 재시도 전 대기 시간(초) (기본값: 60)
    
    Returns:
        함수의 반환값
    
    Raises:
        APIError: 최대 재시도 횟수 초과 시
    """
    for attempt in range(max_retries):
        try:
            return func()
        except APIError as e:
            error_code = None
            error_msg = str(e).lower()
            
            # APIError의 response 속성에서 상태 코드 추출 시도
            try:
                if hasattr(e, 'response'):
                    if isinstance(e.response, dict):
                        error_code = e.response.get('status')
                    elif hasattr(e.response, 'status'):
                        error_code = e.response.status
            except:
                pass
            
            # 429 에러 또는 "Quota exceeded" 메시지 확인
            is_quota_error = (
                error_code == 429 or 
                "429" in str(e) or 
                "quota exceeded" in error_msg or 
                "quota" in error_msg
            )
            
            if is_quota_error:
                if attempt < max_retries - 1:
                    print(f"⚠️ 구글 시트 할당량 초과 (429). {wait_time}초 대기 후 재시도합니다... ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ 구글 시트 할당량 초과. 최대 재시도 횟수({max_retries}) 초과.")
                    raise
            else:
                # 429가 아닌 다른 APIError는 즉시 재발생
                raise
        except Exception as e:
            # APIError가 아닌 다른 예외는 즉시 재발생
            if isinstance(e, APIError):
                raise
            # 일반 예외도 그대로 재발생
            raise
    # 이론적으로 도달하지 않지만 타입 체커를 위해
    raise APIError("재시도 실패")

def load_spreadsheet(client):
    """
    Sheet_URL.txt 내용을 읽어서 스프레드시트에 접속.
    - URL 전체를 넣어두면 open_by_url 사용
    - ID만 넣어두면 open_by_key 사용
    - 429 에러 발생 시 자동 재시도
    """
    if not os.path.exists(SHEET_URL_FILE):
        raise FileNotFoundError(f"Sheet_URL.txt 파일을 찾을 수 없습니다: {SHEET_URL_FILE}")

    with open(SHEET_URL_FILE, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    if not raw:
        raise ValueError("Sheet_URL.txt 파일이 비어 있습니다.")

    def _open_spreadsheet():
        if "https://docs.google.com" in raw:
            return client.open_by_url(raw)
        else:
            return client.open_by_key(raw)
    
    return retry_on_quota_exceeded(_open_spreadsheet)


def get_gemini_keys():
    all_keys = []
    key_dir = r"C:\YtFactory9\_System\02_Key"
    key_files = glob.glob(os.path.join(key_dir, "KeyKey*.txt"))
    print(f"🔍 키 파일 탐색 경로: {key_dir}")
    print(f"🔍 발견된 키 파일: {[os.path.basename(k) for k in key_files]}")

    for kf in key_files:
        try:
            with open(kf, 'r', encoding='utf-8') as f:
                content = f.read()
                found = re.findall(r'(AIza[a-zA-Z0-9_-]{35})', content)
                all_keys.extend(found)
        except: pass

    all_keys = list(set(all_keys))
    random.shuffle(all_keys)
    print(f"🔑 로드된 총 API 키 개수: {len(all_keys)}개")
    return all_keys

def load_prompt_template(style_char):
    """
    프롬프트 템플릿 파일을 로드합니다.
    - 1순위: F열 값과 **완전히 같은 이름**의 텍스트 파일
      예) F열: `동화2D일러스트` → `동화2D일러스트.txt`
    - 2순위: F열 값을 **포함하는** 모든 텍스트 파일 중,
      파일명을 오름차순 정렬했을 때 가장 앞에 있는 것
      예) `07_삼촌조카_동화2D일러스트.txt`, `08_삼촌조카_동화2D일러스트.txt`
          → `07_...`를 선택
    - 경로: C:\\YtFactory9\\_System\\04_Co_Asset\\ImagePrompt
    """
    keyword = style_char.strip()
    if not keyword:
        return None

    # 1순위: 키워드와 완전히 동일한 파일명 (동화2D일러스트 → 동화2D일러스트.txt)
    exact_path = os.path.join(PROMPT_BASE_DIR, f"{keyword}.txt")
    if os.path.exists(exact_path):
        try:
            # 어떤 텍스트 파일을 참조했는지 터미널에 그대로 표시
            # 예) 07_삼촌조카_동화2D일러스트.txt
            print(os.path.basename(exact_path))
            with open(exact_path, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return None

    # 2순위: 키워드를 포함하는 모든 txt 파일 중 이름순으로 가장 앞에 있는 것
    pattern = os.path.join(PROMPT_BASE_DIR, f"*{keyword}*.txt")
    candidate_files = glob.glob(pattern)

    if candidate_files:
        # 파일 이름 기준(전체 경로 말고 basename)으로 정렬
        candidate_files.sort(key=lambda p: os.path.basename(p))
        chosen = candidate_files[0]
        try:
            # 포함 일치로 선택된 경우에도 파일명을 그대로 출력
            print(os.path.basename(chosen))
            with open(chosen, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return None

    # 아무 것도 못 찾은 경우
    print(f"  ⚠️ 프롬프트 템플릿을 찾지 못했습니다. (키워드: {keyword})")
    return None

# ==========================================
# 3. AI 생성 함수 (좀비 모드 적용 + 잡담 제거 강화)
# ==========================================
def clean_prompt_text(raw_text):
    """
    Gemini 응답에서 잡담, 마크다운, 메타 설명을 제거하여 순수 프롬프트만 추출
    강화된 정제 로직: 콜론 절단, 샌드위치 제거 등
    
    Args:
        raw_text: Gemini가 생성한 원본 텍스트
    
    Returns:
        str: 정제된 프롬프트 텍스트 (에러 발생 시 원본 반환)
    """
    if not raw_text:
        return None
    
    try:
        cleaned = raw_text.strip()
        
        # 1. 앞부분 잡담 제거 (Okay, Here is, Prompt: 등)
        cleaned = re.sub(
            r"^(Okay|Sure|Here is|Certainly|Prompt|Image Prompt|Based on|I will|I'm ready|I understand|I can|The generated prompt|Here's the prompt).*?(\n|:|\*\*)",
            "",
            cleaned,
            flags=re.IGNORECASE | re.DOTALL
        ).strip()
        
        # 2. 콜론(:) 절단 로직 - 앞부분 50자 이내에 콜론이 있으면 앞부분 제거
        first_50_chars = cleaned[:50]
        colon_pos = first_50_chars.find(':')
        if colon_pos != -1:
            # 콜론 뒤의 내용만 취함
            cleaned = cleaned[colon_pos + 1:].strip()
            # 콜론 뒤에 공백이나 특수문자가 있으면 제거
            cleaned = re.sub(r"^[\s\-]+", "", cleaned)
        
        # 3. 샌드위치 제거 ("sandwich rule", "sandwich structure" 삭제)
        cleaned = re.sub(
            r"(sandwich\s+(rule|structure|format|method)|sandwich\s+rule)",
            "",
            cleaned,
            flags=re.IGNORECASE
        ).strip()
        
        # 4. 마크다운 볼드체(**) 제거
        cleaned = cleaned.replace("**", "")
        
        # 5. 앞뒤 따옴표 제거
        cleaned = cleaned.strip('"').strip("'")
        
        # 6. 혹시 모를 앞부분 특수문자 제거 (정규식 오타 수정)
        cleaned = re.sub(r"^[-:\s]+", "", cleaned)
        
        # 7. "PROMPT:" 같은 레이블 제거
        cleaned = re.sub(r"^(PROMPT|Prompt|Image Prompt|Here's|Here is|Generated prompt|The prompt)\s*:?\s*", "", cleaned, flags=re.IGNORECASE)
        
        # 8. 여러 줄일 경우 첫 번째 의미있는 문단만 추출 (빈 줄 전까지)
        lines = cleaned.split('\n')
        meaningful_lines = []
        for line in lines:
            line = line.strip()
            # 잡담으로 시작하는 줄 제외
            if line and not line.startswith(('Okay', 'Sure', 'Here', 'Prompt', 'Based', 'I will', 'I\'m', 'The generated', 'Generated')):
                meaningful_lines.append(line)
            elif meaningful_lines:  # 이미 의미있는 내용이 있으면 중단
                break
        
        if meaningful_lines:
            cleaned = ' '.join(meaningful_lines)
        
        # 9. 최종 정리: 연속된 공백 제거
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned.strip()
    except Exception as e:
        # 정제 중 에러 발생 시 원본 반환 (구버전처럼 무조건 수용)
        print(f"  ⚠️ 정제 중 에러 발생, 원본 사용: {str(e)[:50]}")
        return raw_text.strip()


def validate_prompt_quality(prompt_text):
    """
    프롬프트 품질 검증
    
    Args:
        prompt_text: 검증할 프롬프트 텍스트
    
    Returns:
        tuple: (is_valid: bool, reason: str)
    """
    if not prompt_text:
        return (False, "빈 프롬프트")
    
    # 최소 길이 검증
    if len(prompt_text) < 50:
        return (False, f"프롬프트가 너무 짧음 ({len(prompt_text)}자)")
    
    # 금지어 검증
    forbidden_words = [
        "okay", "sure", "here is", "here's", "prompt:", "image prompt:",
        "based on", "i will", "i'm ready", "sandwich structure", "sandwich rule"
    ]
    prompt_lower = prompt_text.lower()
    for word in forbidden_words:
        if word in prompt_lower:
            return (False, f"금지어 포함: '{word}'")
    
    # 필수 스타일 키워드 검증 (돈경1,2,3 중 하나는 포함되어야 함)
    style_keywords = [
        "flat 2d", "vector", "stick figure", "cartoon style",
        "american comic", "pop art", "everyday life", "illustration"
    ]
    has_style_keyword = any(keyword in prompt_lower for keyword in style_keywords)
    if not has_style_keyword:
        return (False, "스타일 키워드 없음")
    
    # 빈 응답 요청 메시지 검증
    request_phrases = [
        "please provide", "provide the", "상황설명", "situation"
    ]
    if any(phrase in prompt_lower and len(prompt_text) < 100 for phrase in request_phrases):
        return (False, "요청 메시지로 보임")
    
    return (True, "검증 통과")


def optimize_prompt_for_flux(prompt_text):
    """
    Flux 모델 사용 시 프롬프트 최적화 (선명도 개선)
    - "hand-drawn feel", "sketchy" 같은 단어 제거
    - "clean vector", "sharp lines" 같은 단어 강조
    
    Args:
        prompt_text: 원본 프롬프트 텍스트
    
    Returns:
        str: 최적화된 프롬프트 텍스트
    """
    if not prompt_text:
        return prompt_text
    
    optimized = prompt_text
    
    # 지저분함을 유발하는 단어 제거/대체
    replacements = {
        "hand-drawn feel": "clean vector art style",
        "hand drawn feel": "clean vector art style",
        "hand-drawn": "clean vector",
        "sketchy": "clean",
        "rough": "smooth",
        "messy": "clean",
        "uneven": "even"
    }
    
    for old_word, new_word in replacements.items():
        optimized = re.sub(
            re.escape(old_word),
            new_word,
            optimized,
            flags=re.IGNORECASE
        )
    
    # 선명도를 강조하는 단어 추가 (없을 경우)
    if "clean lines" not in optimized.lower() and "sharp" not in optimized.lower():
        # 스타일 정의 부분 뒤에 추가
        if "illustration style" in optimized.lower():
            optimized = re.sub(
                r"(illustration style[^.]*)",
                r"\1 with clean, sharp lines",
                optimized,
                flags=re.IGNORECASE,
                count=1
            )
    
    return optimized


def _try_generate_with_key(key, full_prompt, candidate_models, key_manager):
    """
    단일 키로 프롬프트 생성 시도 (ThreadPoolExecutor용 헬퍼 함수)
    
    Args:
        key: 사용할 API 키
        full_prompt: 전체 프롬프트 텍스트
        candidate_models: 시도할 모델 리스트
        key_manager: KeyManager 인스턴스
    
    Returns:
        tuple: (success: bool, result: str or None, key: str, error_type: str or None)
    """
    try:
        genai.configure(api_key=key)
        
        for model_name in candidate_models:
            try:
                model = genai.GenerativeModel(model_name)
                # Timeout 5초 설정 (Google Generative AI SDK는 request_options로 timeout 지원)
                try:
                    response = model.generate_content(full_prompt, request_options={"timeout": 5})
                except TypeError:
                    # request_options가 지원되지 않는 경우 기본 호출
                    response = model.generate_content(full_prompt)
                
                if response.text:
                    # 정제 로직 적용
                    try:
                        cleaned_text = clean_prompt_text(response.text)
                    except Exception:
                        cleaned_text = response.text.strip()
                    
                    # 최소한의 검증 (빈 응답 체크)
                    if cleaned_text and len(cleaned_text.strip()) > 10:
                        key_manager.report_status(key, 'success')
                        return (True, cleaned_text, key, None)
                    else:
                        continue  # 다음 모델 시도
                else:
                    continue  # 다음 모델 시도
                    
            except Exception as api_error:
                error_msg = str(api_error)
                error_lower = error_msg.lower()
                
                # 에러 타입 분류
                if "403" in error_msg or "not been used" in error_lower or "disabled" in error_lower or "quota" in error_lower:
                    # 403/Quota: Dead로 즉시 이동 (재시도 없음)
                    key_manager.report_status(key, '403')
                    return (False, None, key, '403')
                elif "429" in error_msg or "rate limit" in error_lower:
                    # 429: Waiting으로 이동 (2초 후 재시도)
                    key_manager.report_status(key, '429')
                    return (False, None, key, '429')
                elif "404" in error_msg or "not found" in error_lower:
                    # 404: 모델명 문제, 다음 모델로 (키는 유지)
                    continue
                else:
                    # 기타 에러: 다음 모델로
                    continue
                    
    except Exception as e:
        # 키 설정 에러 등
        return (False, None, key, 'other')
    
    # 모든 모델에서 실패
    return (False, None, key, None)


def generate_prompt_text(context, template, api_keys):
    """
    YtFactory3 방식: Gemini를 사용하여 이미지 프롬프트 생성 (단순 순차 시도)
    
    Args:
        context: 상황 설명 텍스트
        template: 프롬프트 템플릿
        api_keys: API 키 리스트
    
    Returns:
        str or None: 프롬프트 텍스트
    """
    if not template:
        return None
    
    full_prompt = f"{template}\n\n[상황설명]\n{context}\n\n위 상황을 묘사하는 영어 이미지 프롬프트를 작성해줘."
    candidate_models = ['gemini-2.0-flash-exp', 'gemini-1.5-flash', 'gemini-1.5-pro']
    
    for key in api_keys:
        try:
            genai.configure(api_key=key)
            for model_name in candidate_models:
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(full_prompt)
                    if response.text:
                        return response.text.strip()
                except:
                    continue
        except:
            continue
    return None

def parse_error_type(response):
    """
    에러 타입 분류
    Args:
        response: requests.Response 객체
    Returns:
        str: 'quota', 'rate_limit', 'billed_users', 'responsible_ai', 'model_not_found', 'other'
    """
    status_code = response.status_code
    
    if status_code == 403:
        return 'quota'
    elif status_code == 429:
        return 'rate_limit'
    elif status_code == 404:
        return 'model_not_found'
    elif status_code == 400:
        # 400 에러는 메시지를 확인해야 함
        try:
            error_json = response.json()
            error_message = error_json.get('error', {}).get('message', '').lower()
            
            if 'responsible ai' in error_message or 'filtered out' in error_message:
                return 'responsible_ai'
            elif 'billed users' in error_message or 'only accessible to billed' in error_message:
                return 'billed_users'
        except:
            pass
        return 'other'
    else:
        return 'other'


def generate_image_file(prompt, filename, api_keys, save_dir):
    """
    YtFactory3 방식의 단순한 이미지 생성 함수
    - LAST_SUCCESSFUL_KEY 전역 변수 사용
    - 키를 순차적으로 시도 (성공한 키 우선)
    - 모델을 순차적으로 시도
    
    Returns:
        bool: 성공 여부
    """
    global LAST_SUCCESSFUL_KEY
    save_path = os.path.join(save_dir, f"{filename}.png")
    
    working_keys = list(api_keys)
    if LAST_SUCCESSFUL_KEY and LAST_SUCCESSFUL_KEY in working_keys:
        working_keys.remove(LAST_SUCCESSFUL_KEY)
        working_keys.insert(0, LAST_SUCCESSFUL_KEY)

    for key in working_keys:
        clean_key = key.strip()
        for model_name in IMAGE_MODELS_CANDIDATES:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:predict?key={clean_key}"
                payload = {
                    "instances": [{"prompt": prompt}],
                    "parameters": {"sampleCount": 1, "aspectRatio": "16:9"}
                }
                
                response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('predictions'):
                        b64 = result['predictions'][0]['bytesBase64Encoded']
                        with open(save_path, "wb") as f: 
                            f.write(base64.b64decode(b64))
                        print(f"-> ✅ 성공! ({save_path})")
                        LAST_SUCCESSFUL_KEY = clean_key
                        return True
                elif response.status_code == 429:
                    time.sleep(1)
                else:
                    pass
            except: 
                pass
    return False


def get_deepinfra_key():
    """
    DeepInfra API 키 로드
    1) 환경변수 DEEPINFRA_API_KEY
    2) KeyKeyDeepInfra.txt 파일
    """
    env_key = os.getenv("DEEPINFRA_API_KEY")
    if env_key and len(env_key) > 10:
        print(f"💳 DeepInfra 키 로드 (.env): {env_key[:5]}...{env_key[-5:]}")
        return env_key

    if os.path.exists(DEEPINFRA_KEY_FILE):
        try:
            with open(DEEPINFRA_KEY_FILE, 'r', encoding='utf-8') as f:
                key = f.read().strip()
                if len(key) > 10:
                    print(f"💳 DeepInfra 키 로드 (KeyKeyDeepInfra.txt): {key[:5]}...{key[-5:]}")
                    return key
        except:
            pass

    print("❌ DeepInfra 키를 찾을 수 없습니다. (.env의 DEEPINFRA_API_KEY 또는 KeyKeyDeepInfra.txt)")
    return None


def get_fal_key():
    """
    Fal API 키 로드
    1) 환경변수 FAL_KEY
    2) KeyKeyFal.txt 파일
    """
    env_key = os.getenv("FAL_KEY")
    if env_key and len(env_key) > 10:
        print(f"💳 Fal 키 로드 (.env): {env_key[:5]}...{env_key[-5:]}")
        return env_key

    if os.path.exists(FAL_KEY_FILE):
        try:
            with open(FAL_KEY_FILE, 'r', encoding='utf-8') as f:
                key = f.read().strip()
                if len(key) > 10:
                    print(f"💳 Fal 키 로드 (KeyKeyFal.txt): {key[:5]}...{key[-5:]}")
                    return key
        except:
            pass

    print("❌ Fal 키를 찾을 수 없습니다. (.env의 FAL_KEY 또는 KeyKeyFal.txt)")
    return None


def generate_image_file_deepinfra(prompt, filename, deep_key, save_dir):
    """
    홈페이지 공식 방식(OpenAI Client) 적용 + 여러 모델명 시도
    """
    save_path = os.path.join(save_dir, f"{filename}.png")
    
    # ⭐️ 1. 공식 클라이언트 설정 (URL 조립 실수 원천 봉쇄)
    client = openai.OpenAI(
        base_url="https://api.deepinfra.com/v1/openai",
        api_key=deep_key
    )

    # ⭐️ 2. 성공한 모델명 우선 시도 (빠른 실행을 위해 최소화)
    model_candidates = [
        "black-forest-labs/FLUX-1-schnell",  # ✅ 성공 확인된 모델 (우선)
        "blackforestlabs/FLUX-1-schnell",    # 대안
    ]

    for target_model in model_candidates:
        target_model = target_model.strip()  # 유령 공백 제거
        print(f"🎨 DeepInfra 요청 중... [{target_model}]", end=" ")

        try:
            response = client.images.generate(
                prompt=prompt,
                model=target_model,
                size="1280x720",  # 16:9 비율
                n=1
            )

            # 데이터 저장 로직 (OpenAI 방식은 응답 구조가 다름)
            if response.data:
                # DeepInfra OpenAI 호환 모드는 때때로 url을 줄 수도 있습니다. 체크:
                if hasattr(response.data[0], 'b64_json') and response.data[0].b64_json:
                    # b64_json으로 주면 디코딩
                    image_data_b64 = response.data[0].b64_json
                    with open(save_path, "wb") as f:
                        f.write(base64.b64decode(image_data_b64))
                    print(f"-> ✅ 성공! ({save_path})")
                    return True
                elif hasattr(response.data[0], 'url') and response.data[0].url:
                    # URL로 주는 경우 다운로드
                    img_url = response.data[0].url
                    img_res = requests.get(img_url, timeout=10)
                    if img_res.status_code == 200:
                        with open(save_path, "wb") as f:
                            f.write(img_res.content)
                        print(f"-> ✅ 성공! ({save_path})")
                        return True
                
            print("-> ⚠️ 응답은 왔지만 이미지 데이터가 없습니다.")
            # 다음 모델 시도
            continue

        except openai.APIError as e:
            error_str = str(e)
            if "404" in error_str or "not available" in error_str.lower():
                print(f"-> ⚠️ 모델 없음, 다음 시도...")
            else:
                print(f"-> ⚠️ API 에러: {e}, 다음 시도...")
            continue
        except Exception as e:
            print(f"-> ⚠️ 에러: {e}, 다음 시도...")
            continue
    
    print(f"-> ❌ 모든 모델 시도 실패")
    return False


def copy_midtro_video(gid, save_dir, channel_name):
    """
    미드트로 비디오를 복사하여 이미지 그룹 번호로 저장
    예: 4번 그룹이면 4_image_group.mp4로 저장
    Args:
        gid: 그룹 ID
        save_dir: 저장할 디렉토리
        channel_name: 채널명 (예: "Ch01")
    """
    source_path = f"C:\\YtFactory9\\{channel_name}\\02_Input\\Intro_Video.mp4"
    if not os.path.exists(source_path):
        print(f"  ❌ 미드트로 비디오를 찾을 수 없습니다: {source_path}")
        return False
    
    save_filename = f"{gid}_image_group.mp4"
    save_path = os.path.join(save_dir, save_filename)
    
    try:
        shutil.copy2(source_path, save_path)
        print(f"  ✅ 미드트로 비디오 복사 완료: {save_path}")
        return True
    except Exception as e:
        print(f"  ❌ 미드트로 비디오 복사 실패: {e}")
        return False


def copy_out_video(gid, save_dir, channel_name):
    """
    아웃트로 비디오를 복사하여 이미지 그룹 번호로 저장
    예: 4번 그룹이면 4_image_group.mp4로 저장
    Args:
        gid: 그룹 ID
        save_dir: 저장할 디렉토리
        channel_name: 채널명 (예: "Ch01")
    """
    source_path = f"C:\\YtFactory9\\{channel_name}\\02_Input\\Outro_Video.mp4"
    if not os.path.exists(source_path):
        print(f"  ❌ 아웃트로 비디오를 찾을 수 없습니다: {source_path}")
        return False
    
    save_filename = f"{gid}_image_group.mp4"
    save_path = os.path.join(save_dir, save_filename)
    
    try:
        shutil.copy2(source_path, save_path)
        print(f"  ✅ 아웃트로 비디오 복사 완료: {save_path}")
        return True
    except Exception as e:
        print(f"  ❌ 아웃트로 비디오 복사 실패: {e}")
        return False


def find_and_upload_fal_image(keyword, fal_key):
    """
    FAL_ROOT_IMAGE_DIR 폴더에서 keyword가 포함된 이미지 파일을 찾아 fal 클라우드에 업로드
    
    Args:
        keyword: M열(fal_RootImage)의 키워드
        fal_key: Fal API 키
    
    Returns:
        str or None: 업로드된 이미지 URL 또는 None (찾지 못한 경우)
    """
    if not keyword or not keyword.strip():
        print(f"  ⚠️ Fal 참조 이미지 키워드가 비어있습니다.")
        return None
    
    keyword = keyword.strip()
    
    # FAL_ROOT_IMAGE_DIR 폴더 존재 확인
    if not os.path.exists(FAL_ROOT_IMAGE_DIR):
        print(f"  ❌ Fal 참조 이미지 폴더를 찾을 수 없습니다: {FAL_ROOT_IMAGE_DIR}")
        return None
    
    # 이미지 파일 확장자 목록
    image_extensions = ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.PNG', '.JPG', '.JPEG', '.WEBP', '.BMP']
    
    # keyword가 포함된 이미지 파일 찾기
    found_files = []
    
    # 1순위: 정확히 일치하는 파일명 (예: "1" -> "1.png")
    for ext in image_extensions:
        exact_match = os.path.join(FAL_ROOT_IMAGE_DIR, f"{keyword}{ext}")
        if os.path.exists(exact_match):
            found_files.append(exact_match)
            break
    
    # 2순위: keyword가 포함된 파일명 (예: "1" -> "*1*.png")
    if not found_files:
        for ext in image_extensions:
            pattern = f"*{keyword}*{ext}"
            found = glob.glob(os.path.join(FAL_ROOT_IMAGE_DIR, pattern), recursive=False)
            if found:
                found_files.extend(found)
                break
    
    if not found_files:
        print(f"  ❌ Fal 참조 이미지를 찾을 수 없습니다. (키워드: '{keyword}', 경로: {FAL_ROOT_IMAGE_DIR})")
        return None
    
    # 첫 번째로 찾은 파일 사용
    image_path = found_files[0]
    print(f"  🔍 Fal 참조 이미지 발견: {os.path.basename(image_path)}")
    
    try:
        # Fal API 키를 환경변수로 설정 (fal_client가 환경변수를 읽음)
        original_env_key = os.environ.get("FAL_KEY")
        os.environ["FAL_KEY"] = fal_key
        
        # fal_client를 사용하여 이미지 업로드 (파일 경로를 직접 전달)
        upload_result = fal_client.upload_file(image_path)
        
        # 환경변수 복원
        if original_env_key:
            os.environ["FAL_KEY"] = original_env_key
        elif "FAL_KEY" in os.environ:
            del os.environ["FAL_KEY"]
        
        # upload_result가 문자열(URL)이거나 객체일 수 있음
        if isinstance(upload_result, str):
            image_url = upload_result
        elif hasattr(upload_result, 'url'):
            image_url = upload_result.url
        elif isinstance(upload_result, dict) and 'url' in upload_result:
            image_url = upload_result['url']
        else:
            print(f"  ❌ Fal 업로드 결과 형식이 예상과 다릅니다: {type(upload_result)}")
            return None
        
        print(f"  ✅ Fal 이미지 업로드 완료: {image_url[:50]}...")
        return image_url
    except Exception as e:
        print(f"  ❌ Fal 이미지 업로드 실패: {e}")
        # 환경변수 복원 (예외 발생 시에도)
        if "FAL_KEY" in os.environ and fal_key != os.environ.get("FAL_KEY"):
            if original_env_key:
                os.environ["FAL_KEY"] = original_env_key
            else:
                del os.environ["FAL_KEY"]
        return None


def generate_image_fal(prompt, image_url, filename, save_dir, fal_key):
    """
    Fal AI를 사용하여 Image-to-Image 또는 Text-to-Image 생성
    
    Args:
        prompt: H열의 프롬프트
        image_url: 참조 이미지 URL (None이면 Text-to-Image, 있으면 Image-to-Image)
        filename: 저장할 파일명 (확장자 제외)
        save_dir: 저장할 디렉토리
        fal_key: Fal API 키
    
    Returns:
        bool: 성공 여부
    """
    save_path = os.path.join(save_dir, f"{filename}.png")
    
    try:
        # Fal API 키를 환경변수로 설정 (fal_client가 환경변수를 읽음)
        original_env_key = os.environ.get("FAL_KEY")
        os.environ["FAL_KEY"] = fal_key
        
        # image_url이 있으면 Image-to-Image, 없으면 Text-to-Image
        if image_url:
            # Image-to-Image 모델 사용
            model = "fal-ai/flux/dev/image-to-image"
            print(f"  🎨 Fal 이미지 생성 중... [Image-to-Image]", end=" ")
            
            # Fal API 호출 (Image-to-Image)
            result = fal_client.run(
                model,
                arguments={
                    "prompt": prompt,
                    "image_url": image_url,
                    "strength": 0.75,  # 원본 이미지 느낌 유지 강도 (0.0~1.0)
                    "guidance_scale": 3.5,
                    "num_inference_steps": 28,
                    "seed": random.randint(1, 1000000)
                }
            )
        else:
            # Text-to-Image 모델 사용
            model = "fal-ai/flux/dev"
            print(f"  🎨 Fal 이미지 생성 중... [Text-to-Image]", end=" ")
            
            # Fal API 호출 (Text-to-Image)
            result = fal_client.run(
                model,
                arguments={
                    "prompt": prompt,
                    "guidance_scale": 3.5,
                    "num_inference_steps": 28,
                    "seed": random.randint(1, 1000000)
                }
            )
        
        # 환경변수 복원
        if original_env_key:
            os.environ["FAL_KEY"] = original_env_key
        elif "FAL_KEY" in os.environ:
            del os.environ["FAL_KEY"]
        
        # 결과에서 이미지 URL 추출 (다양한 응답 형식 처리)
        image_url_result = None
        
        if isinstance(result, dict):
            # 딕셔너리 형태일 때
            if "images" in result and result["images"]:
                img_obj = result["images"][0]
                if isinstance(img_obj, dict):
                    image_url_result = img_obj.get("url")
                elif isinstance(img_obj, str):
                    image_url_result = img_obj
            elif "image" in result:
                img_obj = result["image"]
                if isinstance(img_obj, dict):
                    image_url_result = img_obj.get("url")
                elif isinstance(img_obj, str):
                    image_url_result = img_obj
        elif hasattr(result, 'images') and result.images:
            # 객체에 images 속성이 있을 때
            img_obj = result.images[0]
            if hasattr(img_obj, 'url'):
                image_url_result = img_obj.url
            elif isinstance(img_obj, str):
                image_url_result = img_obj
        elif hasattr(result, 'image'):
            # 객체에 image 속성이 있을 때
            img_obj = result.image
            if hasattr(img_obj, 'url'):
                image_url_result = img_obj.url
            elif isinstance(img_obj, str):
                image_url_result = img_obj
        
        if not image_url_result:
            print("-> ⚠️ 응답에서 이미지 URL을 찾을 수 없습니다.")
            return False
        
        # 이미지 다운로드
        img_response = requests.get(image_url_result, timeout=10)
        if img_response.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(img_response.content)
            print(f"-> ✅ 성공! ({save_path})")
            return True
        else:
            print(f"-> ❌ 이미지 다운로드 실패 (HTTP {img_response.status_code})")
            return False
            
    except Exception as e:
        print(f"-> ❌ Fal 이미지 생성 실패: {e}")
        # 환경변수 복원 (예외 발생 시에도)
        if "FAL_KEY" in os.environ and fal_key != os.environ.get("FAL_KEY"):
            if original_env_key:
                os.environ["FAL_KEY"] = original_env_key
            else:
                del os.environ["FAL_KEY"]
        return False

# ==========================================
# 4. 단계별 일괄 처리 함수들
# ==========================================
def prepare_prompts_batch(selected_sheet, grouped_data, row_mapping, key_manager):
    """
    1단계: 프롬프트 선행 일괄 생성 (병렬 처리)
    H열이 비어있는 모든 그룹을 찾아서 병렬로 프롬프트를 생성하고, 메모리에 모아둔 후 일괄 업데이트
    
    Args:
        selected_sheet: gspread Worksheet 객체
        grouped_data: 그룹 데이터 딕셔너리
        row_mapping: 그룹 ID -> 행 번호 매핑
        key_manager: KeyManager 인스턴스
    
    Returns:
        dict: {gid: prompt_text} 형태의 딕셔너리
    """
    print(f"\n{'='*50}")
    print(f"📝 [1단계] 프롬프트 일괄 생성 시작...")
    print(f"{'='*50}")
    
    # H열이 비어있는 그룹 찾기
    groups_needing_prompts = []
    for gid in grouped_data.keys():
        row_idx = row_mapping[gid]
        try:
            h_col_value = retry_on_quota_exceeded(lambda: selected_sheet.cell(row_idx, 8).value)  # H열 = 8번째 컬럼
            if not h_col_value or len(str(h_col_value).strip()) < 10:
                groups_needing_prompts.append(gid)
        except:
            groups_needing_prompts.append(gid)
    
    if not groups_needing_prompts:
        print(f"✅ 모든 그룹에 프롬프트가 이미 존재합니다.")
        return {}
    
    print(f"📋 프롬프트가 필요한 그룹: {len(groups_needing_prompts)}개")
    
    # 프롬프트 생성 작업 정의
    def generate_single_prompt(gid):
        """단일 그룹의 프롬프트 생성"""
        try:
            style_char = grouped_data[gid]['style']
            combined_text = " ".join(grouped_data[gid]['texts'])
            
            template = load_prompt_template(style_char)
            if not template:
                print(f"  ⚠️ [Group {gid}] 템플릿({style_char}.txt) 없음")
                return (gid, None)
            
            prompt = generate_prompt_text(combined_text, template, key_manager)
            if prompt:
                return (gid, prompt)
            else:
                print(f"  ❌ [Group {gid}] 프롬프트 생성 실패")
                return (gid, None)
        except Exception as e:
            print(f"  ⚠️ [Group {gid}] 프롬프트 생성 중 오류: {str(e)[:50]}")
            return (gid, None)
    
    # 병렬 처리로 프롬프트 생성 (메모리 상에서만)
    prompt_results = {}  # {gid: prompt_text}
    max_workers = 5  # 안전한 병렬 처리
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 모든 그룹에 대해 작업 제출
        future_to_gid = {executor.submit(generate_single_prompt, gid): gid for gid in groups_needing_prompts}
        
        # 완료된 작업부터 처리
        completed = 0
        for future in as_completed(future_to_gid):
            completed += 1
            gid, prompt = future.result()
            if prompt:
                prompt_results[gid] = prompt
                print(f"  ✅ [{completed}/{len(groups_needing_prompts)}] Group {gid}: 프롬프트 생성 완료 ({len(prompt)}자)")
            else:
                print(f"  ⚠️ [{completed}/{len(groups_needing_prompts)}] Group {gid}: 프롬프트 생성 실패")
    
    # 시트에 일괄 업데이트 (10개씩 묶어서)
    if prompt_results:
        print(f"\n💾 시트에 프롬프트 일괄 업데이트 중... ({len(prompt_results)}개)")
        cell_updates = []
        for gid, prompt in prompt_results.items():
            row_idx = row_mapping[gid]
            cell_updates.append(gspread.Cell(row_idx, 8, prompt))  # H열 = 8번째 컬럼
        
        # 10개씩 묶어서 업데이트 (시트 API 제한 회피)
        batch_size = 10
        for i in range(0, len(cell_updates), batch_size):
            batch = cell_updates[i:i+batch_size]
            try:
                retry_on_quota_exceeded(lambda: selected_sheet.update_cells(batch))
                print(f"  ✅ {min(i+batch_size, len(cell_updates))}/{len(cell_updates)}개 업데이트 완료")
                time.sleep(0.5)  # 배치 간 짧은 대기
            except Exception as e:
                print(f"  ⚠️ 배치 업데이트 중 오류: {str(e)[:50]}")
        
        print(f"✅ 프롬프트 일괄 생성 완료! ({len(prompt_results)}개 생성)")
    else:
        print(f"⚠️ 생성된 프롬프트가 없습니다.")
    
    return prompt_results


def process_images_parallel(selected_sheet, grouped_data, row_mapping, sorted_groups,
                           FINAL_OUTPUT_DIR, channel_name, api_keys, deep_key, fal_key):
    """
    2단계: 이미지 병렬 생성 (속도 최적화)
    프롬프트가 준비된 상태에서 이미지를 병렬로 생성 (max_workers=5)
    
    Args:
        selected_sheet: gspread Worksheet 객체
        grouped_data: 그룹 데이터 딕셔너리
        row_mapping: 그룹 ID -> 행 번호 매핑
        sorted_groups: 정렬된 그룹 ID 리스트
        FINAL_OUTPUT_DIR: 출력 디렉토리
        channel_name: 채널명
        api_keys: Gemini API 키 리스트 (YtFactory3 방식)
        deep_key: DeepInfra API 키
        fal_key: Fal API 키
    
    Returns:
        set: 실패한 그룹 ID 집합
    """
    print(f"\n{'='*50}")
    print(f"🎨 [2단계] 이미지 생성 시작... (병렬 처리, 5 workers)")
    print(f"{'='*50}")
    
    # 이미지 생성 작업 정의
    def generate_single_image(gid):
        """단일 그룹의 이미지 생성"""
        try:
            save_filename = f"{gid}_image_group"
            full_path_png = os.path.join(FINAL_OUTPUT_DIR, f"{save_filename}.png")
            full_path_mp4 = os.path.join(FINAL_OUTPUT_DIR, f"{save_filename}.mp4")
            
            row_idx = row_mapping[gid]
            
            # 이미지 또는 비디오 파일 존재 여부 확인
            image_exists = os.path.exists(full_path_png)
            video_exists = os.path.exists(full_path_mp4)
            
            if image_exists or video_exists:
                print(f"✅ [Group {gid}] 이미 파일 존재 - 완료")
                return (gid, True, None)
            
            style_char = grouped_data[gid]['style']
            combined_text = " ".join(grouped_data[gid]['texts'])
            
            # 미드트로 체크
            if "(미드트로)" in combined_text:
                print(f"⚡ [Group {gid}] 미드트로 감지 -> 비디오 복사 시작")
                if copy_midtro_video(gid, FINAL_OUTPUT_DIR, channel_name):
                    return (gid, True, None)
                else:
                    return (gid, False, "미드트로 복사 실패")
            
            # 아웃트로 체크
            if "(아웃트로)" in combined_text:
                print(f"⚡ [Group {gid}] 아웃트로 감지 -> 비디오 복사 시작")
                if copy_out_video(gid, FINAL_OUTPUT_DIR, channel_name):
                    return (gid, True, None)
                else:
                    return (gid, False, "아웃트로 복사 실패")
            
            print(f"⚡ [Group {gid}] 이미지 생성 시작")
            
            # J열(imagetype) 확인
            image_type = "gemini"
            try:
                img_type_val = retry_on_quota_exceeded(lambda: selected_sheet.cell(row_idx, 10).value)  # J열 = 10번째 컬럼
                if img_type_val:
                    image_type = img_type_val.strip().lower()
            except:
                pass
            
            # H열에서 프롬프트 가져오기
            current_prompt = ""
            try:
                val = retry_on_quota_exceeded(lambda: selected_sheet.cell(row_idx, 8).value)  # H열 = 8번째 컬럼
                if val and len(str(val).strip()) > 10:
                    current_prompt = str(val).strip()
            except:
                pass
            
            if not current_prompt:
                print(f"  ⚠️ [Group {gid}] H열에 프롬프트가 없습니다. 스킵합니다.")
                return (gid, False, "프롬프트 없음")
            
            # Flux 모델 사용 시 프롬프트 최적화
            if image_type == "flux":
                original_prompt = current_prompt
                current_prompt = optimize_prompt_for_flux(current_prompt)
                if original_prompt != current_prompt:
                    print(f"  ✨ [Group {gid}] Flux 모델용 프롬프트 최적화 완료")
                    try:
                        retry_on_quota_exceeded(lambda: selected_sheet.update_cell(row_idx, 8, current_prompt))
                    except:
                        pass
            
            # 이미지 생성 분기 처리
            print(f"  🎨 [Group {gid}] 이미지 생성 중... (타입: {image_type}, 프롬프트 길이: {len(current_prompt)}자)")
            success = False
            error_type = 'other'
            
            if image_type == "fal":
                if not fal_key:
                    print(f"  ❌ [Group {gid}] Fal 키가 없어 이미지를 생성할 수 없습니다.")
                    return (gid, False, "Fal 키 없음")
                
                # M열(fal_RootImage) 확인
                fal_root_keyword = ""
                try:
                    fal_root_val = retry_on_quota_exceeded(lambda: selected_sheet.cell(row_idx, 13).value)
                    if fal_root_val:
                        fal_root_keyword = fal_root_val.strip()
                except:
                    pass
                
                image_url = None
                if fal_root_keyword:
                    image_url = find_and_upload_fal_image(fal_root_keyword, fal_key)
                    if not image_url:
                        print(f"  ⚠️ [Group {gid}] Fal 참조 이미지 업로드 실패. Text-to-Image로 진행합니다.")
                
                success = generate_image_fal(current_prompt, image_url, save_filename, FINAL_OUTPUT_DIR, fal_key)
                
            elif image_type == "flux":
                if not deep_key:
                    print(f"  ❌ [Group {gid}] DeepInfra 키가 없어 FLUX 이미지를 생성할 수 없습니다.")
                    return (gid, False, "DeepInfra 키 없음")
                success = generate_image_file_deepinfra(current_prompt, save_filename, deep_key, FINAL_OUTPUT_DIR)
                
            else:
                # 기본값 및 'gemini'일 때 (YtFactory3 방식)
                success = generate_image_file(current_prompt, save_filename, api_keys, FINAL_OUTPUT_DIR)
                error_type = 'other' if not success else 'success'
            
            if not success:
                # Responsible AI 위반 시 폴백 시도
                if error_type == 'responsible_ai' and (deep_key or fal_key):
                    print(f"  🔄 [Group {gid}] Responsible AI 위반 감지 -> 폴백 시도")
                    fallback_success = False
                    
                    if deep_key:
                        print(f"  🎨 [Group {gid}] DeepInfra로 폴백 시도 중...")
                        fallback_success = generate_image_file_deepinfra(current_prompt, save_filename, deep_key, FINAL_OUTPUT_DIR)
                    
                    if not fallback_success and fal_key:
                        print(f"  🎨 [Group {gid}] Fal로 폴백 시도 중...")
                        image_url = None
                        try:
                            fal_root_val = retry_on_quota_exceeded(lambda: selected_sheet.cell(row_idx, 13).value)
                            if fal_root_val:
                                fal_root_keyword = fal_root_val.strip()
                                image_url = find_and_upload_fal_image(fal_root_keyword, fal_key)
                        except:
                            pass
                        fallback_success = generate_image_fal(current_prompt, image_url, save_filename, FINAL_OUTPUT_DIR, fal_key)
                    
                    if fallback_success:
                        print(f"  ✅ [Group {gid}] 폴백 성공!")
                        success = True
            
            if success:
                return (gid, True, None)
            else:
                return (gid, False, f"이미지 생성 실패 ({error_type})")
                
        except Exception as e:
            print(f"  ⚠️ [Group {gid}] 이미지 생성 중 예외: {str(e)[:50]}")
            return (gid, False, f"예외: {str(e)[:50]}")
    
    # 병렬 처리로 이미지 생성
    failed_groups = set()
    max_workers = 5  # 5개 동시 실행 (32개 키 활용)
    
    # 이미지가 필요한 그룹만 필터링
    groups_needing_images = []
    for gid in sorted_groups:
        save_filename = f"{gid}_image_group"
        full_path_png = os.path.join(FINAL_OUTPUT_DIR, f"{save_filename}.png")
        full_path_mp4 = os.path.join(FINAL_OUTPUT_DIR, f"{save_filename}.mp4")
        
        if not os.path.exists(full_path_png) and not os.path.exists(full_path_mp4):
            groups_needing_images.append(gid)
    
    if not groups_needing_images:
        print(f"✅ 모든 그룹에 이미지가 이미 존재합니다.")
        return failed_groups
    
    print(f"📋 이미지가 필요한 그룹: {len(groups_needing_images)}개")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 모든 그룹에 대해 작업 제출
        future_to_gid = {executor.submit(generate_single_image, gid): gid for gid in groups_needing_images}
        
        # 완료된 작업부터 처리
        completed = 0
        for future in as_completed(future_to_gid):
            completed += 1
            gid, success, error_msg = future.result()
            if success:
                print(f"  ✅ [{completed}/{len(groups_needing_images)}] Group {gid}: 이미지 생성 완료")
            else:
                print(f"  ❌ [{completed}/{len(groups_needing_images)}] Group {gid}: {error_msg}")
                failed_groups.add(gid)
    
    return failed_groups


# ==========================================
# 5. 메인 실행 (시트 선택 로직 유지)
# ==========================================
def main():
    print(f"🚀 ImageMaker v9.4 (Speed Optimized)")
    
    # === [자동 선택 로직] - 비활성화됨 ===
    # auto_sheet_file = AUTO_SHEET_FILE
    selected_sheet_name = None
    # if os.path.exists(auto_sheet_file):
    #     try:
    #         with open(auto_sheet_file, 'r', encoding='utf-8') as f:
    #             selected_sheet_name = f.read().strip()
    #             print(f"🤖 [Auto] 시트 자동 선택됨: {selected_sheet_name}")
    #     except: pass
    # ========================
    
    api_keys = get_gemini_keys()
    if not api_keys:
        print("❌ Gemini 키 없음")
        return
    
    # KeyManager 인스턴스 생성 (키 상태를 스마트하게 관리)
    key_manager = KeyManager(api_keys)
    key_manager.print_status()  # 초기 상태 출력

    # DeepInfra 키 (flux 이미지를 위해, 없으면 flux 타입은 스킵)
    deep_key = get_deepinfra_key()
    
    # Fal 키 (fal 이미지를 위해, 없으면 fal 타입은 스킵)
    fal_key = get_fal_key()

    # 1. 구글 시트 접속
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        doc = load_spreadsheet(client)
    except Exception as e:
        print(f"❌ 시트 접속 실패: {e}"); return

    # 2. 'go'가 들어간 시트 찾기 & 사용자 선택
    all_worksheets = doc.worksheets()
    go_sheets = [ws for ws in all_worksheets if "go" in ws.title.lower()]

    if not go_sheets:
        print("❌ 'go'가 포함된 시트(예: 15go)를 찾을 수 없습니다!")
        return

    print("\n" + "="*40)
    print(" 🎨 [ImageMaker] 작업할 시트를 선택하세요")
    print("="*40)
    
    for idx, ws in enumerate(go_sheets):
        print(f" [{idx+1}] {ws.title}")
    
    selected_sheet = None
    while selected_sheet is None:
        # [자동 매칭] - 비활성화됨 --------------------------------
        # if selected_sheet_name:
        #     for ws in go_sheets:
        #         if ws.title == selected_sheet_name:
        #             selected_sheet = ws
        #             break
        #     if selected_sheet: break
        # ---------------------------------------------
        
        try:
            choice = input("\n번호 입력 >> ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(go_sheets):
                selected_sheet = go_sheets[idx]
            else:
                print("⚠️ 올바른 번호를 입력하세요.")
        except:
            print("⚠️ 숫자를 입력하세요.")

    print(f"✅ 선택된 시트: '{selected_sheet.title}'")

    # 3. 시트 이름에서 채널명 추출 및 폴더 생성
    sheet_title = selected_sheet.title
    channel_match = re.search(r'Ch\d+', sheet_title)
    if not channel_match:
        print(f"❌ 시트 이름에서 채널명을 추출할 수 없습니다: {sheet_title}")
        return
    channel_name = channel_match.group(0)  # 예: "Ch01"
    
    # 출력 경로: C:\YtFactory9\{channel_name}\03_Output\{sheet_title}
    FINAL_OUTPUT_DIR = f"C:\\YtFactory9\\{channel_name}\\03_Output\\{sheet_title}"
    if not os.path.exists(FINAL_OUTPUT_DIR): 
        os.makedirs(FINAL_OUTPUT_DIR)
    print(f"📂 타겟 폴더: {FINAL_OUTPUT_DIR}")

    # 4. 데이터 로드 (YtFactory3 방식: 직접 시도)
    all_values = selected_sheet.get_all_values()
    data_rows = all_values[1:] # 헤더 제외

    # 5. 그룹화 (먼저 그룹을 파악)
    grouped_data = {}
    row_mapping = {}
    # 각 그룹의 첫 번째 행 정보만 저장 (promptABC, imagetype 등)
    group_first_row_info = {}  # {gid: {'row_idx': i+2, 'promptABC': row[5], 'imagetype': row[9] if len(row)>9 else ''}}

    for i, row in enumerate(data_rows):
        if len(row) < 6: continue
        gid = row[2].strip()
        text = row[1].strip()
        
        if not gid: continue

        if gid not in grouped_data:
            # 그룹의 첫 번째 행일 때만 F열(promptABC)과 J열(imagetype) 읽기
            style = row[5].strip() if len(row) > 5 else ""  # F열: promptABC (돈경1, 돈경2, 돈경3 등) - 첫 번째 행만
            imagetype = row[9].strip().lower() if len(row) > 9 and row[9].strip() else "gemini"  # J열: imagetype - 첫 번째 행만
            
            grouped_data[gid] = {'texts': [], 'style': style}
            row_mapping[gid] = i + 2
            # 첫 번째 행의 정보만 저장
            group_first_row_info[gid] = {
                'row_idx': i + 2,
                'promptABC': style,
                'imagetype': imagetype
            }
        else:
            # 그룹의 나머지 행들은 F열 무시 (비워있어야 함)
            pass
        
        grouped_data[gid]['texts'].append(text)

    # (비상조치) 스타일 할당 - 그룹의 첫 번째 행(대표 행)만 체크하고 비어있으면 채우기
    groups_needing_style = []
    for gid, data in grouped_data.items():
        row_idx = row_mapping[gid]
        current_style = data['style'].strip()
        if not current_style:
            groups_needing_style.append(gid)
    
    if groups_needing_style:
        print(f"📊 {len(groups_needing_style)}개 그룹의 스타일(A/B/C)이 비어있어 자동 할당합니다 (30:40:30)")
        total_empty = len(groups_needing_style)
        count_a = int(total_empty * 0.3)
        count_b = int(total_empty * 0.4)
        count_c = total_empty - count_a - count_b
        
        styles = ['a']*count_a + ['b']*count_b + ['c']*count_c
        random.shuffle(styles)
        
        cell_updates = []
        for i, gid in enumerate(groups_needing_style):
            row_idx = row_mapping[gid]
            cell_updates.append(gspread.Cell(row_idx, 6, styles[i]))
        
        if cell_updates:
            # YtFactory3 방식: retry_on_quota_exceeded 사용하지 않고 직접 시도
            selected_sheet.update_cells(cell_updates)
            print(f"✅ {len(cell_updates)}개 그룹에 스타일 할당 완료. 다시 로드합니다.")
            # 다시 로드해서 업데이트된 스타일 반영
            data_rows = selected_sheet.get_all_values()[1:]
            # 그룹화도 다시 해서 스타일 업데이트
            grouped_data = {}
            row_mapping = {}
            group_first_row_info = {}
            for i, row in enumerate(data_rows):
                if len(row) < 6: continue
                gid = row[2].strip()
                text = row[1].strip()
                
                if not gid: continue

                if gid not in grouped_data:
                    # 그룹의 첫 번째 행일 때만 F열(promptABC)과 J열(imagetype) 읽기
                    style = row[5].strip() if len(row) > 5 else ""
                    imagetype = row[9].strip().lower() if len(row) > 9 and row[9].strip() else "gemini"
                    if not style: style = 'a'
                    
                    grouped_data[gid] = {'texts': [], 'style': style}
                    row_mapping[gid] = i + 2
                    # 첫 번째 행의 정보만 저장
                    group_first_row_info[gid] = {
                        'row_idx': i + 2,
                        'promptABC': style,
                        'imagetype': imagetype
                    }
                else:
                    # 그룹의 나머지 행들은 F열 무시 (비워있어야 함)
                    pass
                grouped_data[gid]['texts'].append(text)

    # F열과 J열 정리: 그룹의 첫 번째 행만 남기고 나머지는 비우기 (선택적, 환경변수로 제어)
    # YTF_CLEANUP_COLUMNS 환경변수가 설정되어 있거나, 한 번만 실행하도록 제한
    should_cleanup = os.environ.get("YTF_CLEANUP_COLUMNS", "").lower() in ["1", "true", "yes"]
    
    if should_cleanup:
        print(f"\n🧹 F열(promptABC)과 J열(imagetype) 정리 중...")
        cells_to_clear = []
        
        for i, row in enumerate(data_rows):
            if len(row) < 6: continue
            gid = row[2].strip()
            if not gid: continue
            
            # 이 행이 그룹의 첫 번째 행인지 확인
            if gid in row_mapping and row_mapping[gid] == i + 2:
                # 첫 번째 행이면 유지 (아무것도 안 함)
                continue
            else:
                # 나머지 행이면 F열(6번째 컬럼)과 J열(10번째 컬럼) 비우기
                row_num = i + 2  # 실제 시트 행 번호 (헤더 제외)
                
                # F열 확인 (비어있지 않으면 비우기)
                if len(row) > 5 and row[5].strip():
                    cells_to_clear.append(gspread.Cell(row_num, 6, ""))  # F열 = 6번째 컬럼
                
                # J열 확인 (비어있지 않으면 비우기)
                if len(row) > 9 and row[9].strip():
                    cells_to_clear.append(gspread.Cell(row_num, 10, ""))  # J열 = 10번째 컬럼
        
        # 일괄 업데이트 (100개씩 묶어서 - API 호출 최소화)
        if cells_to_clear:
            print(f"  📝 {len(cells_to_clear)}개 셀 정리 중...")
            batch_size = 100  # 배치 크기 증가 (10 -> 100)
            for batch_start in range(0, len(cells_to_clear), batch_size):
                batch = cells_to_clear[batch_start:batch_start + batch_size]
                try:
                    # retry_on_quota_exceeded 사용하지 않고 직접 시도 (빠른 실패)
                    selected_sheet.update_cells(batch)
                    print(f"  ✅ {min(batch_start + batch_size, len(cells_to_clear))}/{len(cells_to_clear)}개 셀 정리 완료")
                    time.sleep(0.2)  # 배치 간 짧은 대기 (0.5 -> 0.2)
                except Exception as e:
                    # 에러 발생 시 스킵하고 계속 진행 (정리 실패해도 이미지 생성은 계속)
                    print(f"  ⚠️ 셀 정리 중 오류 (계속 진행): {str(e)[:50]}")
                    break  # 에러 발생 시 정리 중단하고 계속 진행
            print(f"✅ F열과 J열 정리 완료!")
        else:
            print(f"✅ F열과 J열이 이미 정리되어 있습니다.")
    else:
        # 정리 기능 비활성화 (기본값: 빠른 실행)
        print(f"💡 F열/J열 정리 기능은 비활성화되어 있습니다. (환경변수 YTF_CLEANUP_COLUMNS=1로 활성화 가능)")
    
    sorted_groups = sorted(grouped_data.keys(), key=lambda x: int(x) if x.isdigit() else 9999)
    print(f"🎯 총 {len(sorted_groups)}개 그룹 처리 시작")

    # ==========================================
    # 6. 작업 루프 (YtFactory3 방식: 순차 처리)
    # ==========================================
    for gid in sorted_groups:
        save_filename = f"{gid}_image_group"
        full_path_png = os.path.join(FINAL_OUTPUT_DIR, f"{save_filename}.png")
        full_path_mp4 = os.path.join(FINAL_OUTPUT_DIR, f"{save_filename}.mp4")
        
        # 이미지 또는 비디오 파일 존재 여부 확인
        if os.path.exists(full_path_png) or os.path.exists(full_path_mp4):
            continue
        
        print(f"\n⚡ [Group {gid}] 파일 없음 -> AI 이미지 생성 시작")
        
        # 그룹의 대표 행 (첫 번째 행)
        row_idx = row_mapping[gid]
        
        # 그룹의 첫 번째 행 정보만 사용 (F열과 J열은 첫 번째 행에만 있음)
        first_row_info = group_first_row_info.get(gid)
        if first_row_info:
            style_char = first_row_info['promptABC'].strip()
            image_type = first_row_info['imagetype'].strip().lower() if first_row_info['imagetype'] else "gemini"
        else:
            # 정보가 없으면 기본값 사용
            style_char = grouped_data[gid]['style']
            image_type = "gemini"
        
        # 미드트로/아웃트로 체크
        combined_text = " ".join(grouped_data[gid]['texts'])
        if "(미드트로)" in combined_text:
            print(f"⚡ [Group {gid}] 미드트로 감지 -> 비디오 복사 시작")
            if copy_midtro_video(gid, FINAL_OUTPUT_DIR, channel_name):
                continue
            else:
                print(f"  ❌ [Group {gid}] 미드트로 복사 실패")
                continue
        
        if "(아웃트로)" in combined_text:
            print(f"⚡ [Group {gid}] 아웃트로 감지 -> 비디오 복사 시작")
            if copy_out_video(gid, FINAL_OUTPUT_DIR, channel_name):
                continue
            else:
                print(f"  ❌ [Group {gid}] 아웃트로 복사 실패")
                continue
        
        # 프롬프트 체크 및 생성 (YtFactory3 방식)
        current_prompt = ""
        try:
            # YtFactory3 방식: retry_on_quota_exceeded 사용하지 않고 직접 시도
            val = selected_sheet.cell(row_idx, 8).value
            if val and len(str(val).strip()) > 10:
                current_prompt = str(val).strip()
        except:
            pass
        
        if not current_prompt:
            if not style_char:
                print(f"  ❌ [Group {gid}] F열(promptABC)이 비어있습니다.")
                continue
            
            template = load_prompt_template(style_char)
            if not template:
                print(f"  ❌ [Group {gid}] 템플릿 파일 없음 (키워드: {style_char})")
                continue
            
            combined_text = " ".join(grouped_data[gid]['texts'])
            current_prompt = generate_prompt_text(combined_text, template, api_keys)
            
            if current_prompt:
                try:
                    # YtFactory3 방식: retry_on_quota_exceeded 사용하지 않고 직접 시도
                    selected_sheet.update_cell(row_idx, 8, current_prompt)
                except:
                    pass
            else:
                print(f"  ❌ [Group {gid}] 프롬프트 생성 실패")
                continue
        
        # 이미지 타입 확인 (J열에서 다시 한 번 확인 - 시트에서 직접 읽기)
        if not image_type or image_type == "gemini":
            try:
                # YtFactory3 방식: retry_on_quota_exceeded 사용하지 않고 직접 시도
                img_type_val = selected_sheet.cell(row_idx, 10).value
                if img_type_val:
                    image_type = img_type_val.strip().lower()
            except:
                pass
        
        if not image_type:
            image_type = "gemini"
        
        print(f"  📋 [Group {gid}] promptABC: {style_char}, imagetype: {image_type}")
        
        # Flux 모델 사용 시 프롬프트 최적화
        if image_type == "flux":
            original_prompt = current_prompt
            current_prompt = optimize_prompt_for_flux(current_prompt)
            if original_prompt != current_prompt:
                try:
                    # YtFactory3 방식: retry_on_quota_exceeded 사용하지 않고 직접 시도
                    selected_sheet.update_cell(row_idx, 8, current_prompt)
                except:
                    pass
        
        # 이미지 생성
        if image_type == "fal":
            if not fal_key:
                print(f"  ❌ [Group {gid}] Fal 키가 없어 이미지를 생성할 수 없습니다.")
                continue
            
            fal_root_keyword = ""
            try:
                # YtFactory3 방식: retry_on_quota_exceeded 사용하지 않고 직접 시도
                fal_root_val = selected_sheet.cell(row_idx, 13).value
                if fal_root_val:
                    fal_root_keyword = fal_root_val.strip()
            except:
                pass
            
            image_url = None
            if fal_root_keyword:
                image_url = find_and_upload_fal_image(fal_root_keyword, fal_key)
                if not image_url:
                    print(f"  ⚠️ [Group {gid}] Fal 참조 이미지 업로드 실패. Text-to-Image로 진행합니다.")
            
            generate_image_fal(current_prompt, image_url, save_filename, FINAL_OUTPUT_DIR, fal_key)
            
        elif image_type == "flux":
            if not deep_key:
                print(f"  ❌ [Group {gid}] DeepInfra 키가 없어 FLUX 이미지를 생성할 수 없습니다.")
                continue
            generate_image_file_deepinfra(current_prompt, save_filename, deep_key, FINAL_OUTPUT_DIR)
            
        else:
            # 기본값 및 'gemini'일 때 (YtFactory3 방식)
            generate_image_file(current_prompt, save_filename, api_keys, FINAL_OUTPUT_DIR)
    
    print(f"\n🎉 모든 그룹 처리 완료!")

if __name__ == "__main__": main()