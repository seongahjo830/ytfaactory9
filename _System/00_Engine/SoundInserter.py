import os
import glob
import subprocess
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 설정 및 경로 정의
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)  # _System 루트
PROJECT_ROOT = os.path.dirname(BASE_DIR)  # YtFactory9 루트
BASE_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "02_Output")
ASSET_DIR = os.path.join(BASE_DIR, "04_Co_Asset")
SOUND_DIR = os.path.join(ASSET_DIR, "Sound")
BGM_DIR = os.path.join(ASSET_DIR, "BGM")

# [필수 자산 경로] - 프로젝트 루트에서 찾기
FFMPEG_CMD = os.path.join(PROJECT_ROOT, "ffmpeg.exe")
FFPROBE_CMD = os.path.join(PROJECT_ROOT, "ffprobe.exe") 

# service_account.json 탐색 (YTFactory9 기준)
_JSON_CANDIDATES = [
    os.path.join(PROJECT_ROOT, "_System", "02_Key", "service_account.json"),
    os.path.join(PROJECT_ROOT, "service_account.json"),
    os.path.join(CURRENT_DIR, "service_account.json"),
    os.path.join(BASE_DIR, "service_account.json"),
]
JSON_KEY_FILE = _JSON_CANDIDATES[0]
for _p in _JSON_CANDIDATES:
    if os.path.exists(_p):
        JSON_KEY_FILE = _p
        break

# Sheet URL 파일 탐색
_SHEET_URL_CANDIDATES = [
    os.path.join(PROJECT_ROOT, "_System", "04_Co_Asset", "YtFactory9_SheetURL.txt"),
    os.path.join(PROJECT_ROOT, "_System", "00_Engine", "YtFactory9_URL.txt"),
    os.path.join(CURRENT_DIR, "Sheet_URL.txt"),
]
SHEET_URL_FILE = _SHEET_URL_CANDIDATES[0]
for _p in _SHEET_URL_CANDIDATES:
    if os.path.exists(_p):
        SHEET_URL_FILE = _p
        break

# 워크플로우별 고유 auto_sheet 파일 (환경변수 우선)
ENV_AUTO_SHEET = os.environ.get("YTF_AUTO_SHEET_FILE")
if ENV_AUTO_SHEET and ENV_AUTO_SHEET.strip():
    AUTO_SHEET_FILE = ENV_AUTO_SHEET.strip()
else:
    AUTO_SHEET_FILE = os.path.join(CURRENT_DIR, "_auto_sheet.txt")

# ==========================================
# 2. 유틸리티 함수
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

