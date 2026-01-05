import os
import glob
import subprocess
import time
import random
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 설정 및 경로 정의 (YTFactory9 구조 대응)
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))           # ...\_System\00_Engine
SYSTEM_DIR = os.path.dirname(CURRENT_DIR)                          # ...\_System
PROJECT_ROOT = os.path.dirname(SYSTEM_DIR)                         # ...\YTFACTORY9

# 출력 루트: 기본은 PROJECT_ROOT\02_Output, 있으면 환경변수 우선
ENV_OUTPUT_ROOT = os.environ.get("YTF_OUTPUT_ROOT")
if ENV_OUTPUT_ROOT and ENV_OUTPUT_ROOT.strip():
    BASE_OUTPUT_DIR = ENV_OUTPUT_ROOT.strip()
else:
    BASE_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "02_Output")

# service_account.json 탐색 (YTFactory9 기준)
_JSON_CANDIDATES = [
    os.path.join(PROJECT_ROOT, "_System", "02_Key", "service_account.json"),
    os.path.join(PROJECT_ROOT, "service_account.json"),
    os.path.join(CURRENT_DIR, "service_account.json"),
    os.path.join(SYSTEM_DIR, "service_account.json"),
]
JSON_KEY_FILE = _JSON_CANDIDATES[0]
for _p in _JSON_CANDIDATES:
    if os.path.exists(_p):
        JSON_KEY_FILE = _p
        break

