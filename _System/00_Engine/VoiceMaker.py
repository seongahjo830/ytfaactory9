import os
import glob
import re
import time
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import random
import subprocess
import edge_tts
import asyncio
import html

# 오디오 후처리용 (ElevenLabs 속도/피치 조절)
try:
    from pydub import AudioSegment
    from pydub.effects import speedup, normalize
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("⚠️ pydub가 설치되지 않았습니다. 속도/피치 조절을 위해 'pip install pydub' 실행이 필요합니다.")
try:
    import azure.cognitiveservices.speech as speechsdk
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    print("⚠️ Azure Speech SDK가 설치되지 않았습니다. 'pip install azure-cognitiveservices-speech' 실행이 필요합니다.")

# ==========================================
# 1. 설정 및 경로 정의 (자동 설정)
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# Voice 파일 경로
VOICES_BASE_DIR = r"C:\YtFactory9\_System\04_Co_Asset\Voice"
VOICES_EDGE_FILE = os.path.join(VOICES_BASE_DIR, "voices_edge.txt")
VOICES_AZURE_FILE = os.path.join(VOICES_BASE_DIR, "voices_azure.txt")
VOICES_ELEVENLABS_FILE = os.path.join(VOICES_BASE_DIR, "voices_elevenlabs.txt")

# 기존 방식 호환성을 위한 폴더 (04_Asset/Voice에서 목소리 ID 추출용)
ASSET_VOICE_DIR = r"C:\YtFactory9\_System\04_Co_Asset\Voice"

JSON_KEY_FILE = r"C:\YtFactory9\_System\02_Key\service_account.json"
SHEET_URL_FILE = r"C:\YtFactory9\_System\00_Engine\YtFactory9_URL.txt"
FFPROBE_CMD = r"C:\YtFactory9\ffprobe.exe"

# 워크플로우별 고유 auto_sheet 파일 (환경변수 우선)
ENV_AUTO_SHEET = os.environ.get("YTF_AUTO_SHEET_FILE")
if ENV_AUTO_SHEET and ENV_AUTO_SHEET.strip():
    AUTO_SHEET_FILE = ENV_AUTO_SHEET.strip()
else:
    AUTO_SHEET_FILE = os.path.join(CURRENT_DIR, "_auto_sheet.txt")

# ==========================================
# 2. Edge TTS 목소리 매핑 (voices_edge.txt 로드)
# ==========================================
_edge_voice_map = {}  # {호출이름: {"id": "voice_id", "rate": "속도값", "pitch": "피치값"}}

# ==========================================
# 2-1. Azure TTS 목소리 매핑 (voices_azure.txt 로드)
# ==========================================
_azure_voice_map = {}  # {호출이름: {"id": "voice_id", "rate": "속도값", "pitch": "피치값"}}

# ==========================================
# 2-2. ElevenLabs TTS 목소리 매핑 (voices_elevenlabs.txt 로드)
# ==========================================
_elevenlabs_voice_map = {}  # {호출이름: {"id": "voice_id", "model": "모델명", "rate": "속도값", "pitch": "피치값"}}

