import os
import glob
import subprocess
import time
import sys
import shutil
import re
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 설정 및 경로 정의
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# YtFactory9 절대 경로 기반 설정
BASE_DIR = r"C:\YtFactory9"
ASSET_DIR = r"C:\YtFactory9\_System\04_Co_Asset"

# [필수 자산 경로]
FFMPEG_CMD = r"C:\YtFactory9\ffmpeg.exe"
FFPROBE_CMD = r"C:\YtFactory9\ffprobe.exe"
# 기본 폰트 (폴백용) - 실제 사용 폰트는 subtype 기반으로 동적 선택
FONT_PATH = os.path.join(ASSET_DIR, "Sub", "Fonts", "BMJUA_ttf.ttf")

# 공통 키/시트 설정 (ImageMaker / VoiceMaker와 동일)
JSON_KEY_FILE = r"C:\YtFactory9\_System\02_Key\service_account.json"
SHEET_URL_FILE = r"C:\YtFactory9\_System\00_Engine\YtFactory9_URL.txt"

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


def clean_text_for_ffmpeg(text):
    """ 자막 특수문자 이스케이프 처리 """
    if not text: return ""
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "").replace('"', '')
    text = text.replace("%", "\\%").replace("/", "\\/")
    return text

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
            FFPROBE_CMD, "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        duration = result.stdout.strip()
        if duration:
            return float(duration)
        # 비디오 스트림 duration이 없으면 format duration 사용
        cmd = [
            FFPROBE_CMD, "-v", "error", "-show_entries", 
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except:
        return 0.0

def ensure_video_has_audio(video_path):
    """
    비디오 파일에 오디오 스트림이 있는지 확인하고, 없으면 무음 오디오를 추가
    반환: 오디오가 있는 비디오 경로 (원본 또는 새로 생성된 파일)
    """
    try:
        # 비디오에 오디오 스트림이 있는지 확인
        cmd = [
            FFPROBE_CMD, "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        # 오디오 스트림이 있으면 원본 반환
        if result.stdout.strip() == "audio":
            return video_path
        
        # 오디오가 없으면 비디오 길이 측정
        video_duration = get_audio_duration(video_path)
        if video_duration <= 0:
            # 비디오 길이를 비디오 스트림으로 측정
            cmd = [
                FFPROBE_CMD, "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                video_duration = float(result.stdout.strip())
            except:
                video_duration = 5.0  # 기본값 5초
        
        # 무음 오디오 추가
        output_path = video_path.replace(".mp4", "_with_audio.mp4")
        print(f"   🔊 오디오 없음 감지 → 무음 오디오 추가 중... ({video_duration:.2f}초)")
        
        cmd = [
            FFMPEG_CMD, "-y",
            "-i", video_path,
            "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-t", str(video_duration),
            output_path
        ]
        
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return output_path
        
    except Exception as e:
        print(f"   ⚠️ 오디오 추가 실패: {e}, 원본 파일 사용")
        return video_path

def find_visual_asset(search_dir, gid):
    """ 
    [서열 정리 알고리즘]
    GID(이미지그룹)를 기준으로 우선순위에 따라 파일을 찾습니다.
    반환값: (파일경로, 타입: 'video'|'image', 설명)
    """
    gid = str(gid).strip()
    
    # 우선순위 목록 (1~6순위)
    candidates = [
        (f"{gid}_source.mp4",      "video", "👑 1순위 (소스 영상)"),
        (f"{gid}.mp4",             "video", "🥈 2순위 (수동 영상)"),
        (f"{gid}_source_kb.mp4",   "video", "🥉 3순위 (소스 켄번)"),
        (f"{gid}_image_group.mp4", "video", "4순위 (AI 켄번)"),
        (f"{gid}.png",             "image", "5순위 (수동 이미지)"),
        (f"{gid}_image_group.png", "image", "6순위 (AI 이미지)")
    ]

    for fname, type_, desc in candidates:
        path = os.path.join(search_dir, fname)
        if os.path.exists(path):
            return path, type_, desc
            
    return None, None, None


def clean_json_content(content):
    """JSON 파일에서 주석(//)과 후행 쉼표를 제거"""
    lines = content.split('\n')
    cleaned_lines = []
    for line in lines:
        # // 주석 제거
        if '//' in line:
            comment_idx = line.find('//')
            # 문자열 안에 있는 //는 제거하지 않음 (간단한 처리)
            if line[:comment_idx].count('"') % 2 == 0:
                line = line[:comment_idx]
        cleaned_lines.append(line.rstrip())
    return '\n'.join(cleaned_lines)

def load_json_with_comments(file_path):
    """주석이 포함된 JSON 파일을 로드"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # 주석 제거
        cleaned_content = clean_json_content(content)
        # 후행 쉼표 제거 (간단한 정규식으로 처리)
        cleaned_content = re.sub(r',(\s*[}\]])', r'\1', cleaned_content)
        return json.loads(cleaned_content)
    except Exception as e:
        raise Exception(f"JSON 파싱 실패: {e}")

def get_subtitle_style(subtype):
    r"""
    시트 E열(Subtype)을 기반으로 자막 스타일 설정을 로드합니다.
    우선순위:
      1) _System\04_Co_Asset\Sub\Styles\{subtype}.json 파일에서 스타일 로드
      2) 기본 스타일: default.json 또는 하드코딩된 기본값
    반환값: dict (fontfile, fontsize, fontcolor, x, y, box, boxcolor, boxborderw)
    """
    styles_dir = os.path.join(ASSET_DIR, "Sub", "Styles")
    fonts_dir = os.path.join(ASSET_DIR, "Sub", "Fonts")

    subtype_clean = (subtype or "").strip()
    
    # 디버깅: subtype 값 확인
    if subtype_clean:
        print(f"   🔍 E열 Subtype 감지: '{subtype_clean}'")
    
    if subtype_clean:
        # 대소문자 구분하여 파일명 매칭 (Chapter.json, Talk.json 등)
        style_json = os.path.join(styles_dir, f"{subtype_clean}.json")
        
        if os.path.exists(style_json):
            try:
                print(f"   📂 스타일 파일 찾음: {os.path.basename(style_json)}")
                data = load_json_with_comments(style_json)
                
                # 폰트 경로 처리
                font_name = data.get("fontfile") or data.get("font")
                font_path = FONT_PATH  # 기본값
                if font_name:
                    font_candidate = os.path.join(fonts_dir, font_name)
                    if os.path.exists(font_candidate):
                        font_path = font_candidate
                        print(f"   ✅ 폰트 적용: {font_name}")
                    else:
                        print(f"   ⚠️ 폰트 파일을 찾을 수 없습니다: {font_name}, 기본 폰트 사용")
                
                # 스타일 설정 반환
                style_result = {
                    "fontfile": font_path,
                    "fontsize": data.get("fontsize", 50),
                    "fontcolor": data.get("fontcolor", "white"),
                    "x": data.get("x", "(w-text_w)/2"),
                    "y": data.get("y", "h-100"),
                    "box": data.get("box", 1),
                    "boxcolor": data.get("boxcolor", "black@0.6"),
                    "boxborderw": data.get("boxborderw", 10)
                }
                print(f"   ✨ 스타일 적용 완료: {subtype_clean}")
                return style_result
            except Exception as e:
                print(f"   ⚠️ 스타일 로드 실패 (Subtype={subtype_clean}): {e}")
        else:
            print(f"   ⚠️ 스타일 파일 없음: {os.path.basename(style_json)}")

    # 폴백: default.json 시도
    default_json = os.path.join(styles_dir, "default.json")
    if os.path.exists(default_json):
        try:
            print(f"   📂 기본 스타일 파일 사용: default.json")
            data = load_json_with_comments(default_json)
            font_name = data.get("fontfile") or data.get("font")
            font_path = FONT_PATH
            if font_name:
                font_candidate = os.path.join(fonts_dir, font_name)
                if os.path.exists(font_candidate):
                    font_path = font_candidate
            
            return {
                "fontfile": font_path,
                "fontsize": data.get("fontsize", 50),
                "fontcolor": data.get("fontcolor", "white"),
                "x": data.get("x", "(w-text_w)/2"),
                "y": data.get("y", "h-100"),
                "box": data.get("box", 1),
                "boxcolor": data.get("boxcolor", "black@0.6"),
                "boxborderw": data.get("boxborderw", 10)
            }
        except Exception as e:
            print(f"   ⚠️ 기본 스타일 로드 실패: {e}")

    # 최종 폴백: 하드코딩된 기본값
    print(f"   ⚠️ 기본값 사용 (스타일 파일 없음)")
    return {
        "fontfile": FONT_PATH,
        "fontsize": 50,
        "fontcolor": "white",
        "x": "(w-text_w)/2",
        "y": "h-100",
        "box": 1,
        "boxcolor": "black@0.6",
        "boxborderw": 10
    }

# ==========================================
# 3. 메인 로직
# ==========================================
def main():
    print("\n🚀 [Mergy] 최종 영상 조립기 (Smart Skip & Sync) 시작")
    print("=" * 60)

    # 🛑 [Check 0] 필수 실행 파일 확인
    if not os.path.exists(FFMPEG_CMD) or not os.path.exists(FFPROBE_CMD):
        print("🚨 [오류] ffmpeg.exe 또는 ffprobe.exe가 없습니다.")
        print(f"👉 경로: {CURRENT_DIR}")
        input("엔터 키를 누르면 종료합니다..."); return

    if not os.path.exists(FONT_PATH):
        print(f"🚨 [오류] 폰트 파일이 없습니다.\n👉 경로: {FONT_PATH}")
        input("엔터 키를 누르면 종료합니다..."); return

    # 1. 구글 시트 연결
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

    # 시트 이름에서 채널명 추출 (예: Ch01_2go -> Ch01)
    sheet_title = SHEET_NAME
    channel_match = re.search(r"Ch\d+", sheet_title)
    if not channel_match:
        print(f"❌ 시트 이름에서 채널명을 추출할 수 없습니다: {sheet_title}")
        return
    channel_name = channel_match.group(0)

    # 📂 폴더 경로 설정 (YtFactory9 표준 구조)
    ROOT_OUTPUT = f"C:\\YtFactory9\\{channel_name}\\03_Output\\{SHEET_NAME}"
    CLIP_DIR = os.path.join(ROOT_OUTPUT, "Clip")
    FINAL_DIR = os.path.join(ROOT_OUTPUT, "Mergy")
    VOICE_DIR = os.path.join(ROOT_OUTPUT, "Voice")

    if not os.path.exists(ROOT_OUTPUT): os.makedirs(ROOT_OUTPUT)
    if not os.path.exists(CLIP_DIR): os.makedirs(CLIP_DIR)
    if not os.path.exists(FINAL_DIR): os.makedirs(FINAL_DIR)

    # 데이터 로드
    rows = selected_sheet.get_all_values()[1:] # 헤더 제외
    
    # ---------------------------------------------------------
    # 🛑 [Step 1] 사전 전수 조사 (Zero-Trash Check)
    # ---------------------------------------------------------
    print("\n🧐 [무결성 검사] 재료 전수 조사 중...", end="")
    
    missing_log = []
    tasks = []

    for i, row in enumerate(rows):
        if len(row) < 3: continue 
        
        row_id = row[0].strip()        # A열: ID
        script = row[1].strip()        # B열: Script
        gid = row[2].strip()           # C열: Image Group
        subtype = row[4].strip() if len(row) > 4 else ""  # E열: Subtype (옵션)
        
        if not row_id or not gid: continue

        # 1. 오디오 확인
        audio_path = os.path.join(VOICE_DIR, f"{row_id}.mp3")
        if not os.path.exists(audio_path):
            missing_log.append(f"❌ [Row {i+2}] 오디오 없음: {row_id}.mp3")
            continue

        # 2. 시각 자료 확인 (C열 GID 기준)
        visual_path, v_type, v_desc = find_visual_asset(ROOT_OUTPUT, gid)
        if not visual_path:
            missing_log.append(f"❌ [Row {i+2}] 시각자료 없음 (Group: {gid}) - 1~6순위 파일 전멸")
            continue

        tasks.append({
            "id": row_id,
            "gid": gid,
            "script": script,
            "audio": audio_path,
            "visual": visual_path,
            "v_type": v_type,
            "v_desc": v_desc,
            "subtype": subtype
        })

    # 결과 판정
    if missing_log:
        print(" [실패] 💥")
        print("\n" + "="*60)
        print("🚨 [치명적 오류] 재료가 부족하여 작업을 시작할 수 없습니다.")
        print("   (쓰레기 영상 생성을 방지하기 위해 시스템을 중단합니다)")
        print("="*60)
        for log in missing_log:
            print(log)
        print("="*60)
        print("👉 부족한 파일을 채워넣고 다시 실행해주세요.")
        input("엔터 키를 누르면 종료합니다...")
        return
    else:
        print(" [통과] ✨")
        print(f"✅ 모든 재료가 완벽합니다! 총 {len(tasks)}개 컷 조립을 시작합니다.\n")

    # ==========================================
    # 3. 클립 생성 루프 (Continuity & Drift Fix)
    # ==========================================
    valid_clips = []
    
    # 🕒 [핵심] 비디오 커서 (각 그룹별로 어디까지 재생했는지 기억)
    video_cursors = {} 

    for task in tasks:
        file_id = task['id']
        gid = task['gid']
        duration = get_audio_duration(task['audio'])
        output_clip = os.path.join(CLIP_DIR, f"{file_id}_clip.mp4")
        
        # ----------------------------------------------------
        # 🕵️ [Continuity Logic] 영상 시간 계산 (생성 여부와 무관하게 필수!)
        # 파일이 있든 없든 이 계산은 무조건 해야 다음 영상이 이어집니다.
        # ----------------------------------------------------
        start_time = 0.0
        if task['v_type'] == 'video':
            if gid not in video_cursors:
                video_cursors[gid] = 0.0
            start_time = video_cursors[gid]
            # 다음 컷을 위해 커서 업데이트 (누적)
            video_cursors[gid] += duration

        # ==========================================
        # 🎬 생성 작업 시작 (E열 스타일 적용을 위해 항상 재생성)
        # ==========================================
        # 기존 파일이 있으면 삭제 (E열 값 변경 시 스타일 재적용을 위해)
        if os.path.exists(output_clip):
            print(f"🔄 [{file_id}] 기존 파일 삭제 후 재생성 (E열 스타일 적용)")
            try:
                os.remove(output_clip)
            except Exception as e:
                print(f"   ⚠️ 파일 삭제 실패: {e}")
        
        print(f"🔨 [{file_id}] 조립: {task['v_desc']} ({duration:.3f}s)")

        # 행별 Subtype(E열) 기반 자막 스타일 적용
        subtype_value = task.get('subtype', '').strip()
        if not subtype_value:
            print(f"   ⚠️ E열이 비어있습니다. 기본 스타일 사용")
        style = get_subtitle_style(subtype_value)
        safe_font = style['fontfile'].replace("\\", "/").replace(":", "\\:")
        safe_script = clean_text_for_ffmpeg(task['script'])

        # JSON 스타일 설정을 기반으로 drawtext 필터 생성
        drawtext_filter = (
            f"drawtext=fontfile='{safe_font}':text='{safe_script}':"
            f"fontcolor={style['fontcolor']}:fontsize={style['fontsize']}:"
            f"x={style['x']}:y={style['y']}:"
            f"box={style['box']}:boxcolor={style['boxcolor']}:boxborderw={style['boxborderw']}"
        )

        input_args = []
        filter_chain = ""
        
        if task['v_type'] == 'image':
            # 🖼️ 이미지 -> 단순 정지 화면
            input_args = ["-loop", "1", "-i", task['visual'], "-i", task['audio']]
            
            vf = (
                f"scale=1280:720:force_original_aspect_ratio=decrease,"
                f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                f"setsar=1,fps=30,setpts=PTS-STARTPTS,"
                f"{drawtext_filter}"
            )
            filter_chain = f"[0:v]{vf}[v];[1:a]apad[a]"

        else:
            # 🎥 비디오 -> 정방향-역방향-정방향 반복 패턴
            video_duration = get_video_duration(task['visual'])
            
            if video_duration <= 0:
                # 비디오 길이를 측정할 수 없으면 기본 루프 사용
                input_args = ["-i", task['visual'], "-i", task['audio']]
                vf = (
                    f"loop=loop=-1:size=32767:start=0,"
                    f"trim=start={start_time}:duration={duration},"
                    f"setpts=PTS-STARTPTS,"
                    f"scale=1280:720:force_original_aspect_ratio=decrease,"
                    f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                    f"fps=30,format=yuv420p,"
                    f"{drawtext_filter}"
                )
                filter_chain = f"[0:v]{vf}[v];[1:a]apad[a]"
            else:
                # 정방향-역방향-정방향 패턴 생성
                input_args = ["-i", task['visual'], "-i", task['audio']]
                
                # 필요한 세그먼트 계산
                segments = []
                remaining_time = duration
                is_forward = True
                current_pos = start_time % video_duration
                
                while remaining_time > 0:
                    if is_forward:
                        # 정방향 재생
                        segment_duration = min(remaining_time, video_duration - current_pos)
                        if segment_duration > 0:
                            segments.append({
                                'start': current_pos,
                                'duration': segment_duration,
                                'reverse': False
                            })
                            remaining_time -= segment_duration
                            current_pos += segment_duration
                            if current_pos >= video_duration:
                                current_pos = 0
                                is_forward = False
                    else:
                        # 역방향 재생 (되감기)
                        segment_duration = min(remaining_time, video_duration)
                        if segment_duration > 0:
                            segments.append({
                                'start': video_duration - segment_duration,
                                'duration': segment_duration,
                                'reverse': True
                            })
                            remaining_time -= segment_duration
                            is_forward = True
                
                # 세그먼트가 없으면 기본 처리
                if not segments:
                    vf = (
                        f"loop=loop=-1:size=32767:start=0,"
                        f"trim=start={start_time}:duration={duration},"
                        f"setpts=PTS-STARTPTS,"
                        f"scale=1280:720:force_original_aspect_ratio=decrease,"
                        f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                        f"fps=30,format=yuv420p,"
                        f"{drawtext_filter}"
                    )
                    filter_chain = f"[0:v]{vf}[v];[1:a]apad[a]"
                else:
                    # 여러 세그먼트를 concat으로 연결
                    segment_filters = []
                    for i, seg in enumerate(segments):
                        base_vf = (
                            f"trim=start={seg['start']}:duration={seg['duration']},"
                            f"setpts=PTS-STARTPTS"
                        )
                        if seg['reverse']:
                            base_vf = f"{base_vf},reverse"
                        scale_vf = (
                            f"scale=1280:720:force_original_aspect_ratio=decrease,"
                            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,"
                            f"fps=30,format=yuv420p"
                        )
                        segment_filters.append(f"[0:v]{base_vf},{scale_vf}[seg{i}]")
                    
                    # concat 필터 생성
                    concat_inputs = "".join([f"[seg{i}]" for i in range(len(segments))])
                    concat_filter = f"{concat_inputs}concat=n={len(segments)}:v=1[concat_v]"
                    
                    # 자막 필터 추가
                    final_vf = f"[concat_v]{drawtext_filter}[v]"
                    
                    filter_chain = ";".join(segment_filters) + ";" + concat_filter + ";" + final_vf + ";[1:a]apad[a]"

        cmd = [
            FFMPEG_CMD, "-y",
            *input_args,
            "-filter_complex", filter_chain,
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration), # Drift 방지용 강제 길이
            output_clip
        ]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            valid_clips.append(output_clip)
        except Exception as e:
            print(f"   💥 생성 실패: {e}")

    # ==========================================
    # 4. 최종 병합 (Finalize)
    # ==========================================
    if not valid_clips: return

    print("\n" + "="*50)
    print("🔗 최종 병합 시작 (Finalize)")
    
    list_txt = os.path.join(FINAL_DIR, "mylist.txt")
    final_mp4 = os.path.join(FINAL_DIR, "Final_Complete.mp4")
    
    with open(list_txt, "w", encoding='utf-8') as f:
        for clip in valid_clips:
            safe_path = clip.replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    # 1차 시도: Copy Mode (빠름)
    merge_cmd = [
        FFMPEG_CMD, "-y", "-f", "concat", "-safe", "0",
        "-i", list_txt, "-c", "copy", final_mp4
    ]
    
    success = False
    try:
        subprocess.run(merge_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"🎉 [성공] {os.path.basename(final_mp4)} 생성 완료!")
        success = True
    except:
        print("⚠️ 고속 병합 실패. 재인코딩 모드로 전환합니다...")
        
        # 2차 시도: Re-encode Mode (호환성 향상)
        merge_encode = [
            FFMPEG_CMD, "-y", "-f", "concat", "-safe", "0",
            "-i", list_txt, 
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-avoid_negative_ts", "make_zero",
            final_mp4
        ]
        try:
            subprocess.run(merge_encode, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"🎉 [성공] 재인코딩 병합 완료! ({os.path.basename(final_mp4)})")
            success = True
        except Exception as e:
            print(f"💥 최종 병합 실패: {e}")

    if os.path.exists(list_txt): os.remove(list_txt)
    
    if success:
        os.startfile(FINAL_DIR)

if __name__ == "__main__":
    main()