def find_sound_file(sound_name):
    """
    효과음/BGM 파일 찾기
    1차: 04_Co_Asset/Sound 폴더에서 검색
    2차: 04_Co_Asset/BGM 폴더에서 검색 (배경음악)
    sound_name: K열에 적힌 파일 이름 (확장자 포함/미포함 모두 지원)
    반환: (file_path, is_bgm) 튜플 또는 (None, False)
    """
    if not sound_name or not sound_name.strip():
        return None, False
    
    # 공백 제거 및 정규화 (보이지 않는 문자 제거)
    sound_name = sound_name.strip().replace('\ufeff', '').replace('\u200b', '')
    
    # 확장자가 없으면 .mp3, .wav 등을 시도
    if not os.path.splitext(sound_name)[1]:
        candidates = [f"{sound_name}.mp3", f"{sound_name}.wav", f"{sound_name}.m4a"]
    else:
        candidates = [sound_name]
    
    # 1차: Sound 폴더에서 정확한 매칭 시도
    for candidate in candidates:
        sound_path = os.path.join(SOUND_DIR, candidate)
        if os.path.exists(sound_path):
            return sound_path, False
    
    # Sound 폴더에서 대소문자 무시 검색 (한글 포함)
    all_files = []
    for ext in ['*.mp3', '*.wav', '*.m4a', '*.ogg']:
        all_files.extend(glob.glob(os.path.join(SOUND_DIR, ext)))
        all_files.extend(glob.glob(os.path.join(SOUND_DIR, ext.upper())))
    
    # 시트에서 읽은 이름 정규화 (공백, 특수문자 제거)
    sound_name_normalized = sound_name.replace(' ', '').replace('　', '').replace('\ufeff', '').replace('\u200b', '')  # 일반 공백, 전각 공백, BOM, 제로 너비 공백 제거
    sound_name_base = os.path.splitext(sound_name_normalized)[0]
    
    for file_path in all_files:
        file_name = os.path.basename(file_path)
        file_name_base = os.path.splitext(file_name)[0]
        
        # 정확한 매칭 (대소문자 무시)
        if sound_name_base.lower() == file_name_base.lower():
            return file_path, False
        
        # 공백 제거 후 매칭 (한글 파일명의 공백 처리)
        file_name_no_space = file_name_base.replace(' ', '').replace('　', '')
        if sound_name_base.lower() == file_name_no_space.lower():
            return file_path, False
        
        # 부분 매칭: 시트 이름이 파일명에 포함되거나 파일명이 시트 이름에 포함되는 경우
        if sound_name_base.lower() in file_name_base.lower() or file_name_base.lower() in sound_name_base.lower():
            # 숫자로 시작하는 경우 숫자 부분도 일치하는지 확인 (예: "2.상큼뿅" vs "2.상큼뿅.mp3")
            if sound_name_base and file_name_base:
                # 숫자 부분 추출
                sound_num = ''.join(filter(str.isdigit, sound_name_base))
                file_num = ''.join(filter(str.isdigit, file_name_base))
                if sound_num and file_num and sound_num == file_num:
                    return file_path, False
    
    # 2차: BGM 폴더에서 검색 (배경음악)
    for candidate in candidates:
        bgm_path = os.path.join(BGM_DIR, candidate)
        if os.path.exists(bgm_path):
            return bgm_path, True
    
    # BGM 폴더에서 대소문자 무시 검색
    bgm_files = []
    for ext in ['*.mp3', '*.wav', '*.m4a', '*.ogg']:
        bgm_files.extend(glob.glob(os.path.join(BGM_DIR, ext)))
        bgm_files.extend(glob.glob(os.path.join(BGM_DIR, ext.upper())))
    
    for file_path in bgm_files:
        file_name = os.path.basename(file_path)
        file_name_base = os.path.splitext(file_name)[0]
        
        # 정확한 매칭 (대소문자 무시)
        if sound_name_base.lower() == file_name_base.lower():
            return file_path, True
        
        # 공백 제거 후 매칭
        file_name_no_space = file_name_base.replace(' ', '').replace('　', '')
        if sound_name_base.lower() == file_name_no_space.lower():
            return file_path, True
        
        # 부분 매칭: 시트 이름이 파일명에 포함되거나 파일명이 시트 이름에 포함되는 경우
        if sound_name_base.lower() in file_name_base.lower() or file_name_base.lower() in sound_name_base.lower():
            # 숫자로 시작하는 경우 숫자 부분도 일치하는지 확인
            if sound_name_base and file_name_base:
                sound_num = ''.join(filter(str.isdigit, sound_name_base))
                file_num = ''.join(filter(str.isdigit, file_name_base))
                if sound_num and file_num and sound_num == file_num:
                    return file_path, True
    
    return None, False

def parse_duration(duration_str):
    """
    D열의 duration 문자열을 초 단위(float)로 변환
    지원 형식: "10.5", "10.5초", "0:10", "0:10.5", "10"
    """
    if not duration_str or not duration_str.strip():
        return None
    
    duration_str = duration_str.strip()
    
    # "초" 제거
    duration_str = duration_str.replace("초", "").strip()
    
    # 분:초 형식 (예: "1:30", "0:10.5")
    if ":" in duration_str:
        parts = duration_str.split(":")
        if len(parts) == 2:
            try:
                minutes = float(parts[0])
                seconds = float(parts[1])
                return minutes * 60 + seconds
            except:
                return None
    
    # 초 단위 숫자 (예: "10.5", "10")
    try:
        return float(duration_str)
    except:
        return None

