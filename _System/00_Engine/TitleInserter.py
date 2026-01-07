import os
import glob
import subprocess
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
FONT_PATH = os.path.join(ASSET_DIR, "Sub", "Fonts", "BMJUA_ttf.ttf")

# 공통 키/시트 설정
JSON_KEY_FILE = r"C:\YtFactory9\_System\02_Key\service_account.json"
SHEET_URL_FILE = r"C:\YtFactory9\_System\00_Engine\YtFactory9_URL.txt"

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

    if "docs.google.com" in raw or "spreadsheets" in raw:
        return client.open_by_url(raw)
    else:
        return client.open_by_key(raw)


def clean_text_for_ffmpeg(text):
    """ 자막 특수문자 이스케이프 처리 """
    if not text: return ""
    text = text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace('"', '\\"')
    text = text.replace("%", "\\%")
    return text


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


def load_title_styles(style_name):
    """
    P열의 스타일명을 기반으로 제목/부제목 스타일을 로드합니다.
    JSON 파일은 첫 번째 객체가 제목, 두 번째 객체가 부제목 스타일입니다.
    
    반환값: (title_style, subtitle_style) 튜플
    """
    styles_dir = os.path.join(ASSET_DIR, "Sub", "Styles")
    fonts_dir = os.path.join(ASSET_DIR, "Sub", "Fonts")
    
    style_json = os.path.join(styles_dir, f"{style_name}.json")
    
    if not os.path.exists(style_json):
        print(f"   ⚠️ 스타일 파일 없음: {style_name}.json, 기본값 사용")
        return get_default_title_styles()
    
    try:
        print(f"   📂 스타일 파일 로드: {style_name}.json")
        with open(style_json, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 주석 제거
        cleaned_content = clean_json_content(content)
        # 후행 쉼표 제거
        cleaned_content = re.sub(r',(\s*[}\]])', r'\1', cleaned_content)
        
        # JSON 파싱 - 배열 또는 연속 객체 처리
        # title_1.json은 두 개의 객체가 연속으로 있을 수 있음
        title_data = {}
        subtitle_data = {}
        
        try:
            # 먼저 배열 형태로 파싱 시도
            data = json.loads(cleaned_content)
            if isinstance(data, list):
                title_data = data[0] if len(data) > 0 else {}
                subtitle_data = data[1] if len(data) > 1 else {}
            else:
                # 단일 객체인 경우
                title_data = data
        except json.JSONDecodeError:
            # 배열 파싱 실패 시, 두 개의 독립 객체를 분리해서 파싱
            # 첫 번째 { } 블록과 두 번째 { } 블록 찾기
            brace_start = cleaned_content.find('{')
            if brace_start == -1:
                raise Exception("JSON 객체를 찾을 수 없습니다")
            
            # 첫 번째 객체 찾기
            brace_count = 0
            first_end = -1
            for i in range(brace_start, len(cleaned_content)):
                if cleaned_content[i] == '{':
                    brace_count += 1
                elif cleaned_content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        first_end = i + 1
                        break
            
            if first_end > brace_start:
                title_str = cleaned_content[brace_start:first_end]
                try:
                    title_data = json.loads(title_str)
                except:
                    pass
            
            # 두 번째 객체 찾기
            second_start = cleaned_content.find('{', first_end)
            if second_start != -1:
                brace_count = 0
                second_end = -1
                for i in range(second_start, len(cleaned_content)):
                    if cleaned_content[i] == '{':
                        brace_count += 1
                    elif cleaned_content[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            second_end = i + 1
                            break
                if second_end > second_start:
                    subtitle_str = cleaned_content[second_start:second_end]
                    try:
                        subtitle_data = json.loads(subtitle_str)
                    except:
                        pass
        
        # 폰트 경로 처리
        def get_font_path(font_name):
            if not font_name:
                return FONT_PATH
            font_candidate = os.path.join(fonts_dir, font_name)
            if os.path.exists(font_candidate):
                return font_candidate
            print(f"   ⚠️ 폰트 파일을 찾을 수 없습니다: {font_name}, 기본 폰트 사용")
            return FONT_PATH
        
        # 제목 스타일 (첫 번째 객체)
        title_font_name = title_data.get("fontfile") or title_data.get("font")
        title_style = {
            "fontfile": get_font_path(title_font_name),
            "fontsize": title_data.get("fontsize", 60),
            "fontcolor": title_data.get("fontcolor", "white"),
            "x": title_data.get("x", "(w-text_w)/2"),
            "y": title_data.get("y", 100),
            "box": title_data.get("box", 1),
            "boxcolor": title_data.get("boxcolor", "black@1.0"),
            "boxborderw": title_data.get("boxborderw", 10)
        }
        
        # 부제목 스타일 (두 번째 객체, 없으면 기본값)
        if subtitle_data:
            subtitle_font_name = subtitle_data.get("fontfile") or subtitle_data.get("font")
            subtitle_style = {
                "fontfile": get_font_path(subtitle_font_name),
                "fontsize": subtitle_data.get("fontsize", 40),
                "fontcolor": subtitle_data.get("fontcolor", "white"),
                "x": subtitle_data.get("x", "(w-text_w)/2"),
                "y": subtitle_data.get("y", 180),
                "box": subtitle_data.get("box", 1),
                "boxcolor": subtitle_data.get("boxcolor", "black@1.0"),
                "boxborderw": subtitle_data.get("boxborderw", 10)
            }
        else:
            # 부제목 스타일이 없으면 제목 스타일을 기반으로 생성 (y와 fontsize만 다름)
            subtitle_style = title_style.copy()
            subtitle_style["fontsize"] = 40
            subtitle_style["y"] = 180
        
        print(f"   ✅ 제목 스타일: fontsize={title_style['fontsize']}, y={title_style['y']}")
        print(f"   ✅ 부제목 스타일: fontsize={subtitle_style['fontsize']}, y={subtitle_style['y']}")
        
        return title_style, subtitle_style
        
    except Exception as e:
        print(f"   ⚠️ 스타일 로드 실패 ({style_name}): {e}")
        return get_default_title_styles()


def get_default_title_styles():
    """기본 제목/부제목 스타일 반환"""
    return (
        {
            "fontfile": FONT_PATH,
            "fontsize": 60,
            "fontcolor": "white",
            "x": "(w-text_w)/2",
            "y": 100,
            "box": 1,
            "boxcolor": "black@1.0",
            "boxborderw": 10
        },
        {
            "fontfile": FONT_PATH,
            "fontsize": 40,
            "fontcolor": "white",
            "x": "(w-text_w)/2",
            "y": 180,
            "box": 1,
            "boxcolor": "black@1.0",
            "boxborderw": 10
        }
    )


def create_title_overlay_command(input_video, title_text, subtitle_text, title_style, subtitle_style, output_video):
    """
    FFmpeg 명령어 생성: 비디오에 제목/부제목 오버레이
    """
    # 텍스트 이스케이프 처리
    safe_title = clean_text_for_ffmpeg(title_text)
    safe_subtitle = clean_text_for_ffmpeg(subtitle_text)
    
    # 폰트 경로 이스케이프 처리
    safe_title_font = title_style['fontfile'].replace("\\", "/").replace(":", "\\:")
    safe_subtitle_font = subtitle_style['fontfile'].replace("\\", "/").replace(":", "\\:")
    
    # 제목 drawtext 필터
    title_filter = (
        f"drawtext=fontfile='{safe_title_font}':"
        f"text='{safe_title}':"
        f"fontcolor={title_style['fontcolor']}:"
        f"fontsize={title_style['fontsize']}:"
        f"x={title_style['x']}:"
        f"y={title_style['y']}:"
        f"box={title_style['box']}:"
        f"boxcolor={title_style['boxcolor']}:"
        f"boxborderw={title_style['boxborderw']}"
    )
    
    # 부제목 drawtext 필터
    subtitle_filter = (
        f"drawtext=fontfile='{safe_subtitle_font}':"
        f"text='{safe_subtitle}':"
        f"fontcolor={subtitle_style['fontcolor']}:"
        f"fontsize={subtitle_style['fontsize']}:"
        f"x={subtitle_style['x']}:"
        f"y={subtitle_style['y']}:"
        f"box={subtitle_style['box']}:"
        f"boxcolor={subtitle_style['boxcolor']}:"
        f"boxborderw={subtitle_style['boxborderw']}"
    )
    
    # 필터 체인 구성 (두 개의 drawtext를 순차적으로 적용)
    filter_complex = f"[0:v]{title_filter},{subtitle_filter}[v]"
    
    cmd = [
        FFMPEG_CMD, "-y",
        "-i", input_video,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",  # 오디오가 있으면 포함
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "copy",  # 오디오는 복사
        output_video
    ]
    
    return cmd


# ==========================================
# 3. 메인 로직
# ==========================================
def main():
    print("\n🎬 [TitleInserter] 제목/부제목 삽입기 시작")
    print("=" * 60)
    
    # 🛑 [Check 0] 필수 실행 파일 확인
    if not os.path.exists(FFMPEG_CMD) or not os.path.exists(FFPROBE_CMD):
        print("🚨 [오류] ffmpeg.exe 또는 ffprobe.exe가 없습니다.")
        print(f"👉 경로: {BASE_DIR}")
        input("엔터 키를 누르면 종료합니다...")
        return
    
    # 1. 구글 시트 연결
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        doc = load_spreadsheet(client)
    except Exception as e:
        print(f"❌ 시트 접속 실패: {e}")
        input("엔터 키를 누르면 종료합니다...")
        return
    
    # 2. 시트 선택
    all_worksheets = doc.worksheets()
    go_sheets = [ws for ws in all_worksheets if "go" in ws.title.lower()]
    
    if not go_sheets:
        print("❌ 'go' 시트가 없습니다.")
        input("엔터 키를 누르면 종료합니다...")
        return
    
    print("\n🎬 작업할 시트를 선택하세요")
    for idx, ws in enumerate(go_sheets):
        print(f" [{idx+1}] {ws.title}")
    
    selected_sheet = None
    while selected_sheet is None:
        try:
            choice = input("\n번호 입력 >> ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(go_sheets):
                selected_sheet = go_sheets[idx]
        except:
            pass
    
    SHEET_NAME = selected_sheet.title
    print(f"✅ 선택된 시트: '{SHEET_NAME}'")
    
    # 시트 이름에서 채널명 추출 (예: Ch01_2go -> Ch01)
    sheet_title = SHEET_NAME
    channel_match = re.search(r"Ch\d+", sheet_title)
    if not channel_match:
        print(f"❌ 시트 이름에서 채널명을 추출할 수 없습니다: {sheet_title}")
        input("엔터 키를 누르면 종료합니다...")
        return
    channel_name = channel_match.group(0)
    
    # 📂 폴더 경로 설정
    ROOT_OUTPUT = f"C:\\YtFactory9\\{channel_name}\\03_Output\\{SHEET_NAME}"
    MERGY_DIR = os.path.join(ROOT_OUTPUT, "Mergy")
    
    if not os.path.exists(MERGY_DIR):
        print(f"❌ Mergy 폴더가 없습니다: {MERGY_DIR}")
        input("엔터 키를 누르면 종료합니다...")
        return
    
    # 입력 영상 파일 찾기 (우선순위: Final_With_Sound.mp4 > Final_Complete.mp4)
    final_with_sound = os.path.join(MERGY_DIR, "Final_With_Sound.mp4")
    final_complete = os.path.join(MERGY_DIR, "Final_Complete.mp4")
    
    final_video = None
    if os.path.exists(final_with_sound):
        final_video = final_with_sound
        print(f"✅ 입력 영상 찾음: {os.path.basename(final_video)} (Final_With_Sound 우선 선택)")
    elif os.path.exists(final_complete):
        final_video = final_complete
        print(f"✅ 입력 영상 찾음: {os.path.basename(final_video)}")
    else:
        print(f"❌ 입력 영상 파일을 찾을 수 없습니다.")
        print(f"   찾는 위치: {MERGY_DIR}")
        print(f"   찾는 파일: Final_With_Sound.mp4 또는 Final_Complete.mp4")
        print("👉 먼저 Mergy를 실행하여 최종 영상을 생성해주세요.")
        input("엔터 키를 누르면 종료합니다...")
        return
    
    # 3. 시트 데이터 읽기 (N, O, P 열)
    all_values = selected_sheet.get_all_values()
    if not all_values:
        print("❌ 시트가 비어 있습니다.")
        input("엔터 키를 누르면 종료합니다...")
        return
    
    header = all_values[0]
    rows = all_values[1:]  # 헤더 제외
    
    # N, O, P 열 인덱스 찾기 (0-based)
    n_idx = None  # 제목
    o_idx = None  # 부제목
    p_idx = None  # 스타일명
    
    for idx, col_name in enumerate(header):
        col_upper = str(col_name).strip().upper()
        if col_upper == "TITLE" or idx == 13:  # N열은 13번 인덱스 (0-based)
            n_idx = idx
        elif col_upper == "SUBTITLE" or idx == 14:  # O열은 14번 인덱스
            o_idx = idx
        elif col_upper == "TITLE_STYLE" or "STYLE" in col_upper or idx == 15:  # P열은 15번 인덱스
            p_idx = idx
    
    # 명시적으로 N, O, P 열 인덱스 설정 (M=12, N=13, O=14, P=15)
    if n_idx is None:
        n_idx = 13  # N열
    if o_idx is None:
        o_idx = 14  # O열
    if p_idx is None:
        p_idx = 15  # P열
    
    print(f"📊 시트 열 인덱스: N={n_idx} (제목), O={o_idx} (부제목), P={p_idx} (스타일)")
    
    # 첫 번째 데이터 행에서 제목/부제목/스타일 읽기
    title_text = ""
    subtitle_text = ""
    style_name = ""
    
    for row in rows:
        if len(row) > max(n_idx, o_idx, p_idx):
            title_text = row[n_idx].strip() if len(row) > n_idx else ""
            subtitle_text = row[o_idx].strip() if len(row) > o_idx else ""
            style_name = row[p_idx].strip() if len(row) > p_idx else ""
            
            if title_text or subtitle_text or style_name:
                break  # 첫 번째 유효한 데이터 행 사용
    
    if not title_text and not subtitle_text:
        print("❌ 시트의 N열(제목) 또는 O열(부제목)에 데이터가 없습니다.")
        input("엔터 키를 누르면 종료합니다...")
        return
    
    if not style_name:
        style_name = "title_1"  # 기본값
        print(f"⚠️ P열(스타일)이 비어있어 기본값 사용: {style_name}")
    
    print(f"📝 제목: {title_text}")
    print(f"📝 부제목: {subtitle_text}")
    print(f"🎨 스타일: {style_name}")
    
    # 4. 스타일 로드
    print(f"\n📂 스타일 파일 로드 중...")
    title_style, subtitle_style = load_title_styles(style_name)
    
    # 5. 출력 파일 경로
    output_video = os.path.join(MERGY_DIR, "Final_WithTitle.mp4")
    
    # 6. FFmpeg 명령어 생성 및 실행
    print(f"\n🎬 제목/부제목 오버레이 적용 중...")
    print(f"   입력: {os.path.basename(final_video)}")
    print(f"   출력: {os.path.basename(output_video)}")
    
    cmd = create_title_overlay_command(
        final_video, title_text, subtitle_text,
        title_style, subtitle_style, output_video
    )
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"\n🎉 [성공] {os.path.basename(output_video)} 생성 완료!")
        print(f"👉 저장 위치: {MERGY_DIR}")
        os.startfile(MERGY_DIR)
    except subprocess.CalledProcessError as e:
        print(f"\n💥 [실패] 제목/부제목 삽입 실패: {e}")
        if e.stderr:
            print(f"오류 메시지: {e.stderr.decode('utf-8', errors='ignore')}")
        input("엔터 키를 누르면 종료합니다...")
    except Exception as e:
        print(f"\n💥 [실패] 예상치 못한 오류: {e}")
        input("엔터 키를 누르면 종료합니다...")


if __name__ == "__main__":
    main()