# Sheet URL 파일 (YTFactory9 자산 폴더 우선)
_SHEET_URL_CANDIDATES = [
    os.path.join(PROJECT_ROOT, "_System", "04_Co_Asset", "YtFactory9_SheetURL.txt"),
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


def get_ffmpeg_path():
    """
    FFmpeg 실행 파일 위치를 탐색 (YTFactory9 기준).
    1) PROJECT_ROOT\ffmpeg.exe
    2) PATH 내 ffmpeg
    """
    candidates = [
        os.path.join(PROJECT_ROOT, "ffmpeg.exe"),
        "ffmpeg",
    ]

    selected = None
    for path in candidates:
        if path == "ffmpeg":
            # 실제 실행 가능 여부는 ffmpeg 호출 시점에 다시 한 번 체크
            selected = selected or "ffmpeg"
            continue
        if os.path.exists(path):
            selected = path
            break

    # exe가 있는 디렉터리를 PATH에 추가
    if selected and selected != "ffmpeg":
        ff_dir = os.path.dirname(selected)
        if ff_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + ff_dir

    return selected


FFMPEG_CMD = get_ffmpeg_path()

# ==========================================
# 2. 켄번 효과 엔진 (Ultimate Stabilizer)
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


def create_zoom_video(image_path):
    base_name = os.path.splitext(image_path)[0]
    output_path = f"{base_name}.mp4"
    
    if os.path.exists(output_path):
        print(f"⏩ [Skip] 이미 변환됨: {os.path.basename(output_path)}")
        return

    # 🎲 랜덤 효과 뽑기
    effects = ["zoom_in", "pan_right", "pan_left", "pan_up", "pan_down"]
    choice = random.choice(effects)
    
    effect_name = ""
    zoompan_cmd = ""
    
    # 🎬 [효과 강도 & 안정화 설정] - 켄번 효과 명확하게 + 흔들림 제거
    speed_factor = 0.0004   # 적절한 속도 (효과가 보이도록)
    pan_zoom_level = 1.10   # 적절한 줌 레벨 (켄번 효과 명확)
    zoom_max = 1.4          # 줌인 최대값 (명확한 효과)
    
    # 정수 픽셀 정렬을 위한 계산식 (흔들림 완전 제거)
    # round() 함수로 정수 픽셀로 강제 정렬하여 서브픽셀 움직임 제거

    if choice == "zoom_in":
        effect_name = "🔍 줌 인"
        # 정수 픽셀 정렬된 명확한 줌인 효과
        zoompan_cmd = f"z='min(zoom+{speed_factor},{zoom_max})':x='round(iw/2-(iw/zoom/2))':y='round(ih/2-(ih/zoom/2))'"
    elif choice == "pan_right":
        effect_name = "➡️ 팬 라이트"
        # 정수 픽셀 정렬된 명확한 팬 효과
        zoompan_cmd = f"z={pan_zoom_level}:x='round((iw-iw/zoom)*(on/duration))':y='round((ih-ih/zoom)/2)'"
    elif choice == "pan_left":
        effect_name = "⬅️ 팬 레프트"
        # 정수 픽셀 정렬된 명확한 팬 효과 (역방향)
        zoompan_cmd = f"z={pan_zoom_level}:x='round((iw-iw/zoom)*(1-on/duration))':y='round((ih-ih/zoom)/2)'"
    elif choice == "pan_up":
        effect_name = "⬆️ 팬 업"
        # 정수 픽셀 정렬된 명확한 팬 효과 (역방향)
        zoompan_cmd = f"z={pan_zoom_level}:x='round((iw-iw/zoom)/2)':y='round((ih-ih/zoom)*(1-on/duration))'"
    elif choice == "pan_down":
        effect_name = "⬇️ 팬 다운"
        # 정수 픽셀 정렬된 명확한 팬 효과
        zoompan_cmd = f"z={pan_zoom_level}:x='round((iw-iw/zoom)/2)':y='round((ih-ih/zoom)*(on/duration))'"

    print(f"🎬 변환 중 [{effect_name}]: {os.path.basename(image_path)}")

    # ⚡ [Ultimate Stabilizer Filter Chain - Anti-Shake Pro]
    # 원리: 초고해상도(4K)에서 줌팬 계산 -> 정수 픽셀 정렬 -> 다운스케일
    #       이렇게 하면 서브픽셀 움직임이 완전히 제거되어 흔들림이 사라짐
    
    vf_filter = (
        "scale=3840:2160:force_original_aspect_ratio=increase," # 1. 4K로 업스케일 (정밀도 향상)
        "crop=3840:2160,"                                       # 2. 4K 16:9 강제 맞춤
        "setsar=1,"                                             # 3. 픽셀 비율 1:1
        f"zoompan={zoompan_cmd}:d=300:s=3840x2160:fps=30,"      # 4. 4K 해상도에서 줌 연산 (정수 픽셀 정렬로 흔들림 제거)
        "scale=1280:720:flags=lanczos:sws_dither=none"          # 5. 최종 출력 (다운스케일, 디더링 제거로 더 부드럽게)
    )

    try:
        if not FFMPEG_CMD:
            print(f"\n🚨 [오류] ffmpeg를 찾을 수 없습니다!")
            return False

        cmd = [
            FFMPEG_CMD, "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", vf_filter,
            "-t", "10",             # 10초 길이 생성
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "faster",
            "-threads", "0",
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"   ❌ 실패! (FFmpeg 에러 코드: {result.returncode})")
            if result.stderr:
                # 에러 메시지의 마지막 몇 줄만 출력
                error_lines = result.stderr.strip().split('\n')
                print(f"   에러 내용:")
                for line in error_lines[-5:]:
                    if line.strip():
                        print(f"   {line}")
            return False
        print(f"   ✅ 성공!")
        return True
    except Exception as e:
        print(f"   ❌ 실패! (원인: {e})")
        return False

# ==========================================
# 3. 메인 실행
# ==========================================
def main():
    print(f"🚀 EffectMaker v1.5 (Ultimate Stabilizer - Anti-Shake Pro)")
    
    if not FFMPEG_CMD:
        print("🚨 ffmpeg.exe 를 찾을 수 없습니다. (PROJECT_ROOT 또는 PATH 확인)")
        return

    # 1. 시트 연결
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        doc = load_spreadsheet(client)
    except Exception as e:
        print(f"❌ 시트 접속 실패: {e}"); return

    # 2. 시트 선택
    all_worksheets = doc.worksheets()
    go_sheets = [ws for ws in all_worksheets if "go" in ws.title.lower()]

    if not go_sheets:
        print("❌ 'go' 시트가 없습니다."); return

    print("\n" + "="*40)
    print(" 🎬 [EffectMaker] 작업할 시트를 선택하세요")
    print("="*40)
    
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

    print(f"✅ 선택된 시트: '{selected_sheet.title}'")

    # 채널별 출력 폴더 계산
    sheet_title = selected_sheet.title  # 예: "Ch01_1go"
    channel_output_root = BASE_OUTPUT_DIR

    # 1) 환경변수 YTF_OUTPUT_ROOT가 이미 설정돼 있으면 그대로 사용 (BASE_OUTPUT_DIR에 반영됨)
    # 2) 없고, 시트명이 "ChXX_..." 형식이면 C:\YTFACTORY9\ChXX\03_Output 을 자동 추론
    if not (ENV_OUTPUT_ROOT and ENV_OUTPUT_ROOT.strip()):
        # "Ch01_1go" 같은 패턴에서 "Ch01"만 분리
        parts = sheet_title.split("_", 1)
        if len(parts) == 2 and parts[0].startswith("Ch"):
            ch_id = parts[0]  # "Ch01"
            guessed_root = os.path.join(PROJECT_ROOT, ch_id, "03_Output")
            if os.path.isdir(guessed_root):
                channel_output_root = guessed_root

    target_folder = os.path.join(channel_output_root, sheet_title)
    if not os.path.exists(target_folder):
        print(f"❌ 폴더가 없습니다: {target_folder}")
        return

    # 이미지 탐색
    image_files = glob.glob(os.path.join(target_folder, "*_image_group.png"))
    if not image_files: image_files = glob.glob(os.path.join(target_folder, "*.png"))

    if not image_files:
        print("🤷‍♂️ 변환할 이미지가 없습니다.")
        return

    print(f"🎯 총 {len(image_files)}개의 이미지를 변환합니다.")

    # 변환 시작
    for img_path in image_files:
        if create_zoom_video(img_path) == False:
            break

    print("\n" + "="*50)
    print("🎉 변환 완료! (안정화 필터 적용됨)")
    print("👉 다음 단계: Mergy.py 실행!")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()