def get_clip_timings(rows, voice_dir, sound_col_idx):
    """
    각 클립의 시작 시간과 길이를 계산
    - G열(duration)이 있으면 우선 사용 (더 정확함) - 인덱스 6 (0-based)
    - 없으면 Voice 파일 길이 측정
    - sound_col_idx: 헤더에서 'sound' 라는 이름을 가진 열 인덱스
    반환: [(row_id, start_time, duration, sound_file), ...]
    """
    timings = []
    current_time = 0.0
    
    for i, row in enumerate(rows):
        if len(row) < 3: continue
        
        row_id = row[0].strip()        # A열: ID
        if not row_id: continue
        
        # G열: Duration (인덱스 6, 0-based) - 우선 사용
        duration = None
        used_g_column = False
        if len(row) > 6 and row[6].strip():
            duration = parse_duration(row[6].strip())
            if duration is not None and duration > 0:
                used_g_column = True  # G열 값이 유효하면 사용됨
        
        # G열이 없거나 잘못된 경우: Voice 파일 길이 측정 (Fallback)
        if duration is None or duration <= 0:
            audio_path = os.path.join(voice_dir, f"{row_id}.mp3")
            if os.path.exists(audio_path):
                duration = get_audio_duration(audio_path)
            else:
                continue  # Voice 파일도 없으면 스킵
        
        if duration <= 0:
            continue
        
        # 효과음 열: 헤더에서 'sound' 라는 이름으로 찾은 열 인덱스
        sound_name = row[sound_col_idx].strip() if len(row) > sound_col_idx else ""
        sound_file, is_bgm = find_sound_file(sound_name) if sound_name else (None, False)
        
        timings.append({
            "id": row_id,
            "start_time": current_time,
            "duration": duration,
            "sound_file": sound_file,
            "sound_name": sound_name,
            "is_bgm": is_bgm,  # BGM 여부
            "used_g_column": used_g_column  # G열 사용 여부
        })
        
        # 다음 클립 시작 시간 = 현재 시간 + 현재 클립 길이
        current_time += duration
    
    return timings

def create_sound_mix_command(final_video, timings, output_path, sound_volume=0.1, bgm_volume=0.3):
    """
    ffmpeg 명령어 생성: 최종 영상에 효과음/BGM 오버레이
    - 각 효과음은 해당 클립의 시작 지점에 삽입
    - BGM은 15초 재생, 마지막 6초 페이드아웃, 30% 볼륨
    - 메인 오디오와 효과음/BGM을 믹싱
    - sound_volume: 효과음 볼륨 조절 (0.0 ~ 1.0, 기본 0.1 = 10%)
    - bgm_volume: BGM 볼륨 조절 (0.0 ~ 1.0, 기본 0.3 = 30%)
    """
    if not timings:
        # 효과음이 없으면 그냥 복사
        cmd = [FFMPEG_CMD, "-y", "-i", final_video, "-c", "copy", output_path]
        return cmd
    
    # 효과음/BGM이 있는 경우: 필터 컴플렉스 사용
    filter_parts = []
    input_args = ["-i", final_video]
    
    # 각 효과음/BGM을 입력으로 추가하고 필터 구성
    sound_inputs = []
    for idx, timing in enumerate(timings):
        if timing["sound_file"]:
            input_idx = len(input_args) // 2  # 현재 입력 인덱스
            input_args.extend(["-i", timing["sound_file"]])
            start_time = timing["start_time"]
            is_bgm = timing.get("is_bgm", False)
            
            # adelay는 밀리초 단위로 작동 (스테레오: 채널1|채널2)
            delay_ms = int(start_time * 1000)  # 초를 밀리초로 변환
            
            if is_bgm:
                # BGM 처리: 15초 재생, 마지막 6초 페이드아웃, 30% 볼륨
                # atrim: 0부터 15초까지 자르기
                # afade: 마지막 6초 페이드아웃 (9초부터 15초까지)
                # volume: 30% 볼륨
                # adelay: 시작 시간 딜레이 (밀리초 단위, 스테레오 지원)
                filter_parts.append(
                    f"[{input_idx}:a]atrim=0:15,afade=t=out:st=9:d=6,volume={bgm_volume},adelay={delay_ms}|{delay_ms}[s{idx}]"
                )
            else:
                # 효과음 처리: 볼륨 조절 + 딜레이 (밀리초 단위, 스테레오 지원)
                filter_parts.append(
                    f"[{input_idx}:a]volume={sound_volume},adelay={delay_ms}|{delay_ms}[s{idx}]"
                )
            
            sound_inputs.append(f"[s{idx}]")
    
    if sound_inputs:
        # 모든 효과음/BGM을 메인 오디오와 믹싱
        # amix: 여러 오디오 스트림을 하나로 믹싱
        # duration=longest: 가장 긴 오디오만큼 길이 유지
        # normalize=0: 자동 정규화 비활성화 (메인 오디오 볼륨 유지)
        # dropout_transition=2: 효과음이 끝날 때 페이드아웃
        mix_inputs = "[0:a]" + "".join(sound_inputs)
        filter_complex = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={len(sound_inputs)+1}:duration=longest:dropout_transition=2:normalize=0[aout]"
        
        cmd = [
            FFMPEG_CMD, "-y",
            *input_args,
            "-filter_complex", filter_complex,
            "-map", "0:v",  # 비디오는 원본 사용
            "-map", "[aout]",  # 믹싱된 오디오
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",  # 비디오 재인코딩 (호환성 향상)
            "-c:a", "aac", "-b:a", "192k",  # 오디오는 인코딩
            output_path
        ]
    else:
        # 효과음이 없으면 복사
        cmd = [FFMPEG_CMD, "-y", "-i", final_video, "-c", "copy", output_path]
    
    return cmd

