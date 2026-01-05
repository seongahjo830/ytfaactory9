import tkinter as tk
from tkinter import messagebox
import os
import requests
from PIL import Image, ImageGrab
from io import BytesIO
import pyperclip
import yt_dlp
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import threading

# ==========================================
# 1. 설정 및 경로 정의 (YTFactory9 구조 대응)
# ==========================================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))           # ...\_System\00_Engine
SYSTEM_DIR = os.path.dirname(CURRENT_DIR)                          # ...\_System
PROJECT_ROOT = os.path.dirname(SYSTEM_DIR)                         # ...\YTFACTORY9

# 과거 BASE_DIR 개념은 _System 루트로 사용
BASE_DIR = SYSTEM_DIR

# 출력 루트: 환경변수(YTF_OUTPUT_ROOT) 우선, 없으면 구버전 호환용 PROJECT_ROOT\02_Output
ENV_OUTPUT_ROOT = os.environ.get("YTF_OUTPUT_ROOT")
if ENV_OUTPUT_ROOT and ENV_OUTPUT_ROOT.strip():
    OUTPUT_ROOT = ENV_OUTPUT_ROOT.strip()
else:
    OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "02_Output")

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

# ==========================================
# 2. 유틸리티 함수
# ==========================================
def normalize_time_input(raw: str) -> str:
    """
    예전 버전과의 호환을 위해 남겨둔 함수.
    하나의 칸에 "330" 처럼 적으면 "3:30" 형태의 문자열로 바꿔준다.
    (현재는 내부적으로 초 단위로 계산하는 새로운 로직을 사용)
    """
    if not raw:
        return "0:20"
    raw = raw.strip()
    if ":" in raw:
        return raw
    digits = re.sub(r'\D', '', raw)
    if not digits:
        return "0:20"
    if len(digits) <= 2:
        secs = int(digits)
        mins = secs // 60
        secs = secs % 60
    else:
        mins = int(digits[:-2]) if digits[:-2] else 0
        secs = int(digits[-2:])
        mins += secs // 60
        secs = secs % 60
    return f"{mins}:{secs:02d}"


def parse_time_to_seconds(raw: str):
    """
    "330" -> 210초, "3:30" -> 210초.
    빈 문자열이면 None 반환.
    """
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None

    # "분:초" 형식
    if ":" in raw:
        try:
            m, s = raw.split(":", 1)
            m = int(re.sub(r'\D', '', m or "0") or 0)
            s = int(re.sub(r'\D', '', s or "0") or 0)
            return m * 60 + s
        except Exception:
            return None

    # 숫자만 있을 때 -> 뒤 2자리 초, 앞자리 분
    digits = re.sub(r'\D', '', raw)
    if not digits:
        return None
    if len(digits) <= 2:
        secs = int(digits)
        return secs
    mins = int(digits[:-2]) if digits[:-2] else 0
    secs = int(digits[-2:])
    return mins * 60 + secs

def get_ffmpeg_path():
    """
    FFmpeg 실행 파일 위치를 탐색하고, 해당 폴더를 시스템 PATH에 추가합니다.
    """
    candidates = [
        os.path.join(PROJECT_ROOT, "ffmpeg.exe"),
        os.path.join(PROJECT_ROOT, "bin", "ffmpeg.exe"),
        os.path.join(BASE_DIR, "ffmpeg.exe"),
        os.path.join(PROJECT_ROOT, "01_Go", "ffmpeg.exe"),  # 구버전(YTFactory8) 호환
        "ffmpeg"
    ]
    
    selected_path = None
    for path in candidates:
        if path == "ffmpeg": continue
        if os.path.exists(path):
            selected_path = path
            break
    
    if selected_path:
        ffmpeg_dir = os.path.dirname(selected_path)
        if ffmpeg_dir not in os.environ["PATH"]:
            os.environ["PATH"] += os.pathsep + ffmpeg_dir
            
    return selected_path

def save_padded_image(img, save_path):
    try:
        img = img.convert("RGB")
        target_w, target_h = 1920, 1080
        src_w, src_h = img.size
        scale = min(target_w / src_w, target_h / src_h)
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        new_img = Image.new("RGB", (target_w, target_h), (0, 0, 0))
        x_offset = (target_w - new_w) // 2
        y_offset = (target_h - new_h) // 2
        new_img.paste(img, (x_offset, y_offset))
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        new_img.save(save_path, quality=95)
        print(f"✅ 이미지 저장: {os.path.basename(save_path)}")
        return True
    except Exception as e:
        print(f"❌ 이미지 실패: {e}")
        return False