def load_edge_voices_map():
    """voices_edge.txt 파일을 읽어서 호출이름 -> ID 매핑 생성
    
    파일 형식: 호출이름,스타일,성별,ID,속도,피치,설명
    예: 선희_기본,General,여성,ko-KR-SunHiNeural,0,0,가장 깔끔한 아나운서 기본 톤
    """
    global _edge_voice_map
    if _edge_voice_map:
        return _edge_voice_map
    
    _edge_voice_map = {}
    
    if not os.path.exists(VOICES_EDGE_FILE):
        print(f"⚠️ voices_edge.txt 파일을 찾을 수 없습니다: {VOICES_EDGE_FILE}")
        return _edge_voice_map
    
    try:
        with open(VOICES_EDGE_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        header_found = False
        for line in lines:
            line = line.strip()
            
            # 빈 줄 스킵
            if not line:
                continue
            
            # 주석 스킵
            if line.startswith('#'):
                continue
            
            # 헤더 줄 체크 (호출이름으로 시작하면 헤더)
            if '호출이름' in line or 'call_name' in line.lower():
                header_found = True
                continue
            
            # 헤더 이후에만 데이터 파싱
            if not header_found and not line.startswith('선희') and not line.startswith('인준') and not line.startswith('미국'):
                continue
            
            # CSV 파싱: 호출이름,스타일,성별,ID,속도,피치,설명
            # 설명 컬럼에 쉼표가 포함될 수 있으므로 maxsplit 사용
            parts = [p.strip() for p in line.split(',', 6)]  # 최대 7개 필드로 분리
            
            # 최소 4개 필드 필요 (호출이름,스타일,성별,ID)
            if len(parts) >= 4:
                call_name = parts[0]  # 호출이름 (예: '선희_기본')
                style = parts[1] if len(parts) > 1 else "General"  # 스타일 (예: 'General')
                gender = parts[2]  # 성별 (예: '여성')
                voice_id = parts[3]   # ID (예: 'ko-KR-SunHiNeural')
                rate = parts[4] if len(parts) > 4 else "0"      # 속도 (예: "+20%", "-10%", "0")
                pitch = parts[5] if len(parts) > 5 else "0"     # 피치 (예: "+5Hz", "-2Hz", "0")
                
                # 빈 값 체크
                if call_name and voice_id:
                    _edge_voice_map[call_name] = {
                        "id": voice_id,
                        "style": style,
                        "gender": gender,
                        "rate": rate,
                        "pitch": pitch
                    }
                    # 매핑 정보 로드 (출력 제거)
        
        if _edge_voice_map:
            print(f"✅ Edge TTS 목소리 매핑 로드 완료: {len(_edge_voice_map)}개")
        else:
            print(f"⚠️ voices_edge.txt에서 목소리를 찾지 못했습니다.")
    except Exception as e:
        print(f"❌ voices_edge.txt 파일 읽기 실패: {e}")
        import traceback
        traceback.print_exc()
    
    return _edge_voice_map

def load_azure_voices_map():
    """voices_azure.txt 파일을 읽어서 호출이름 -> ID 매핑 생성
    
    파일 형식: 호출이름,스타일,성별,ID,속도,피치,설명
    예: 회장_쇼츠,General,남성,ko-KR-BongJinNeural,+15%,-5Hz,[쇼츠용] 회장님 목소리 빠르게
    """
    global _azure_voice_map
    if _azure_voice_map:
        return _azure_voice_map
    
    _azure_voice_map = {}
    
    if not os.path.exists(VOICES_AZURE_FILE):
        print(f"⚠️ voices_azure.txt 파일을 찾을 수 없습니다: {VOICES_AZURE_FILE}")
        return _azure_voice_map
    
    try:
        with open(VOICES_AZURE_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        header_found = False
        for line in lines:
            line = line.strip()
            
            # 빈 줄 스킵
            if not line:
                continue
            
            # 주석 스킵
            if line.startswith('#'):
                continue
            
            # 헤더 줄 체크 (호출이름으로 시작하면 헤더)
            if '호출이름' in line or 'call_name' in line.lower():
                header_found = True
                continue
            
            # 헤더 이후에만 데이터 파싱 (다양한 호출이름 시작 패턴 허용)
            if not header_found and not any(line.startswith(prefix) for prefix in ['선희', '인준', '지민', '연우', '서현', '국민', '철수', '봉진', '회장', '이장', '도사', '다정', '음흉', '옥분', '말자']):
                continue
            
            # CSV 파싱: 호출이름,스타일,성별,ID,속도,피치,설명
            # 설명 컬럼에 쉼표가 포함될 수 있으므로 maxsplit 사용
            parts = [p.strip() for p in line.split(',', 6)]  # 최대 7개 필드로 분리
            
            # 최소 4개 필드 필요 (호출이름,스타일,성별,ID)
            if len(parts) >= 4:
                call_name = parts[0]  # 호출이름 (예: '회장_쇼츠')
                style = parts[1] if len(parts) > 1 else "General"  # 스타일 (예: 'General', 'News', 'Sad')
                gender = parts[2]  # 성별 (예: '남성')
                voice_id = parts[3]   # ID (예: 'ko-KR-BongJinNeural')
                rate = parts[4] if len(parts) > 4 else "0"      # 속도 (예: "+15%", "-10%", "0")
                pitch = parts[5] if len(parts) > 5 else "0"     # 피치 (예: "-5Hz", "+2Hz", "0")
                
                # 빈 값 체크
                if call_name and voice_id:
                    _azure_voice_map[call_name] = {
                        "id": voice_id,
                        "style": style,
                        "gender": gender,
                        "rate": rate,
                        "pitch": pitch
                    }
                    # 매핑 정보 로드 (출력 제거)
        
        if _azure_voice_map:
            print(f"✅ Azure TTS 목소리 매핑 로드 완료: {len(_azure_voice_map)}개")
        else:
            print(f"⚠️ voices_azure.txt에서 목소리를 찾지 못했습니다.")
    except Exception as e:
        print(f"❌ voices_azure.txt 파일 읽기 실패: {e}")
        import traceback
        traceback.print_exc()
    
    return _azure_voice_map

def get_azure_voice_info(voice_input):
    """ Azure TTS 목소리 정보 가져오기 (voices_azure.txt 사용)
    
    Args:
        voice_input: I열에 입력된 호출이름 (예: '회장_쇼츠', '선희_기본')
    
    Returns:
        dict: {"id": "voice_id", "rate": "속도값", "pitch": "피치값"}
              또는 voice_input이 전체 ID 형식이면 {"id": "voice_id", "rate": None, "pitch": None}
    
    Logic:
        - L열에 'azure'가 적혀있으면 이 함수가 호출됨
        - I열의 '회장_쇼츠' 같은 값을 voices_azure.txt에서 찾아서 ID, 속도, 피치 반환
    """
    # voices_azure.txt 매핑 로드
    voice_map = load_azure_voices_map()
    
    if not voice_input or not voice_input.strip():
        # 기본 목소리: 인준_기본
        default_info = voice_map.get("인준_기본")
        if default_info:
            print(f"   ℹ️ voice가 비어있어 기본 목소리 사용: {default_info['id']}")
            return default_info
        else:
            return {"id": "ko-KR-InJoonNeural", "rate": None, "pitch": None}
    
    voice_input_clean = voice_input.strip()
    
    # voices_azure.txt에서 호출이름으로 찾기 (정확한 매칭)
    if voice_input_clean in voice_map:
        found_info = voice_map[voice_input_clean]
        rate_str = f", rate={found_info['rate']}" if found_info.get('rate') and found_info['rate'] != "0" else ""
        pitch_str = f", pitch={found_info['pitch']}" if found_info.get('pitch') and found_info['pitch'] != "0" else ""
        print(f"   ✅ '{voice_input_clean}' -> '{found_info['id']}'{rate_str}{pitch_str} (voices_azure.txt에서 찾음)")
        return found_info
    
    # 매핑에 없으면, 이미 전체 목소리 이름 형식인지 확인 (예: "ko-KR-InJoonNeural")
    if "ko-" in voice_input_clean or "-Neural" in voice_input_clean or "en-" in voice_input_clean:
        # 이미 전체 이름 형식으로 입력된 경우 그대로 사용 (속도/피치 없음)
        print(f"   ℹ️ 전체 Voice ID 형식으로 인식: {voice_input_clean}")
        return {"id": voice_input_clean, "rate": None, "pitch": None}
    
    # 그 외의 경우 기본값 반환
    default_info = voice_map.get("인준_기본")
    if default_info:
        default_id = default_info['id']
    else:
        default_id = "ko-KR-InJoonNeural"
    
    print(f"   ⚠️ '{voice_input_clean}' 목소리를 voices_azure.txt에서 찾지 못해 기본 목소리({default_id})로 진행합니다.")
    if voice_map:
        print(f"   💡 사용 가능한 목소리: {', '.join(sorted(voice_map.keys())[:10])}...")
    
    return {"id": default_id, "rate": None, "pitch": None}

def load_elevenlabs_voices_map():
    """voices_elevenlabs.txt 파일을 읽어서 호출이름 -> ID 매핑 생성
    
    파일 형식: 호출이름,성별,ID,모델,속도,피치,특징
    예: 일레븐_아기,여성,zrHiDhphv9ZnVXBq795h,eleven_multilingual_v2,0,0,이름:Mimi / 애니메이션 톤 (기본)
    """
    global _elevenlabs_voice_map
    if _elevenlabs_voice_map:
        return _elevenlabs_voice_map
    
    _elevenlabs_voice_map = {}
    
    if not os.path.exists(VOICES_ELEVENLABS_FILE):
        print(f"⚠️ voices_elevenlabs.txt 파일을 찾을 수 없습니다: {VOICES_ELEVENLABS_FILE}")
        return _elevenlabs_voice_map
    
    try:
        with open(VOICES_ELEVENLABS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        header_found = False
        for line in lines:
            line = line.strip()
            
            # 빈 줄 스킵
            if not line:
                continue
            
            # 주석/구분선 스킵
            if line.startswith('#') or line.startswith('=') or line.startswith('['):
                continue
            
            # 헤더 줄 체크
            if '호출이름' in line or 'call_name' in line.lower():
                header_found = True
                continue
            
            # 헤더 이후에만 데이터 파싱
            if not header_found and not line.startswith('일레븐_'):
                continue
            
            # CSV 파싱: 호출이름,스타일,성별,ID,속도,피치,설명
            # 설명 컬럼에 쉼표가 포함될 수 있으므로 maxsplit 사용
            parts = [p.strip() for p in line.split(',', 6)]  # 최대 7개 필드로 분리
            
            # 최소 4개 필드 필요 (호출이름,스타일,성별,ID)
            if len(parts) >= 4:
                call_name = parts[0]  # 호출이름 (예: '레이첼_영어')
                style = parts[1] if len(parts) > 1 else "General"  # 스타일 (예: 'General')
                gender = parts[2]  # 성별 (예: '여성')
                voice_id = parts[3]   # ID (예: '21m00Tcm4TlvDq8ikWAM')
                rate = parts[4] if len(parts) > 4 else "0"      # 속도 (예: "+10%", "-15%", "0")
                pitch = parts[5] if len(parts) > 5 else "0"     # 피치 (예: "+5Hz", "-5Hz", "0")
                # 모델 컬럼은 없으므로 기본값 사용
                model = "eleven_multilingual_v2"
                
                # 빈 값 체크
                if call_name and voice_id:
                    _elevenlabs_voice_map[call_name] = {
                        "id": voice_id,
                        "style": style,
                        "gender": gender,
                        "model": model,  # 기본값 고정
                        "rate": rate,
                        "pitch": pitch
                    }
                    # 매핑 정보 로드 (출력 제거)
        
        if _elevenlabs_voice_map:
            print(f"✅ ElevenLabs TTS 목소리 매핑 로드 완료: {len(_elevenlabs_voice_map)}개")
        else:
            print(f"⚠️ voices_elevenlabs.txt에서 목소리를 찾지 못했습니다.")
    except Exception as e:
        print(f"❌ voices_elevenlabs.txt 파일 읽기 실패: {e}")
        import traceback
        traceback.print_exc()
    
    return _elevenlabs_voice_map

def get_elevenlabs_voice_info(voice_input):
    """ ElevenLabs TTS 목소리 정보 가져오기 (voices_elevenlabs.txt 사용)
    
    Args:
        voice_input: I열에 입력된 호출이름 (예: '일레븐_아기', '일레븐_여자_쇼츠')
    
    Returns:
        dict: {"id": "voice_id", "model": "모델명", "rate": "속도값", "pitch": "피치값"}
    """
    # voices_elevenlabs.txt 매핑 로드
    voice_map = load_elevenlabs_voices_map()
    
    if not voice_input or not voice_input.strip():
        # 기본 목소리: 일레븐_여자
        default_info = voice_map.get("일레븐_여자")
        if default_info:
            print(f"   ℹ️ voice가 비어있어 기본 목소리 사용: {default_info['id']}")
            return default_info
        else:
            return {"id": None, "model": "eleven_multilingual_v2", "rate": None, "pitch": None}
    
    voice_input_clean = voice_input.strip()
    
    # voices_elevenlabs.txt에서 호출이름으로 찾기 (정확한 매칭)
    if voice_input_clean in voice_map:
        found_info = voice_map[voice_input_clean]
        rate_str = f", rate={found_info['rate']}" if found_info.get('rate') and found_info['rate'] != "0" else ""
        pitch_str = f", pitch={found_info['pitch']}" if found_info.get('pitch') and found_info['pitch'] != "0" else ""
        print(f"   ✅ '{voice_input_clean}' -> '{found_info['id']}'{rate_str}{pitch_str} (voices_elevenlabs.txt에서 찾음)")
        return found_info
    
    # 매핑에 없으면 기본값 반환
    default_info = voice_map.get("일레븐_여자")
    if default_info:
        default_id = default_info['id']
    else:
        default_id = None
    
    print(f"   ⚠️ '{voice_input_clean}' 목소리를 voices_elevenlabs.txt에서 찾지 못해 기본 목소리로 진행합니다.")
    if voice_map:
        print(f"   💡 사용 가능한 목소리: {', '.join(sorted(voice_map.keys())[:10])}...")
    
    return {"id": default_id, "model": "eleven_multilingual_v2", "rate": None, "pitch": None}

# ==========================================
# 3. Key Manager (일레븐랩스 좀비 모드)
# ==========================================
class KeyManager:
    def __init__(self):
        self.keys = []
        self.current_idx = 0
        self._load_keys()

    def _load_keys(self):
        # KeyKey*.txt 파일 탐색
        key_dir = r"C:\YtFactory9\_System\02_Key"
        key_files = glob.glob(os.path.join(key_dir, "KeyKey*.txt"))
        print(f"🔍 키 파일 탐색: {[os.path.basename(k) for k in key_files]}")
        
        for kf in key_files:
            try:
                with open(kf, "r", encoding="utf-8") as f:
                    content = f.read()
                    # sk_ 로 시작하는 키 패턴 찾기
                    found = re.findall(r'(sk_[a-zA-Z0-9]{30,})', content)
                    self.keys.extend(found)
            except: pass
        
        self.keys = list(set(self.keys)) # 중복 제거
        random.shuffle(self.keys) # 섞기
        print(f"🔑 로드된 ElevenLabs 키: {len(self.keys)}개")

    def get_current_key(self):
        if not self.keys: return None
        return self.keys[self.current_idx]

    def switch_key(self):
        if self.current_idx < len(self.keys) - 1:
            self.current_idx += 1
            print(f"🔄 [Key Change] 키 교체! ({self.current_idx+1}/{len(self.keys)})")
            return True
        else:
            print("❌ [Key Exhausted] 모든 키가 소진되었습니다.")
            return False

# ==========================================
# 4. 유틸리티 함수
# ==========================================
def load_spreadsheet(client):
    """
    Sheet_URL.txt 내용을 읽어서 스프레드시트에 접속.
    - URL 전체를 넣어두면 open_by_url 사용
    - ID만 넣어두면 open_by_key 사용
    """
    if not os.path.exists(SHEET_URL_FILE):
        raise FileNotFoundError(f"Sheet_URL.txt 파일을 찾을 수 없습니다: {SHEET_URL_FILE}")

    with open(SHEET_URL_FILE, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    if not raw:
        raise ValueError("Sheet_URL.txt 파일이 비어 있습니다.")

    if "https://docs.google.com" in raw:
        return client.open_by_url(raw)
    else:
        return client.open_by_key(raw)

def _extract_voice_id_from_file(voice_file_path: str, target_name: str = ""):
    """지정된 txt 파일에서 Voice ID만 엄격하게 추출"""
    if not voice_file_path or not os.path.exists(voice_file_path):
        return None

    final_id = None
    try:
        with open(voice_file_path, 'r', encoding='utf-8') as f:
            content = f.read().replace('\n', '')
            # "voice id :" 등 앞부분 제거
            cleaned = re.sub(r'(?i)voice\s*id\s*[:=]\s*', '', content)

            # 20자리 ID 패턴 우선 탐색
            match = re.search(r'[a-zA-Z0-9]{20}', cleaned)
            if match:
                final_id = match.group(0)
            else:
                # 없으면 괄호나 태그 앞부분까지만 사용
                final_id = cleaned.split('<')[0].split('(')[0].strip()
    except Exception as e:
        print(f"❌ 목소리 ID 추출 실패 ({os.path.basename(voice_file_path)}): {e}")
        return None

    if final_id:
        if target_name:
            print(f"✅ 목소리 설정: {target_name} (ID: {final_id})")
        else:
            print(f"✅ 목소리 ID 추출 성공 (ID: {final_id})")
        return final_id
    return None


def get_voice_id_by_name(target_name: str):
    """시트의 성우 이름으로 04_Asset/Voice 에서 ID 추출"""
    if not target_name:
        return None

    voice_file_path = None
    candidates = glob.glob(os.path.join(ASSET_VOICE_DIR, "*.txt"))

    for c in candidates:
        if target_name in os.path.basename(c):
            voice_file_path = c
            break

    if not voice_file_path:
        print(f"   ⚠️ '{target_name}' 성우 txt를 {ASSET_VOICE_DIR}에서 찾지 못했습니다.")
        return None

    return _extract_voice_id_from_file(voice_file_path, target_name)

def get_audio_duration(audio_path):
    """ 오디오 파일 길이 정밀 측정 (ffprobe, float 리턴) """
    try:
        cmd = [
            FFPROBE_CMD, "-v", "error", "-show_entries", 
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except:
        return 0.0

def get_video_duration(video_path):
    """ 비디오 파일 길이 정밀 측정 (ffprobe, float 리턴) """
    try:
        cmd = [
            FFPROBE_CMD, "-v", "error", "-show_entries", 
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except:
        return 0.0

def generate_silent_audio(duration_seconds, save_path):
    """ 지정된 길이의 묵음 MP3 파일 생성 (pydub 사용)
    
    Args:
        duration_seconds: 묵음 길이 (초 단위)
        save_path: 저장할 파일 경로
    
    Returns:
        bool: 성공 여부
    """
    if not PYDUB_AVAILABLE:
        print(f"   ❌ pydub가 없어 묵음 오디오를 생성할 수 없습니다.")
        return False
    
    try:
        # 묵음 오디오 생성 (44100Hz, 16bit 기본값)
        silent_audio = AudioSegment.silent(duration=int(duration_seconds * 1000))  # 밀리초 단위
        silent_audio.export(save_path, format="mp3", bitrate="128k")
        print(f"   ✅ 묵음 오디오 생성 완료: {duration_seconds:.2f}초")
        return True
    except Exception as e:
        print(f"   ❌ 묵음 오디오 생성 실패: {e}")
        return False

def apply_audio_speed_pitch(audio_path, rate=None, pitch=None):
    """ 오디오 파일에 속도/피치 조절 적용 (pydub 사용)
    
    Args:
        audio_path: 오디오 파일 경로
        rate: 속도 조절 (예: "+10%" -> 1.1배, "-15%" -> 0.85배)
        pitch: 피치 조절 (Hz 단위, 예: "+5Hz", "-5Hz")
    
    Returns:
        bool: 성공 여부
    """
    if not PYDUB_AVAILABLE:
        print(f"   ⚠️ pydub가 없어 속도/피치 조절을 건너뜁니다.")
        return False
    
    if not rate and not pitch:
        return False  # 조절할 게 없음
    
    try:
        # 오디오 로드
        audio = AudioSegment.from_mp3(audio_path)
        
        # 속도 조절
        if rate and rate != "0":
            try:
                # "+20%" -> 1.2, "-15%" -> 0.85
                rate_clean = rate.replace("%", "").strip()
                rate_value = float(rate_clean)
                rate_multiplier = 1.0 + (rate_value / 100.0)
                
                # 속도 조절 (pydub의 frame_rate 조절 사용)
                audio = audio._spawn(audio.raw_data, overrides={
                    "frame_rate": int(audio.frame_rate * rate_multiplier)
                }).set_frame_rate(audio.frame_rate)
                print(f"   🎵 속도 조절: {rate} ({rate_multiplier:.2f}배)")
            except Exception as e:
                print(f"   ⚠️ 속도 조절 실패: {e}")
        
        # 피치 조절 (Hz)
        if pitch and pitch != "0":
            try:
                # "+5Hz" -> 5, "-5Hz" -> -5
                pitch_clean = pitch.replace("Hz", "").strip()
                pitch_hz = float(pitch_clean)
                
                # 피치 조절 (frame_rate 조절로 피치 변경)
                # Hz를 semitone으로 근사 변환 (1Hz ≈ 0.25 semitone)
                semitones = pitch_hz * 0.25
                new_sample_rate = int(audio.frame_rate * (2 ** (semitones / 12.0)))
                audio = audio._spawn(audio.raw_data, overrides={
                    "frame_rate": new_sample_rate
                }).set_frame_rate(audio.frame_rate)
                print(f"   🎵 피치 조절: {pitch} ({semitones:.2f} semitones)")
            except Exception as e:
                print(f"   ⚠️ 피치 조절 실패: {e}")
        
        # 파일 저장
        audio.export(audio_path, format="mp3")
        return True
        
    except Exception as e:
        print(f"   ❌ 오디오 후처리 에러: {e}")
        return False

def generate_elevenlabs_audio(text, voice_id, save_path, key_manager, model_id="eleven_multilingual_v2", rate=None, pitch=None):
    """ ElevenLabs API 호출 (Zombie Key 적용, 속도/피치 조절 지원)
    
    Args:
        text: 음성으로 변환할 텍스트
        voice_id: ElevenLabs Voice ID
        save_path: 저장할 파일 경로
        key_manager: KeyManager 객체
        model_id: 모델 ID (기본값: eleven_multilingual_v2)
        rate: 속도 (예: "+10%", "-15%")
        pitch: 피치 (예: "+5Hz", "-5Hz")
    """
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    
    # 임시 파일 경로 (후처리 전용)
    temp_path = save_path + ".temp.mp3" if rate or pitch else save_path
    
    while True:
        api_key = key_manager.get_current_key()
        if not api_key: return False, 0.0

        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        data = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        try:
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 200:
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                
                # 속도/피치 조절이 있으면 후처리
                if rate or pitch:
                    apply_audio_speed_pitch(temp_path, rate, pitch)
                    # 후처리된 파일을 최종 경로로 이동
                    if os.path.exists(temp_path) and temp_path != save_path:
                        import shutil
                        shutil.move(temp_path, save_path)
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                
                # 오디오 길이 측정
                duration = get_audio_duration(save_path)
                return True, duration
            
            elif response.status_code in [401, 402, 429]: # 키 만료/잔액부족/제한
                print(f"   ⚠️ 키 오류 ({response.status_code}). 교체 시도...")
                if not key_manager.switch_key():
                    return False, 0.0
            else:
                print(f"   ❌ API 오류: {response.status_code} - {response.text}")
                return False, 0.0
                
        except Exception as e:
            print(f"   ❌ 통신 에러: {e}")
            return False, 0.0

def process_text_for_ssml(text):
    """ 대본 텍스트를 SSML용으로 처리 (pause 태그 변환 및 특수문자 이스케이프)
    
    Args:
        text: 원본 대본 텍스트
    
    Returns:
        str: SSML 태그로 변환된 텍스트
    
    처리 내용:
        1. [pause:N] 태그를 <break time="Ns"/> 태그로 변환
        2. XML 특수문자 이스케이프 (<, >, &, ", ')
        3. break 태그는 다시 원래대로 복원
    """
    if not text:
        return ""
    
    # 1. [pause:N] 또는 [pause:N초] 태그를 임시 플레이스홀더로 변환
    # 예: [pause:2] -> __PAUSE_2__
    # 예: [pause:1.5] -> __PAUSE_1.5__
    # 예: [pause:0.5초] -> __PAUSE_0.5__
    pause_pattern = r'\[pause:([0-9.]+)(?:초|s|sec)?\]'
    pause_placeholders = {}  # {플레이스홀더: 실제 break 태그}
    
    def replace_pause_with_placeholder(match):
        pause_time = match.group(1)
        # 숫자 검증
        try:
            time_val = float(pause_time)
            if time_val <= 0:
                return ""  # 0 이하는 무시
            # 최대 10초로 제한 (너무 긴 pause 방지)
            if time_val > 10:
                time_val = 10
            placeholder = f"__PAUSE_{time_val}__"
            pause_placeholders[placeholder] = f'<break time="{time_val}s"/>'
            return placeholder
        except:
            return ""  # 변환 실패 시 제거
    
    text = re.sub(pause_pattern, replace_pause_with_placeholder, text, flags=re.IGNORECASE)
    
    # 2. XML 특수문자 이스케이프 (XML Injection 방지)
    # < -> &lt;, > -> &gt;, & -> &amp;, " -> &quot;, ' -> &apos;
    text = html.escape(text, quote=True)
    
    # 3. 플레이스홀더를 실제 SSML break 태그로 복원
    for placeholder, break_tag in pause_placeholders.items():
        text = text.replace(html.escape(placeholder, quote=False), break_tag)
    
    return text

def parse_rate_for_ssml(rate_str):
    """ 속도 문자열을 Edge TTS rate 형식으로 변환
    +20% -> +20%
    -10% -> -10%
    0 -> None (기본값, 파라미터 생략)
    """
    if not rate_str or rate_str == "0":
        return None  # 기본값일 때는 None 반환 (파라미터 생략)
    
    # +20%, -10% 형식 그대로 반환
    if "%" in rate_str:
        rate_clean = rate_str.strip()
        # "+0%"도 기본값으로 처리
        if rate_clean == "+0%" or rate_clean == "0%":
            return None
        return rate_clean
    
    # 숫자만 있는 경우 (예: "20" -> "+20%")
    try:
        num = float(rate_str)
        if num == 0:
            return None  # 0은 기본값
        return f"{'+' if num >= 0 else ''}{int(num)}%"
    except:
        pass
    
    return None  # 기본값

def parse_pitch_for_ssml(pitch_str):
    """ 피치 문자열을 Edge TTS pitch 형식으로 변환
    +5Hz -> +5Hz
    -2Hz -> -2Hz
    0 -> None (기본값, 파라미터 생략)
    """
    if not pitch_str or pitch_str == "0":
        return None  # 기본값일 때는 None 반환 (파라미터 생략)
    
    # Hz 포함된 형식 -> Edge TTS는 Hz를 직접 지원하므로 그대로 사용
    if "Hz" in pitch_str:
        pitch_clean = pitch_str.strip()
        # "+0Hz"도 기본값으로 처리
        if pitch_clean == "+0Hz" or pitch_clean == "0Hz":
            return None
        return pitch_clean
    
    # 숫자만 있는 경우 (예: "5" -> "+5Hz")
    try:
        num = float(pitch_str)
        if num == 0:
            return None  # 0은 기본값
        return f"{'+' if num >= 0 else ''}{int(num)}Hz"
    except:
        pass
    
    return None  # 기본값

def convert_pitch_hz_to_percent(pitch_str):
    """ 피치 Hz를 SSML 호환 퍼센트로 변환
    SSML prosody pitch는 상대값(%) 또는 semitone(st) 사용
    Hz를 퍼센트로 근사 변환 (대략 1Hz ≈ 2-3%)
    """
    if not pitch_str or "Hz" not in pitch_str:
        return pitch_str
    
    try:
        # "+5Hz" -> 5
        hz_value = float(pitch_str.replace("Hz", "").replace("+", "").replace("-", ""))
        sign = "+" if "+" in pitch_str else "-"
        
        # Hz를 퍼센트로 변환 (1Hz ≈ 2.5%, 대략적)
        percent_value = hz_value * 2.5
        return f"{sign}{int(percent_value)}%"
    except:
        return pitch_str

def create_ssml_with_prosody(text, voice_name, rate=None, pitch=None):
    """ SSML 생성 (속도/피치 조절 포함, 특수문자 이스케이프 및 pause 처리) 
    
    주의: Edge TTS는 SSML 내부의 <voice> 태그를 제대로 처리하지 못할 수 있으므로,
    voice는 Communicate() 함수의 파라미터로 별도 전달해야 합니다.
    """
    # 대본 텍스트 처리 (pause 태그 변환 및 특수문자 이스케이프)
    processed_text = process_text_for_ssml(text)
    
    # 언어 코드 추출 (예: ko-KR-SunHiNeural -> ko-KR)
    lang_code = voice_name.split("-")[0] + "-" + voice_name.split("-")[1] if "-" in voice_name else "ko-KR"
    
    prosody_attrs = []
    if rate:
        prosody_attrs.append(f'rate="{rate}"')
    if pitch:
        # SSML에서 pitch는 상대값(%) 또는 st(semitone) 사용
        # Hz 형식이면 퍼센트로 변환 시도
        if "Hz" in str(pitch):
            pitch = convert_pitch_hz_to_percent(pitch)
        prosody_attrs.append(f'pitch="{pitch}"')
    
    prosody_attr_str = " " + " ".join(prosody_attrs) if prosody_attrs else ""
    
    # Edge TTS는 SSML 내부의 <voice> 태그를 제대로 처리하지 못하므로 제거
    # voice는 Communicate() 함수의 파라미터로 전달
    if prosody_attr_str:
        ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang_code}">
    <prosody{prosody_attr_str}>
        {processed_text}
    </prosody>
</speak>'''
    else:
        # prosody가 없으면 단순 speak 태그만 사용
        ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang_code}">
    {processed_text}
</speak>'''
    return ssml

async def generate_edge_tts_audio_async(text, voice_name, save_path, rate=None, pitch=None):
    """ Edge TTS를 사용한 음성 생성 (비동기, 속도/피치 조절 지원) 
    
    주의: Edge TTS는 커스텀 SSML을 지원하지 않으므로, rate와 pitch는 Communicate() 함수의
    직접 파라미터로 전달해야 합니다. SSML을 사용하면 텍스트로 읽혀버립니다.
    """
    max_retries = 3
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            # 텍스트 검증
            if not text or not text.strip():
                print(f"   ⚠️ 텍스트가 비어있습니다.")
                return False, 0.0
            
            # Edge TTS는 SSML을 지원하지 않으므로 원본 텍스트 사용
            # pause 태그가 있으면 제거
            clean_text = text.strip()
            # [pause:N] 태그 제거 (Edge TTS는 pause를 지원하지 않음)
            clean_text = re.sub(r'\[pause:[0-9.]+(?:초|s|sec)?\]', '', clean_text, flags=re.IGNORECASE)
            
            # 텍스트가 여전히 비어있는지 확인
            if not clean_text or not clean_text.strip():
                print(f"   ⚠️ 태그 제거 후 텍스트가 비어있습니다.")
                return False, 0.0
            
            # Edge TTS는 rate와 pitch가 None이면 파라미터 생략 (기본값 사용)
            # None이 아닌 경우에만 파라미터 전달
            communicate_kwargs = {"voice": voice_name}
            if rate:  # None이 아니고 기본값이 아닌 경우만
                communicate_kwargs["rate"] = rate
            if pitch:  # None이 아니고 기본값이 아닌 경우만
                communicate_kwargs["pitch"] = pitch
            
            # Communicate 함수에 rate와 pitch를 직접 전달 (기본값이면 생략)
            # text는 위치 인자, voice/rate/pitch는 키워드 인자
            communicate = edge_tts.Communicate(clean_text, **communicate_kwargs)
            
            await communicate.save(save_path)
            
            # 파일이 제대로 생성되었는지 확인
            if not os.path.exists(save_path):
                raise Exception("오디오 파일이 생성되지 않았습니다.")
            
            file_size = os.path.getsize(save_path)
            if file_size == 0:
                raise Exception("생성된 오디오 파일이 비어있습니다 (0바이트).")
            
            # 오디오 길이 측정
            duration = get_audio_duration(save_path)
            if duration == 0:
                raise Exception("오디오 길이를 측정할 수 없습니다.")
            
            return True, duration
            
        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                print(f"   ⚠️ Edge TTS 시도 {attempt + 1}/{max_retries} 실패, {retry_delay}초 후 재시도... ({error_msg})")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # 지수 백오프
            else:
                print(f"   ❌ Edge TTS 에러 (재시도 {max_retries}회 실패): {error_msg}")
                import traceback
                traceback.print_exc()
                return False, 0.0
    
    return False, 0.0

def generate_edge_tts_audio(text, voice_name, save_path, rate=None, pitch=None):
    """ Edge TTS를 사용한 음성 생성 (동기 래퍼, 속도/피치 조절 지원)
    
    Args:
        text: 음성으로 변환할 텍스트
        voice_name: Edge TTS Voice ID (예: 'ko-KR-SunHiNeural')
        save_path: 저장할 파일 경로
        rate: 속도 (예: '+20%', '-10%')
        pitch: 피치 (예: '+5Hz', '-2Hz')
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(generate_edge_tts_audio_async(text, voice_name, save_path, rate, pitch))
    finally:
        loop.close()

def get_azure_key_and_region():
    """ Azure TTS 키와 리전 가져오기 (KeyKey*.txt 파일에서) """
    # 여러 경로에서 키 파일 검색
    key_dirs = [
        r"C:\YtFactory9\_System\02_Key",
        r"C:\YtFactory9\_System\04_Co_Asset\Voice"
    ]
    key_files = []
    for key_dir in key_dirs:
        if os.path.exists(key_dir):
            key_files.extend(glob.glob(os.path.join(key_dir, "KeyKey*.txt")))
    azure_key = None
    azure_region = None
    
    for kf in key_files:
        try:
            with open(kf, "r", encoding="utf-8") as f:
                content = f.read()
                # Azure 키 패턴 찾기 (Azure 키는 보통 32자 이상의 영숫자 문자열)
                # 여러 패턴 시도: 32자리 이상의 영숫자 문자열
                azure_key_match = re.search(r'([a-zA-Z0-9]{32,})', content)
                if azure_key_match:
                    potential_key = azure_key_match.group(1)
                    # URL이나 다른 긴 문자열이 아닌지 확인
                    if 'http' not in potential_key.lower() and len(potential_key) <= 200:
                        azure_key = potential_key
                
                # 리전 찾기 - 섹션 기반 파싱 개선
                # [AZURE] 섹션 또는 REGION= 형식 지원
                lines = content.split('\n')
                in_azure_section = False
                for line in lines:
                    line = line.strip()
                    # 섹션 시작 체크
                    if '[AZURE]' in line.upper() or '[AZURE_TTS]' in line.upper():
                        in_azure_section = True
                        continue
                    # 다른 섹션 시작 시 종료
                    if line.startswith('[') and '[AZURE' not in line.upper():
                        in_azure_section = False
                        continue
                    
                    # REGION= 형식 찾기
                    if 'REGION' in line.upper() and '=' in line:
                        region_match = re.search(r'REGION\s*=\s*([a-zA-Z0-9-]+)', line, re.IGNORECASE)
                        if region_match:
                            azure_region = region_match.group(1).lower()
                            break
                    
                    # 섹션 내에서 리전 키워드 찾기
                    if in_azure_section:
                        region_match = re.search(r'(koreacentral|eastus|westus|japaneast|southeastasia|westus2|westus3|eastasia)', line, re.IGNORECASE)
                        if region_match:
                            azure_region = region_match.group(1).lower()
                            break
                
                # 섹션 파싱으로 찾지 못한 경우 전체 검색
                if not azure_region:
                    region_match = re.search(r'(koreacentral|eastus|westus|japaneast|southeastasia|westus2|westus3|eastasia)', content, re.IGNORECASE)
                    if region_match:
                        azure_region = region_match.group(1).lower()
        except Exception as e:
            print(f"   ⚠️ Azure 키 파일 읽기 에러 ({os.path.basename(kf)}): {e}")
            pass
    
    return azure_key, azure_region

def create_azure_ssml_with_prosody(text, voice_name, rate=None, pitch=None, style=None):
    """ Azure TTS용 SSML 생성 (속도/피치/스타일 조절 포함, 특수문자 이스케이프 및 pause 처리) """
    # 대본 텍스트 처리 (pause 태그 변환 및 특수문자 이스케이프)
    processed_text = process_text_for_ssml(text)
    
    # 언어 코드 추출 (예: ko-KR-BongJinNeural -> ko-KR)
    lang_code = voice_name.split("-")[0] + "-" + voice_name.split("-")[1] if "-" in voice_name else "ko-KR"
    
    prosody_attrs = []
    if rate:
        # Azure TTS rate 검증: 음수 값도 지원하지만 범위 제한 확인
        rate_clean = rate.replace("%", "").strip()
        try:
            rate_num = float(rate_clean)
            # Azure TTS rate 범위: 일반적으로 -50% ~ +100%
            if rate_num < -50 or rate_num > 100:
                print(f"   ⚠️ rate 값이 범위를 벗어남 ({rate}), -50% ~ +100% 범위로 조정 권장")
            # Azure TTS rate는 반드시 + 또는 - 기호가 있어야 함
            if not rate.startswith(('+', '-')):
                rate = f"+{rate_num}%" if rate_num >= 0 else f"{rate_num}%"
        except:
            pass
        prosody_attrs.append(f'rate="{rate}"')
    if pitch:
        # Azure TTS에서 pitch는 상대값(%) 사용 (Hz는 변환 필요)
        if "Hz" in str(pitch):
            # Hz를 퍼센트로 변환
            pitch_percent = convert_pitch_hz_to_percent(pitch)
            # Azure TTS pitch는 반드시 + 또는 - 기호가 있어야 함
            pitch_clean = pitch_percent.replace("%", "").strip()
            try:
                pitch_num = float(pitch_clean)
                if not pitch_percent.startswith(('+', '-')):
                    pitch_percent = f"+{pitch_num}%" if pitch_num >= 0 else f"{pitch_num}%"
            except:
                pass
            prosody_attrs.append(f'pitch="{pitch_percent}"')
        else:
            # pitch 값 검증: 음수 값도 지원하지만 범위 제한 확인
            pitch_clean = str(pitch).replace("%", "").strip()
            try:
                pitch_num = float(pitch_clean)
                # Azure TTS pitch 범위: 일반적으로 -50% ~ +50%
                if pitch_num < -50 or pitch_num > 50:
                    print(f"   ⚠️ pitch 값이 범위를 벗어남 ({pitch}), -50% ~ +50% 범위로 조정 권장")
                # Azure TTS pitch는 반드시 + 또는 - 기호가 있어야 함
                if not str(pitch).startswith(('+', '-')):
                    pitch = f"+{pitch_num}%" if pitch_num >= 0 else f"{pitch_num}%"
            except:
                pass
            prosody_attrs.append(f'pitch="{pitch}"')
    
    prosody_attr_str = " " + " ".join(prosody_attrs) if prosody_attrs else ""
    
    # prosody 태그가 있으면 style_tag를 감싸기
    if prosody_attr_str:
        if style and style != "General":
            ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lang_code}">
    <voice name="{voice_name}">
        <prosody{prosody_attr_str}>
            <mstts:express-as style="{style}">
                {processed_text}
            </mstts:express-as>
        </prosody>
    </voice>
</speak>'''
        else:
            ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang_code}">
    <voice name="{voice_name}">
        <prosody{prosody_attr_str}>
            {processed_text}
        </prosody>
    </voice>
</speak>'''
    else:
        if style and style != "General":
            ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lang_code}">
    <voice name="{voice_name}">
        <mstts:express-as style="{style}">
            {processed_text}
        </mstts:express-as>
    </voice>
</speak>'''
        else:
            ssml = f'''<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{lang_code}">
    <voice name="{voice_name}">
        {processed_text}
    </voice>
</speak>'''
    
    return ssml

def generate_azure_tts_audio(text, voice_name, save_path, rate=None, pitch=None, style=None):
    """ Azure TTS를 사용한 음성 생성 (속도/피치/스타일 조절 지원)
    
    Args:
        text: 음성으로 변환할 텍스트
        voice_name: Azure TTS Voice ID (예: 'ko-KR-BongJinNeural')
        save_path: 저장할 파일 경로
        rate: 속도 (예: '+15%', '-10%')
        pitch: 피치 (예: '-5Hz', '+2Hz')
        style: 스타일 (예: 'News', 'Sad', 'Cheerful', 'CustomerService')
    """
    if not AZURE_AVAILABLE:
        print(f"   ❌ Azure Speech SDK가 설치되지 않았습니다.")
        return False, 0.0
    
    try:
        azure_key, azure_region = get_azure_key_and_region()
        
        if not azure_key:
            print(f"   ❌ Azure TTS 키를 찾을 수 없습니다. KeyKey*.txt 파일을 확인하세요.")
            return False, 0.0
        
        if not azure_region:
            azure_region = "koreacentral"  # 기본값
            print(f"   ⚠️ Azure 리전을 찾지 못해 기본값({azure_region})을 사용합니다.")
        
        # Azure Speech SDK 설정
        speech_config = speechsdk.SpeechConfig(subscription=azure_key, region=azure_region)
        
        # 목소리 설정
        if voice_name:
            speech_config.speech_synthesis_voice_name = voice_name
            print(f"   🔍 Azure 설정: voice={voice_name}, region={azure_region}")
        else:
            print(f"   ⚠️ voice_name이 비어있습니다!")
        
        # 출력 파일 설정
        audio_config = speechsdk.audio.AudioOutputConfig(filename=save_path)
        
        # Speech Synthesizer 생성
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        
        # 속도나 피치나 스타일이 있으면 SSML 사용, 없으면 일반 텍스트 사용
        # Azure TTS는 SSML을 통해 음수 rate/pitch 값을 지원하므로 모두 사용
        if rate or pitch or (style and style != "General"):
            ssml_text = create_azure_ssml_with_prosody(text, voice_name, rate, pitch, style)
            # SSML 디버깅 (오류 발생 시 확인용)
            print(f"   🔍 SSML 생성됨 (rate={rate}, pitch={pitch}, style={style})")
            if len(ssml_text) > 500:
                print(f"   🔍 SSML 미리보기: {ssml_text[:300]}...")
            else:
                print(f"   🔍 SSML 전체: {ssml_text}")
            try:
                result = synthesizer.speak_ssml_async(ssml_text).get()
            except Exception as ssml_error:
                print(f"   ❌ SSML 실행 오류: {ssml_error}")
                # SSML 오류 시 간단한 텍스트로 재시도
                print(f"   🔄 간단한 텍스트로 재시도...")
                result = synthesizer.speak_text_async(text).get()
        else:
            # 기본 음성 합성 (SSML 없이)
            print(f"   🔍 SSML 없이 일반 텍스트로 생성 시도: {text[:50]}...")
            result = synthesizer.speak_text_async(text).get()
        
        # result 객체 안전성 검증
        if result is None:
            print(f"   ❌ Azure TTS: result가 None입니다.")
            # 생성된 파일이 있으면 삭제
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except:
                    pass
            return False, 0.0
        
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            # 오디오 길이 측정
            duration = get_audio_duration(save_path)
            # 파일이 제대로 생성되었는지 확인 (크기가 0이면 실패)
            if os.path.exists(save_path):
                file_size = os.path.getsize(save_path)
                if file_size == 0:
                    print(f"   ❌ 생성된 파일이 비어있습니다 (0바이트).")
                    try:
                        os.remove(save_path)
                    except:
                        pass
                    return False, 0.0
            return True, duration
        elif result.reason == speechsdk.ResultReason.Canceled:
            # CancellationDetails 생성 시 예외 처리 (SPXERR_INVALID_ARG 방지)
            # result 객체의 속성을 먼저 확인하여 오류 정보 추출 시도
            error_info = None
            try:
                # result 객체의 error_details 속성 직접 확인
                if hasattr(result, 'error_details') and result.error_details:
                    error_info = result.error_details
            except:
                pass
            
            # CancellationDetails 생성 시도 (실패해도 계속 진행)
            try:
                cancellation_details = speechsdk.CancellationDetails(result)
                print(f"   ❌ Azure TTS 취소됨: {cancellation_details.reason}")
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    error_info = cancellation_details.error_details
                    if error_info:
                        print(f"   ❌ 에러 상세: {error_info}")
            except Exception:
                # CancellationDetails 생성 실패 시에도 계속 진행
                print(f"   ❌ Azure TTS 취소됨 (오류 코드: SPXERR_INVALID_ARG)")
                if error_info:
                    print(f"   ❌ 에러 상세: {error_info}")
                else:
                    print(f"   💡 SSML 또는 음성 설정을 확인해주세요.")
            
            # 오류 발생 시 생성된 손상된 파일 삭제 시도 (실패해도 계속 진행)
            if os.path.exists(save_path):
                file_size = os.path.getsize(save_path)
                # 파일 삭제 시도 (최대 2회, 각 0.3초 대기)
                for retry in range(2):
                    try:
                        time.sleep(0.3)  # 파일 핸들이 해제될 때까지 대기
                        os.remove(save_path)
                        break  # 성공하면 종료
                    except Exception:
                        if retry == 1:  # 마지막 시도
                            # 삭제 실패해도 계속 진행 (파일이 남아있어도 다음 단계에서 덮어쓰기 가능)
                            pass
                        continue
            
            return False, 0.0
        else:
            print(f"   ❌ Azure TTS 실패: {result.reason}")
            # 실패 시 생성된 파일 삭제
            if os.path.exists(save_path):
                try:
                    os.remove(save_path)
                except:
                    pass
            return False, 0.0
            
    except Exception as e:
        print(f"   ❌ Azure TTS 에러: {e}")
        import traceback
        traceback.print_exc()
        return False, 0.0


def get_edge_voice_info(voice_input):
    """ Edge TTS 목소리 정보 가져오기 (voices_edge.txt 사용)
    
    Args:
        voice_input: I열에 입력된 호출이름 (예: '선희_기본', '인준_기본')
    
    Returns:
        dict: {"id": "voice_id", "rate": "속도값", "pitch": "피치값"}
              또는 voice_input이 전체 ID 형식이면 {"id": "voice_id", "rate": None, "pitch": None}
    
    Logic:
        - L열에 'edge'가 적혀있으면 이 함수가 호출됨
        - I열의 '선희_기본' 같은 값을 voices_edge.txt에서 찾아서 ID, 속도, 피치 반환
    """
    # voices_edge.txt 매핑 로드
    voice_map = load_edge_voices_map()
    
    if not voice_input or not voice_input.strip():
        # 기본 진중한 남성 목소리: 인준_기본
        default_info = voice_map.get("인준_기본")
        if default_info:
            print(f"   ℹ️ voice가 비어있어 기본 목소리 사용: {default_info['id']}")
            return default_info
        else:
            return {"id": "ko-KR-InJoonNeural", "rate": None, "pitch": None}
    
    voice_input_clean = voice_input.strip()
    
    # voices_edge.txt에서 호출이름으로 찾기 (정확한 매칭)
    if voice_input_clean in voice_map:
        found_info = voice_map[voice_input_clean]
        rate_str = f", rate={found_info['rate']}" if found_info.get('rate') and found_info['rate'] != "0" else ""
        pitch_str = f", pitch={found_info['pitch']}" if found_info.get('pitch') and found_info['pitch'] != "0" else ""
        print(f"   ✅ '{voice_input_clean}' -> '{found_info['id']}'{rate_str}{pitch_str} (voices_edge.txt에서 찾음)")
        return found_info
    
    # 매핑에 없으면, 이미 전체 목소리 이름 형식인지 확인 (예: "ko-KR-InJoonNeural")
    if "ko-" in voice_input_clean or "-Neural" in voice_input_clean or "en-" in voice_input_clean:
        # 이미 전체 이름 형식으로 입력된 경우 그대로 사용 (속도/피치 없음)
        print(f"   ℹ️ 전체 Voice ID 형식으로 인식: {voice_input_clean}")
        return {"id": voice_input_clean, "rate": None, "pitch": None}
    
    # Azure 목소리 이름이면 Azure 목소리 ID 그대로 사용 (Edge TTS에는 없지만 매핑)
    # 예: 봉진_산신령 -> ko-KR-BongJinNeural
    azure_voice_map = load_azure_voices_map()
    if voice_input_clean in azure_voice_map:
        azure_info = azure_voice_map[voice_input_clean]
        azure_id = azure_info["id"]
        print(f"   ⚠️ '{voice_input_clean}'는 Edge TTS에 없지만 Azure 목소리({azure_id})로 인식했습니다.")
        print(f"   💡 Edge TTS는 이 목소리를 지원하지 않으므로 Azure TTS를 사용해야 합니다.")
        # Edge TTS에는 봉진 목소리가 없으므로 가장 비슷한 목소리로 매핑 (인준 기본)
        return {"id": "ko-KR-InJoonNeural", "rate": None, "pitch": None}
    
    # 그 외의 경우 기본값 반환
    default_info = voice_map.get("인준_기본")
    if default_info:
        default_id = default_info['id']
    else:
        default_id = "ko-KR-InJoonNeural"
    
    print(f"   ⚠️ '{voice_input_clean}' 목소리를 voices_edge.txt에서 찾지 못해 기본 목소리({default_id})로 진행합니다.")
    if voice_map:
        print(f"   💡 사용 가능한 목소리: {', '.join(sorted(voice_map.keys())[:10])}...")
    
    return {"id": default_id, "rate": None, "pitch": None}

# ==========================================
# 4. 메인 실행
# ==========================================
def main():
    print(f"🚀 VoiceMaker v3.0 (ElevenLabs + Edge TTS + Azure TTS)")
    
    # === [자동 선택 로직] - 비활성화됨 ===
    # auto_sheet_file = AUTO_SHEET_FILE
    # selected_sheet_name = None
    # if os.path.exists(auto_sheet_file):
    #     try:
    #         with open(auto_sheet_file, 'r', encoding='utf-8') as f:
    #             selected_sheet_name = f.read().strip()
    #             print(f"🤖 [Auto] 시트 자동 선택됨: {selected_sheet_name}")
    #     except: pass
    # ========================
    
    # 1. Edge TTS 목소리 매핑 로드
    load_edge_voices_map()
    
    # 1-1. Azure TTS 목소리 매핑 로드
    load_azure_voices_map()
    
    # 1-2. ElevenLabs TTS 목소리 매핑 로드
    load_elevenlabs_voices_map()
    
    # 2. 키 로드 (ElevenLabs 전용)
    km = KeyManager()
    
    # 2-1. Azure 키 확인 (한 번만 확인)
    azure_available_and_configured = False
    if AZURE_AVAILABLE:
        azure_key, azure_region = get_azure_key_and_region()
        if azure_key:
            azure_available_and_configured = True
            print(f"✅ Azure TTS 설정 확인 완료 (region: {azure_region or 'koreacentral'})")
        else:
            print(f"⚠️ Azure TTS SDK는 설치되어 있지만 키가 없습니다. Edge TTS로 자동 전환됩니다.")

    # 3. 구글 시트 연결
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        doc = load_spreadsheet(client)
    except Exception as e:
        print(f"❌ 시트 접속 실패: {e}"); return

    # 4. 시트 선택
    all_worksheets = doc.worksheets()
    go_sheets = [ws for ws in all_worksheets if "go" in ws.title.lower()]

    if not go_sheets:
        print("❌ 'go' 시트가 없습니다.")
        return

    print("\n" + "="*40)
    print(" 🎤 [VoiceMaker] 작업할 시트를 선택하세요")
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
        except: pass

    print(f"✅ 선택된 시트: '{selected_sheet.title}'")

    # 5. 시트 이름에서 채널명 추출 및 폴더 생성
    sheet_title = selected_sheet.title
    channel_match = re.search(r'Ch\d+', sheet_title)
    if not channel_match:
        print(f"❌ 시트 이름에서 채널명을 추출할 수 없습니다: {sheet_title}")
        return
    channel_name = channel_match.group(0)  # 예: "Ch01"
    
    # 출력 경로: C:\YtFactory9\{channel_name}\03_Output\{sheet_title}\Voice
    voice_output_dir = f"C:\\YtFactory9\\{channel_name}\\03_Output\\{sheet_title}\\Voice"
    if not os.path.exists(voice_output_dir):
        os.makedirs(voice_output_dir)
        print(f"📂 폴더 생성: {voice_output_dir}")
    
    # 6. 데이터 로드
    rows = selected_sheet.get_all_values()[1:] # 헤더 제외
    total_count = len(rows)
    print(f"🎯 총 {total_count}개 행 처리 시작")

    success_count = 0
    duration_updates = []  # D열(음성 길이) 업데이트용 리스트

    for i, row in enumerate(rows):
        # A열: ID (파일명), B열: Script (내용)
        # I열(index 8): voice (성우 이름 또는 목소리 이름, 예: '선희_기본')
        # L열(index 11): voice_tool ("edge", "azure", "elevenlabs")
        if len(row) < 2: continue
        
        file_id = row[0].strip() if len(row) > 0 else ""  # A열 안전 접근
        script = row[1].strip() if len(row) > 1 else ""  # B열 안전 접근
        
        # ID나 스크립트 없으면 스킵
        if not file_id or not script:
            continue

        # I열에서 voice 이름 읽기 (안전 접근)
        voice_name = row[8].strip() if len(row) > 8 else ""
        # L열에서 voice_tool 읽기 (안전 접근, 소문자 변환)
        voice_tool = row[11].strip().lower() if len(row) > 11 else ""

        filename = f"{file_id}.mp3"
        save_path = os.path.join(voice_output_dir, filename)

        # 기존 파일이 있으면 길이만 측정해서 D열 업데이트
        if os.path.exists(save_path):
            # D열이 비어있거나 업데이트가 필요한 경우 (D열 = 인덱스 3)
            current_duration = row[3].strip() if len(row) > 3 else ""
            if not current_duration:
                duration = get_audio_duration(save_path)
                if duration > 0:
                    duration_updates.append({
                        "row": i + 2,  # 1-based + 헤더
                        "col": 4,  # D열 (1-based)
                        "value": f"{duration:.2f}"
                    })
            continue

        # 미드트로/아웃트로 체크: B열(script)에 키워드가 있으면 묵음 오디오 생성
        success = False
        duration = 0.0
        
        if "(미드트로)" in script:
            # 미드트로: Intro_Video.mp4 길이만큼 묵음 생성
            intro_video_path = f"C:\\YtFactory9\\{channel_name}\\02_Input\\Intro_Video.mp4"
            if os.path.exists(intro_video_path):
                video_duration = get_video_duration(intro_video_path)
                if video_duration > 0:
                    print(f"🎙️ 생성 중 [{file_id}] (묵음, 미드트로, {video_duration:.2f}초)")
                    success = generate_silent_audio(video_duration, save_path)
                    if success:
                        duration = video_duration
                else:
                    print(f"   ⚠️ 미드트로 비디오 길이를 측정할 수 없습니다: {intro_video_path}")
            else:
                print(f"   ⚠️ 미드트로 비디오 파일을 찾을 수 없습니다: {intro_video_path}")
        elif "(아웃트로)" in script:
            # 아웃트로: Outro_Video.mp4 길이만큼 묵음 생성
            outro_video_path = f"C:\\YtFactory9\\{channel_name}\\02_Input\\Outro_Video.mp4"
            if os.path.exists(outro_video_path):
                video_duration = get_video_duration(outro_video_path)
                if video_duration > 0:
                    print(f"🎙️ 생성 중 [{file_id}] (묵음, 아웃트로, {video_duration:.2f}초)")
                    success = generate_silent_audio(video_duration, save_path)
                    if success:
                        duration = video_duration
                else:
                    print(f"   ⚠️ 아웃트로 비디오 길이를 측정할 수 없습니다: {outro_video_path}")
            else:
                print(f"   ⚠️ 아웃트로 비디오 파일을 찾을 수 없습니다: {outro_video_path}")
        else:
            # 일반 TTS 생성 (기존 로직)
            # voice_tool에 따라 분기 처리
            if voice_tool == "edge":
                # Edge TTS 사용
                edge_voice_info = get_edge_voice_info(voice_name)
                edge_voice_id = edge_voice_info["id"]
                rate = parse_rate_for_ssml(edge_voice_info.get("rate"))
                pitch = parse_pitch_for_ssml(edge_voice_info.get("pitch"))
                
                rate_info = f", rate={rate}" if rate else ""
                pitch_info = f", pitch={pitch}" if pitch else ""
                print(f"🎙️ 생성 중 [{file_id}] (Edge TTS, voice='{voice_name}' -> '{edge_voice_id}'{rate_info}{pitch_info}): {script[:20]}...")
                success, duration = generate_edge_tts_audio(script, edge_voice_id, save_path, rate, pitch)
                
            elif voice_tool == "azure":
                # Azure TTS 사용 (SDK 없거나 키가 없으면 Edge TTS로 자동 전환)
                if not azure_available_and_configured:
                    if not AZURE_AVAILABLE:
                        print(f"   ⚠️ Azure SDK가 없어 Edge TTS로 자동 전환합니다.")
                    else:
                        print(f"   ⚠️ Azure 키가 없어 Edge TTS로 자동 전환합니다.")
                    # Edge TTS로 폴백
                    edge_voice_info = get_edge_voice_info(voice_name)
                    edge_voice_id = edge_voice_info["id"]
                    rate = parse_rate_for_ssml(edge_voice_info.get("rate"))
                    pitch = parse_pitch_for_ssml(edge_voice_info.get("pitch"))
                    
                    rate_info = f", rate={rate}" if rate else ""
                    pitch_info = f", pitch={pitch}" if pitch else ""
                    print(f"🎙️ 생성 중 [{file_id}] (Edge TTS, voice='{voice_name}' -> '{edge_voice_id}'{rate_info}{pitch_info}): {script[:20]}...")
                    success, duration = generate_edge_tts_audio(script, edge_voice_id, save_path, rate, pitch)
                else:
                    # Azure TTS 사용
                    azure_voice_info = get_azure_voice_info(voice_name)  # voices_azure.txt에서 정보 가져오기
                    azure_voice_id = azure_voice_info["id"]
                    style = azure_voice_info.get("style")  # 스타일 정보 추가
                    rate = parse_rate_for_ssml(azure_voice_info.get("rate"))
                    pitch = parse_pitch_for_ssml(azure_voice_info.get("pitch"))
                    
                    style_info = f", style={style}" if style and style != "General" else ""
                    rate_info = f", rate={rate}" if rate else ""
                    pitch_info = f", pitch={pitch}" if pitch else ""
                    print(f"🎙️ 생성 중 [{file_id}] (Azure TTS, voice='{voice_name}' -> '{azure_voice_id}'{style_info}{rate_info}{pitch_info}): {script[:20]}...")
                    success, duration = generate_azure_tts_audio(script, azure_voice_id, save_path, rate, pitch, style)
                    
                    # Azure TTS 실패 시 Edge TTS로 폴백 (한 번만 시도)
                    if not success:
                        print(f"   ⚠️ Azure TTS 실패, Edge TTS로 자동 전환합니다.")
                        # 실패한 Azure 파일 삭제 시도 (실패해도 계속 진행)
                        if os.path.exists(save_path):
                            try:
                                time.sleep(0.2)
                                os.remove(save_path)
                            except:
                                pass  # 삭제 실패해도 계속 진행
                        
                        edge_voice_info = get_edge_voice_info(voice_name)
                        edge_voice_id = edge_voice_info["id"]
                        rate = parse_rate_for_ssml(edge_voice_info.get("rate"))
                        pitch = parse_pitch_for_ssml(edge_voice_info.get("pitch"))
                        
                        rate_info = f", rate={rate}" if rate else ""
                        pitch_info = f", pitch={pitch}" if pitch else ""
                        print(f"🎙️ 생성 중 [{file_id}] (Edge TTS, voice='{voice_name}' -> '{edge_voice_id}'{rate_info}{pitch_info}): {script[:20]}...")
                        success, duration = generate_edge_tts_audio(script, edge_voice_id, save_path, rate, pitch)
                
            elif voice_tool == "elevenlabs":
                # ElevenLabs 사용
                if not km.keys:
                    print(f"   💥 [Row {i+2}] ElevenLabs 키가 없어 이 행은 스킵합니다.")
                    continue

                # voices_elevenlabs.txt에서 정보 가져오기
                elevenlabs_voice_info = get_elevenlabs_voice_info(voice_name)
                voice_id = elevenlabs_voice_info.get("id")
                model_id = elevenlabs_voice_info.get("model", "eleven_multilingual_v2")
                rate = parse_rate_for_ssml(elevenlabs_voice_info.get("rate"))
                pitch = parse_pitch_for_ssml(elevenlabs_voice_info.get("pitch"))
                
                if not voice_id:
                    # 기존 방식으로도 시도 (04_Asset/Voice 폴더)
                    if voice_name:
                        voice_id = get_voice_id_by_name(voice_name)
                        if not voice_id:
                            print(f"   ⚠️ [Row {i+2}] '{voice_name}' 성우를 찾지 못해 이 행은 스킵합니다.")
                            continue
                    else:
                        print(f"   💥 [Row {i+2}] ElevenLabs 사용 시 voice 열이 비어있어 이 행은 스킵합니다.")
                        continue

                rate_info = f", rate={rate}" if rate else ""
                pitch_info = f", pitch={pitch}" if pitch else ""
                print(f"🎙️ 생성 중 [{file_id}] (ElevenLabs, voice='{voice_name}' -> '{voice_id}'{rate_info}{pitch_info}): {script[:20]}...")
                success, duration = generate_elevenlabs_audio(script, voice_id, save_path, km, model_id, rate, pitch)
                
            else:
                # voice_tool이 비어있거나 잘못된 경우: Edge TTS 기본 목소리 사용
                edge_voice_info = get_edge_voice_info(voice_name)
                edge_voice_id = edge_voice_info["id"]
                rate = parse_rate_for_ssml(edge_voice_info.get("rate"))
                pitch = parse_pitch_for_ssml(edge_voice_info.get("pitch"))
                
                rate_info = f", rate={rate}" if rate else ""
                pitch_info = f", pitch={pitch}" if pitch else ""
                print(f"🎙️ 생성 중 [{file_id}] (Edge TTS 기본, voice='{voice_name}' -> '{edge_voice_id}'{rate_info}{pitch_info}): {script[:20]}...")
                success, duration = generate_edge_tts_audio(script, edge_voice_id, save_path, rate, pitch)
        
        if success:
            print(f"   ✅ 성공 (길이: {duration:.2f}초)")
            success_count += 1
            
            # D열에 duration(음성 길이) 자동 채우기 (인덱스 3 = D열)
            if duration > 0:
                duration_updates.append({
                    "row": i + 2,  # 1-based + 헤더
                    "col": 4,  # D열 (1-based, 인덱스 3이므로 4)
                    "value": f"{duration:.2f}"
                })
        else:
            print(f"   💥 실패")
            # ElevenLabs의 경우 키가 다 떨어지면 종료
            if voice_tool == "elevenlabs" and not km.keys: 
                break
    
    # D열 일괄 업데이트
    if duration_updates:
        print(f"\n📝 D열(음성 길이, duration) 자동 채우기 중... ({len(duration_updates)}개)")
        try:
            cells_to_update = []
            for update in duration_updates:
                cells_to_update.append(
                    gspread.Cell(update["row"], update["col"], update["value"])
                )
            selected_sheet.update_cells(cells_to_update)
            print(f"✅ D열 업데이트 완료!")
        except Exception as e:
            print(f"⚠️ D열 업데이트 실패: {e}")
            
    print(f"\n🎉 작업 완료! (생성된 파일: {success_count}개)")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n\n❌ 예상치 못한 오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()
    finally:
        pass