# ==========================================
# 3. 메인 로직
# ==========================================
def main():
    print("\n🔊 [SoundInserter] 효과음 자동 삽입기 시작")
    print("=" * 60)

    # 🛑 [Check 0] 필수 실행 파일 확인
    if not os.path.exists(FFMPEG_CMD) or not os.path.exists(FFPROBE_CMD):
        print("🚨 [오류] ffmpeg.exe 또는 ffprobe.exe가 없습니다.")
        print(f"👉 경로: {PROJECT_ROOT}")
        input("엔터 키를 누르면 종료합니다...")
        return 1

    # 🛑 [Check 1] 효과음/BGM 폴더 확인
    if not os.path.exists(SOUND_DIR):
        print(f"⚠️ 효과음 폴더가 없습니다. 생성합니다: {SOUND_DIR}")
        os.makedirs(SOUND_DIR)
    
    if not os.path.exists(BGM_DIR):
        print(f"⚠️ BGM 폴더가 없습니다. 생성합니다: {BGM_DIR}")
        os.makedirs(BGM_DIR)

    # 1. 구글 시트 연결
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        doc = load_spreadsheet(client)
    except Exception as e:
        print(f"❌ 시트 접속 실패: {e}")
        input("엔터 키를 누르면 종료합니다...")
        return 1

    # 2. 시트 선택
    all_worksheets = doc.worksheets()
    go_sheets = [ws for ws in all_worksheets if "go" in ws.title.lower()]

    if not go_sheets:
        print("❌ 'go' 시트가 없습니다.")
        input("엔터 키를 누르면 종료합니다...")
        return 1

    print(" 🎬 작업할 시트를 선택하세요")
    for idx, ws in enumerate(go_sheets):
        print(f" [{idx+1}] {ws.title}")
    
    selected_sheet = None
    while selected_sheet is None:
        try:
            choice = input("\n번호 입력 >> ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(go_sheets):
                selected_sheet = go_sheets[idx]
        except: pass

    SHEET_NAME = selected_sheet.title
    print(f"✅ 선택된 시트: '{SHEET_NAME}'")

    # 시트 이름에서 채널명 추출 (예: Ch03_5go -> Ch03)
    sheet_title = SHEET_NAME
    channel_match = re.search(r"Ch\d+", sheet_title)
    if not channel_match:
        print(f"❌ 시트 이름에서 채널명을 추출할 수 없습니다: {sheet_title}")
        input("엔터 키를 누르면 종료합니다...")
        return 1
    channel_name = channel_match.group(0)

    # 📂 폴더 경로 설정 (YtFactory9 표준 구조)
    ROOT_OUTPUT = os.path.join(PROJECT_ROOT, channel_name, "03_Output", SHEET_NAME)
    MERGY_DIR = os.path.join(ROOT_OUTPUT, "Mergy")
    VOICE_DIR = os.path.join(ROOT_OUTPUT, "Voice")
    
    # 최종 영상 경로 확인 (Mergy 폴더에서 가져오기)
    final_video_subver = os.path.join(MERGY_DIR, "Final_SubVer_Complete.mp4")
    final_video_normal = os.path.join(MERGY_DIR, "Final_Complete.mp4")
    
    print(f"\n📂 경로 확인: {MERGY_DIR}")
    
    if os.path.exists(final_video_subver):
        final_video = final_video_subver
        print(f"✅ Mergy_SubVer 결과물 사용: {os.path.basename(final_video)}")
    elif os.path.exists(final_video_normal):
        final_video = final_video_normal
        print(f"✅ Mergy 결과물 사용: {os.path.basename(final_video)}")
    else:
        print(f"❌ 최종 영상이 없습니다.")
        print(f"👉 찾는 경로: {MERGY_DIR}")
        print(f"👉 다음 중 하나를 먼저 실행해주세요:")
        print(f"   - 05__Mergy.bat (기본 자막)")
        print(f"   - 05__Mergy_SubVer.bat (스타일 변형 자막)")
        input("엔터 키를 누르면 종료합니다...")
        return 1
    
    # 원본 영상은 절대 삭제하지 않음 (보호)
    print(f"🔒 원본 영상 보호: {os.path.basename(final_video)} (삭제되지 않습니다)")

    # 데이터 로드 (헤더 + 본문)
    all_values = selected_sheet.get_all_values()
    if not all_values:
        print("❌ 시트가 비어 있습니다.")
        input("엔터 키를 누르면 종료합니다...")
        return 1

    header = all_values[0]
    rows = all_values[1:]  # 헤더 제외

    # 'sound' 열 인덱스 탐색 (대소문자 무시)
    sound_col_idx = None
    for idx, name in enumerate(header):
        if str(name).strip().lower() == "sound":
            sound_col_idx = idx
            break

    if sound_col_idx is None:
        print("❌ 헤더에서 'sound' 열을 찾을 수 없습니다. (예: K열에 'sound' 라고 적어주세요)")
        print(f"👉 현재 헤더: {header}")
        input("엔터 키를 누르면 종료합니다...")
        return 1

    print(f"\n📊 [타임스탬프 계산] 각 클립의 시작 시간 계산 중... (sound 열 인덱스: {sound_col_idx})")
    timings = get_clip_timings(rows, VOICE_DIR, sound_col_idx)
    
    if not timings:
        print("❌ 처리할 클립이 없습니다.")
        input("엔터 키를 누르면 종료합니다...")
        return 1
    
    # 효과음/BGM 통계
    sound_count = sum(1 for t in timings if t["sound_file"] and not t.get("is_bgm", False))
    bgm_count = sum(1 for t in timings if t["sound_file"] and t.get("is_bgm", False))
    g_column_count = sum(1 for t in timings if t.get("used_g_column", False))
    print(f"✅ 총 {len(timings)}개 클립 중 {sound_count}개 효과음, {bgm_count}개 BGM이 설정되어 있습니다.")
    if g_column_count > 0:
        print(f"📊 G열(duration) 사용: {g_column_count}개 클립 (더 정확한 타임스탬프)")
    
    # 디버깅: K열 값 확인 및 실제 파일 목록 출력
    print(f"\n🔍 [디버깅] K열 효과음/BGM 파일명 확인:")
    
    # 실제 Sound 폴더의 파일 목록 출력
    if os.path.exists(SOUND_DIR):
        sound_files = []
        for ext in ['*.mp3', '*.wav', '*.m4a', '*.ogg']:
            sound_files.extend(glob.glob(os.path.join(SOUND_DIR, ext)))
        if sound_files:
            print(f"📁 Sound 폴더에 있는 파일 목록:")
            for sf in sorted(sound_files)[:10]:
                print(f"   - {os.path.basename(sf)}")
            if len(sound_files) > 10:
                print(f"   ... (총 {len(sound_files)}개 파일)")
    
    for t in timings[:10]:  # 처음 10개만 출력
        if t["sound_file"]:
            file_type = "🎵 BGM" if t.get("is_bgm", False) else "🔊 효과음"
            print(f"  [{t['id']}] K열: '{t['sound_name']}' → ✅ {file_type}")
            print(f"       → 파일: {os.path.basename(t['sound_file'])}")
        else:
            # 더 자세한 디버깅 정보 출력
            sound_name_repr = repr(t['sound_name']) if t['sound_name'] else "''"
            print(f"  [{t['id']}] K열: '{t['sound_name']}' → ❌ 없음 (repr: {sound_name_repr})")
    if len(timings) > 10:
        print(f"  ... (나머지 {len(timings) - 10}개 생략)")
    
    if sound_count == 0 and bgm_count == 0:
        print("\n⚠️ 효과음/BGM이 설정된 클립이 없습니다. K열을 확인해주세요.")
        print("👉 효과음/BGM 없이 진행합니다.")
    
    # 효과음/BGM 파일 확인 (경고만 출력, 자동 진행)
    missing_sounds = []
    for timing in timings:
        if timing["sound_name"] and not timing["sound_file"]:
            missing_sounds.append(f"  - {timing['id']}: '{timing['sound_name']}' (K열)")
    
    if missing_sounds:
        print("\n⚠️ [경고] 다음 효과음/BGM 파일을 찾을 수 없습니다 (해당 파일은 건너뜁니다):")
        for msg in missing_sounds:
            print(msg)
        print(f"👉 효과음 폴더 위치: {SOUND_DIR}")
        print(f"👉 BGM 폴더 위치: {BGM_DIR}")
        print("👉 계속 진행합니다...\n")
    
    # 4. 효과음 삽입 실행
    print("\n" + "="*60)
    print("🎵 [효과음 삽입] 최종 영상에 효과음 믹싱 중...")
    print("="*60)
    
    output_video = os.path.join(MERGY_DIR, "Final_With_Sound.mp4")
    
    # 기존 파일이 있으면 백업
    if os.path.exists(output_video):
        backup_path = os.path.join(MERGY_DIR, "Final_With_Sound_backup.mp4")
        if os.path.exists(backup_path):
            os.remove(backup_path)
        os.rename(output_video, backup_path)
        print(f"📦 기존 파일 백업: {os.path.basename(backup_path)}")
    
    # 효과음/BGM이 있는 타임스탬프만 필터링
    sound_timings = [t for t in timings if t["sound_file"]]
    
    if sound_timings:
        print(f"\n🔊 효과음/BGM 삽입 정보:")
        for timing in sound_timings:
            sound_duration = get_audio_duration(timing["sound_file"])
            file_type = "🎵 BGM" if timing.get("is_bgm", False) else "🔊 효과음"
            if timing.get("is_bgm", False):
                print(f"  [{timing['id']}] {timing['start_time']:.2f}s 시작 - {file_type} {os.path.basename(timing['sound_file'])} (15초 재생, 마지막 6초 페이드아웃, 30% 볼륨)")
            else:
                print(f"  [{timing['id']}] {timing['start_time']:.2f}s 시작 - {file_type} {os.path.basename(timing['sound_file'])} ({sound_duration:.2f}s, 8% 볼륨)")
        print(f"\n✅ 총 {len(sound_timings)}개의 효과음/BGM을 믹싱합니다.")
    else:
        print("\n⚠️ 효과음/BGM이 설정된 클립이 없어 효과음 없이 복사만 진행합니다.")
        print("   K열에 효과음/BGM 파일명이 있는지 확인해주세요.")
    
    # 효과음/BGM 볼륨 설정 (0.0 ~ 1.0)
    SOUND_VOLUME = 0.08  # 효과음 볼륨 (8%)
    BGM_VOLUME = 0.3     # BGM 볼륨 (30%)
    
    # 명령어 생성 및 실행
    cmd = create_sound_mix_command(final_video, sound_timings, output_video, SOUND_VOLUME, BGM_VOLUME)
    
    # 디버깅: 명령어 출력 (필터 컴플렉스 확인용)
    if sound_timings:
        print(f"\n🔧 생성된 필터 컴플렉스:")
        for arg in cmd:
            if arg == "-filter_complex":
                idx = cmd.index(arg)
                if idx + 1 < len(cmd):
                    print(f"   {cmd[idx + 1]}")
                break
    
    print("\n⚙️ ffmpeg 실행 중... (시간이 걸릴 수 있습니다)")
    try:
        # stderr를 출력하여 디버깅 정보 확인 가능하게
        subprocess.run(cmd, check=True)
        print(f"\n🎉 [성공] 효과음이 삽입된 영상 생성 완료!")
        print(f"📁 파일: {os.path.basename(output_video)}")
        print(f"📂 위치: {MERGY_DIR}")
        
        # 결과 폴더 열기
        os.startfile(MERGY_DIR)
        
    except subprocess.CalledProcessError as e:
        print(f"\n💥 [실패] 효과음 삽입 중 오류 발생")
        print(f"오류 코드: {e.returncode}")
        print("\n👉 디버깅 정보:")
        print(f"  - 최종 영상: {final_video}")
        print(f"  - 효과음 개수: {len(sound_timings)}")
        input("\n엔터 키를 누르면 종료합니다...")
        return 1
    except Exception as e:
        print(f"\n💥 [오류] {e}")
        input("엔터 키를 누르면 종료합니다...")
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    exit_code = main()
    sys.exit(exit_code if exit_code is not None else 0)