def download_youtube_clip(url, start_raw, end_raw, save_path, include_audio=True):
    ffmpeg_exe = get_ffmpeg_path()
    
    if not ffmpeg_exe:
        print("❌ [오류] ffmpeg.exe를 찾을 수 없습니다! (프로젝트 루트 폴더 확인)")
        return False

    try:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        # 1. 시간 계산 (시작/끝 칸 2개 사용)
        start_seconds = parse_time_to_seconds(start_raw)
        end_seconds_input = parse_time_to_seconds(end_raw)

        # 시작 시간이 비어있으면 0초부터
        if start_seconds is None:
            start_seconds = 0

        # 끝 시간이 비어있으면 기본 20초 구간
        if end_seconds_input is None:
            target_end = start_seconds + 20  # 기본 20초
        else:
            target_end = end_seconds_input

        # 끝 시간이 시작 시간보다 앞이면, 안전하게 20초 구간으로 재조정
        if target_end <= start_seconds:
            target_end = start_seconds + 20

        # 2. 영상 정보 미리 확인 (길이 체크)
        print(f"🔍 영상 정보 확인 중...")
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            duration = info.get('duration', 0)

        # 3. 짧은 영상이어도 시작 시간은 그대로, 끝만 영상 끝으로 보정
        if duration > 0 and duration < target_end:
            print(f"⚠️ 짧은 영상 감지 ({duration}초). 구간을 {start_seconds}초~{duration}초로 자동 조정합니다.")
            end_seconds = duration  # 끝나는 시간만 영상 끝으로 맞춤
        else:
            end_seconds = target_end

        # 시작 시간이 영상 길이보다 길면 오류 방지
        if duration > 0 and start_seconds >= duration:
            print("❌ 시작 시간이 영상 길이보다 깁니다. 0초부터 다운로드합니다.")
            start_seconds = 0
            end_seconds = duration

        # 4. 다운로드 옵션 설정 (무조건 구간 자르기 시도)
        if include_audio:
            fmt = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        else:
            # 비디오만 (무음 영상)
            fmt = 'bestvideo[ext=mp4]/bestvideo'

        ydl_opts = {
            'format': fmt,
            'outtmpl': save_path,
            'quiet': True,
            'no_warnings': True,
            'ffmpeg_location': ffmpeg_exe,
            # [중요] 어떤 경우에도 구간 설정을 적용합니다.
            'download_ranges': lambda info, ydl: [{'start_time': start_seconds, 'end_time': end_seconds}]
        }

        # 5. 다운로드 시도
        print(f"⏳ 다운로드 시작 ({start_seconds}초 ~ {end_seconds}초, 오디오 {'포함' if include_audio else '미포함'})...")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            print(f"✅ 영상 저장: {os.path.basename(save_path)}")
            return True
            
        except yt_dlp.utils.DownloadError as de:
            # 6. [실패 시 안전장치] 정밀 자르기가 실패하면 그때만 전체 다운로드
            print("⚠️ 정밀 자르기 실패 (코덱/FFmpeg 문제). 전체 다운로드로 재시도합니다.")
            if 'download_ranges' in ydl_opts:
                del ydl_opts['download_ranges'] # 구간 설정 제거
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            print(f"✅ (재시도) 영상 저장 완료: {os.path.basename(save_path)}")
            return True

    except Exception as e:
        print(f"❌ 영상 실패: {e}")
        return False

