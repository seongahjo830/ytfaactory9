"""
Google Sheets에 Ch01_50go 시트를 추가하고 데이터를 입력하는 스크립트
"""
import os
import csv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 설정
JSON_KEY_FILE = r"C:\YtFactory9\_System\02_Key\service_account.json"
SHEET_URL_FILE = r"C:\YtFactory9\_System\00_Engine\YtFactory9_URL.txt"

def load_spreadsheet(client):
    """Sheet_URL.txt 내용을 읽어서 스프레드시트에 접속"""
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

def create_sheet_with_data(sheet_name, data_rows):
    """
    Google Sheets에 새 시트를 생성하고 데이터를 입력
    
    Args:
        sheet_name: 시트 이름 (예: 'Ch01_50go')
        data_rows: 데이터 행 리스트 (헤더 포함)
                  예: [
                      ['id', 'script', 'image_group', 'duration', 'subtype', 'promptABC', '', 'image_prompt', 'voice', 'imagetype', 'sound', 'voice_tool', 'fal_RootImage'],
                      [1, '스크립트 내용', '1', '', 'Default', '돈경1', '0', '0', '돈경', 'gemini', '0', 'elevenlabs', '0'],
                      ...
                  ]
    """
    # Google Sheets 인증
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
    client = gspread.authorize(creds)
    
    # 스프레드시트 열기
    doc = load_spreadsheet(client)
    
    # 시트가 이미 존재하는지 확인
    try:
        sheet = doc.worksheet(sheet_name)
        print(f"[경고] 시트 '{sheet_name}'가 이미 존재합니다. 기존 시트를 사용합니다.")
        # 기존 시트를 비우고 새 데이터로 채우기
        sheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        # 새 시트 생성
        sheet = doc.add_worksheet(title=sheet_name, rows=1000, cols=13)
        print(f"[성공] 새 시트 '{sheet_name}'를 생성했습니다.")
    
    # 데이터 입력
    if data_rows:
        # 헤더와 데이터를 한 번에 입력
        sheet.update('A1', data_rows)
        print(f"[성공] {len(data_rows)}행의 데이터를 입력했습니다.")
    else:
        # 헤더만 입력
        headers = ['id', 'script', 'image_group', 'duration', 'subtype', 'promptABC', '', 'image_prompt', 'voice', 'imagetype', 'sound', 'voice_tool', 'fal_RootImage']
        sheet.update('A1', [headers])
        print(f"[성공] 헤더만 입력했습니다. 데이터를 추가해주세요.")
    
    # 시트 URL 반환
    sheet_url = f"https://docs.google.com/spreadsheets/d/{doc.id}/edit#gid={sheet.id}"
    print(f"\n[시트 URL] {sheet_url}")
    return sheet_url

def parse_table_data(text_data):
    """
    텍스트 형식의 표 데이터를 파싱하여 리스트로 변환
    마크다운 테이블 형식이나 탭/파이프 구분 형식을 지원
    """
    rows = []
    lines = text_data.strip().split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 마크다운 테이블 형식 (|로 구분)
        if '|' in line:
            # 헤더 구분선 스킵 (|---|---|)
            if line.replace('|', '').replace('-', '').replace(':', '').strip() == '':
                continue
            # 파이프로 구분된 데이터 파싱
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            # 첫 번째와 마지막이 비어있을 수 있음
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]
            if cells:
                rows.append(cells)
        # 탭 구분 형식
        elif '\t' in line:
            cells = [cell.strip() for cell in line.split('\t')]
            rows.append(cells)
        # 쉼표 구분 형식 (CSV)
        elif ',' in line and not line.startswith('#'):
            cells = [cell.strip().strip('"') for cell in line.split(',')]
            rows.append(cells)
    
    return rows

if __name__ == "__main__":
    import sys
    
    # 사용 예시
    sheet_name = "Ch01_50go"
    
    # 헤더 정의
    headers = ['id', 'script', 'image_group', 'duration', 'subtype', 'promptABC', '', 'image_prompt', 'voice', 'imagetype', 'sound', 'voice_tool', 'fal_RootImage']
    
    # 데이터 파일 경로 확인 (명령줄 인자 또는 기본값)
    data_file = None
    if len(sys.argv) > 1:
        data_file = sys.argv[1]
    else:
        # 기본 경로들 확인
        default_paths = [
            r"C:\YtFactory9\Ch01_50go_data.txt",
            r"C:\YtFactory9\Ch01_50go_data.csv",
            r"C:\YtFactory9\_System\04_Co_Asset\Ch01_50go_data.txt",
        ]
        for path in default_paths:
            if os.path.exists(path):
                data_file = path
                break
    
    data_rows = [headers]
    
    # 데이터 파일이 있으면 읽기
    if data_file and os.path.exists(data_file):
        print(f"[데이터 파일] {data_file}에서 데이터를 읽습니다...")
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                text_data = f.read()
            
            parsed_rows = parse_table_data(text_data)
            if parsed_rows:
                # 헤더가 포함되어 있으면 제거하고 우리 헤더 사용
                if len(parsed_rows) > 0:
                    # 첫 행이 헤더인지 확인 (일반적으로 'id' 또는 숫자로 시작)
                    first_row = parsed_rows[0]
                    if len(first_row) > 0 and (first_row[0].lower() == 'id' or first_row[0].isdigit()):
                        # 첫 행이 헤더면 제거
                        if first_row[0].lower() == 'id':
                            parsed_rows = parsed_rows[1:]
                    
                    data_rows = [headers] + parsed_rows
                    print(f"[성공] {len(parsed_rows)}행의 데이터를 파싱했습니다.")
        except Exception as e:
            print(f"[경고] 데이터 파일 읽기 실패: {e}")
            print("[안내] 헤더만 생성합니다.")
    else:
        print("[안내] 데이터 파일을 찾을 수 없습니다. 헤더만 생성합니다.")
        print("[안내] 데이터를 추가하려면:")
        print("  1. 텍스트 파일에 데이터를 저장 (CSV, 탭 구분, 또는 마크다운 테이블 형식)")
        print("  2. python add_sheet_ch01_50go.py <파일경로> 실행")
    
    print(f"\n[시트 생성] '{sheet_name}' 시트를 생성합니다...")
    print("=" * 60)
    
    try:
        url = create_sheet_with_data(sheet_name, data_rows)
        print("\n" + "=" * 60)
        print(f"[완료] 시트가 생성되었습니다.")
        print(f"[링크] {url}")
        print("=" * 60)
    except Exception as e:
        print(f"[오류] 발생: {e}")
        import traceback
        traceback.print_exc()