# ==========================================
# 3. GUI 클래스
# ==========================================
class SourceHunterRemote:
    def __init__(self, root, scenarios, sheet_name):
        self.root = root
        self.scenarios = scenarios
        self.sheet_name = sheet_name
        self.current_idx = 0
        
        self.root.title(f"Source Hunter - {self.sheet_name} Project")
        self.root.geometry("450x700+1450+50") 
        self.root.attributes('-topmost', True)
        self.create_widgets()
        self.load_scene()
        
        ff = get_ffmpeg_path()
        if ff: print(f"✅ FFmpeg 시스템 로드 완료: {ff}")

    def create_widgets(self):
        # 상단 상태바
        self.lbl_status = tk.Label(self.root, text="Ready...", font=("Arial", 12, "bold"), bg="#ddd", pady=10)
        self.lbl_status.pack(fill="x")

        # 스크립트 뷰어
        frame_script = tk.LabelFrame(self.root, text=" Script ", padx=10, pady=10)
        frame_script.pack(fill="both", expand=True, padx=10, pady=10)
        self.txt_script = tk.Text(frame_script, height=8, font=("Malgun Gothic", 10), wrap="word", bg="#f9f9f9")
        self.txt_script.pack(fill="both", expand=True)

        # 컨트롤 패널
        frame_ctrl = tk.Frame(self.root, pady=10)
        frame_ctrl.pack(fill="x", padx=10)

        # [이미지 저장]
        tk.Button(frame_ctrl, text="📸 이미지 저장 (클립보드)", bg="#4CAF50", fg="white", font=("Arial", 11, "bold"), height=2, command=self.action_save_image).pack(fill="x", pady=5)
        
        # [유튜브 클립] - 시작/끝 시간 + 오디오 포함 여부
        frame_yt = tk.Frame(frame_ctrl, pady=5)
        frame_yt.pack(fill="x")

        tk.Label(frame_yt, text="시작", font=("Arial", 10)).pack(side="left")
        self.entry_time_start = tk.Entry(frame_yt, width=6, font=("Arial", 11))
        self.entry_time_start.insert(0, "3:30")
        self.entry_time_start.pack(side="left", padx=3)

        tk.Label(frame_yt, text="~", font=("Arial", 10)).pack(side="left")
        self.entry_time_end = tk.Entry(frame_yt, width=6, font=("Arial", 11))
        # 끝 시간은 기본 비워두면 20초 구간 자동
        self.entry_time_end.pack(side="left", padx=3)

        self.var_include_audio = tk.BooleanVar(value=True)
        tk.Checkbutton(
            frame_yt,
            text="오디오 포함",
            variable=self.var_include_audio,
            font=("Arial", 9)
        ).pack(side="left", padx=5)

        tk.Button(
            frame_yt,
            text="🎬 클립 저장 (YouTube)",
            bg="#F44336",
            fg="white",
            font=("Arial", 10, "bold"),
            command=self.action_save_video
        ).pack(side="left", fill="x", expand=True, padx=3)

        # 네비게이션
        frame_nav = tk.Frame(self.root, pady=10)
        frame_nav.pack(fill="x")
        tk.Button(frame_nav, text="◀ 이전", command=self.prev_scene).pack(side="left", padx=20)
        tk.Button(frame_nav, text="다음 ▶", command=self.next_scene).pack(side="right", padx=20)

    def load_scene(self):
        if self.current_idx >= len(self.scenarios):
            messagebox.showinfo("완료", "모든 컷을 확인했습니다.")
            return
        
        data = self.scenarios[self.current_idx]
        self.lbl_status.config(text=f"Group #{data['group_id']} ({self.current_idx + 1}/{len(self.scenarios)})")
        
        self.txt_script.config(state="normal")
        self.txt_script.delete("1.0", tk.END)
        self.txt_script.insert(tk.END, data['script'])
        self.txt_script.config(state="disabled")

    def get_target_folder(self):
        path = os.path.join(OUTPUT_ROOT, self.sheet_name)
        os.makedirs(path, exist_ok=True)
        return path

    def action_save_image(self):
        clipboard_data = ImageGrab.grabclipboard()
        img_obj = None
        if isinstance(clipboard_data, Image.Image): img_obj = clipboard_data
        elif isinstance(clipboard_data, list): 
            try: img_obj = Image.open(clipboard_data[0])
            except: pass
        
        if not img_obj:
            messagebox.showwarning("주의", "클립보드에 이미지가 없습니다.")
            return

        group_id = self.scenarios[self.current_idx]['group_id']
        filename = f"{group_id}_source.jpg"
        save_path = os.path.join(self.get_target_folder(), filename)

        if os.path.exists(save_path):
            if not messagebox.askyesno("덮어쓰기", f"{filename} 이미 존재합니다.\n덮어쓸까요?"): return

        if save_padded_image(img_obj, save_path):
            self.lbl_status.config(text=f"✅ 저장 완료: {filename}")

    def action_save_video(self):
        url = pyperclip.paste()
        if "youtu" not in url:
            messagebox.showwarning("주의", "유튜브 링크가 아닙니다.")
            return

        group_id = self.scenarios[self.current_idx]['group_id']
        filename = f"{group_id}_source.mp4"
        save_path = os.path.join(self.get_target_folder(), filename)

        if os.path.exists(save_path):
            if not messagebox.askyesno("덮어쓰기", f"{filename} 이미 존재합니다.\n덮어쓸까요?"):
                return

        start_raw = self.entry_time_start.get()
        end_raw = self.entry_time_end.get()
        include_audio = self.var_include_audio.get()

        def worker():
            if download_youtube_clip(url, start_raw, end_raw, save_path, include_audio=include_audio):
                self.lbl_status.config(text=f"✅ 저장 완료: {filename}")
            else:
                self.lbl_status.config(text="❌ 다운로드 실패")
        
        threading.Thread(target=worker, daemon=True).start()

    def prev_scene(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self.load_scene()

    def next_scene(self):
        self.current_idx += 1
        self.load_scene()

# ==========================================
# 4. 메인 실행
# ==========================================
def select_project_sheet(worksheets):
    go_sheets = [ws for ws in worksheets if "go" in ws.title.lower()]
    if not go_sheets:
        print("❌ 'go'가 포함된 시트가 없습니다.")
        return None, None
    
    # === [자동 선택 로직] ===
    auto_sheet_file = AUTO_SHEET_FILE
    selected_sheet_name = None
    if os.path.exists(auto_sheet_file):
        try:
            with open(auto_sheet_file, 'r', encoding='utf-8') as f:
                selected_sheet_name = f.read().strip()
                print(f"🤖 [Auto] 시트 자동 선택됨: {selected_sheet_name}")
        except: pass
    # ========================
    
    print("\n" + "="*40)
    print(" 🎬 [SourceHunter] 작업할 시트를 선택하세요")
    print("="*40)
    for i, ws in enumerate(go_sheets):
        print(f" [{i+1}] {ws.title}")
    
    # [자동 매칭] --------------------------------
    if selected_sheet_name:
        for ws in go_sheets:
            if ws.title == selected_sheet_name:
                return ws, ws.title
    # ---------------------------------------------
    
    while True:
        try:
            sel = input("\n번호 입력 >> ").strip()
            idx = int(sel) - 1
            if 0 <= idx < len(go_sheets):
                return go_sheets[idx], go_sheets[idx].title
        except: pass
        print("올바른 번호를 입력하세요.")

def main():
    print("🚀 Source Hunter v8.3 (Precise Cut)")
    
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
    client = gspread.authorize(creds)
    sh = load_spreadsheet(client)
    
    target_sheet, sheet_name = select_project_sheet(sh.worksheets())
    if not target_sheet: return

    print(f"📂 타겟 프로젝트: {sheet_name}")
    print(f"📂 저장 경로: {os.path.join(OUTPUT_ROOT, sheet_name)}")

    all_values = target_sheet.get_all_values()
    
    grouped_scripts = {}
    row_mapping = []
    gid_cell_updates = []  # C열 자동 채우기용
    
    for i, row in enumerate(all_values):
        # 헤더 행 스킵
        if i == 0:
            continue
        
        # B열 script
        if len(row) < 2:
            continue
        script = row[1].strip()
        if not script:
            continue
        
        # C열 image_group (없으면 자동 생성)
        gid = ""
        if len(row) >= 3:
            gid = row[2].strip()
        
        if not gid:
            # A열 id를 우선 사용, 없으면 행 번호 기반으로 생성
            if len(row) >= 1 and row[0].strip():
                gid = row[0].strip()
            else:
                gid = str(i)  # 헤더 제외 실제 행 인덱스 기반
            
            # 시트 C열에 자동으로 채워 넣기 (1-based row, col=3)
            try:
                gid_cell_updates.append(gspread.Cell(i + 1, 3, gid))
            except Exception:
                pass
        
        if gid:
            if gid not in grouped_scripts:
                grouped_scripts[gid] = []
                row_mapping.append(gid)
            grouped_scripts[gid].append(script)
    
    # 모아둔 C열(image_group) 값 일괄 업데이트
    if gid_cell_updates:
        try:
            target_sheet.update_cells(gid_cell_updates)
            print(f"✅ image_group(C열) 자동 채움: {len(gid_cell_updates)}개 행")
        except Exception as e:
            print(f"⚠️ image_group 자동 채움 실패 (계속 진행): {e}")
    
    scenarios = []
    seen = set()
    for gid in row_mapping:
        if gid in seen: continue
        seen.add(gid)
        full_script = " ".join(grouped_scripts[gid])
        scenarios.append({'group_id': gid, 'script': full_script})

    root = tk.Tk()
    app = SourceHunterRemote(root, scenarios, sheet_name)
    root.mainloop()

if __name__ == "__main__":
    main()