import os
import glob
import re
from PIL import Image
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==========================================
# 1. 설정 및 경로 정의
# ==========================================
JSON_KEY_FILE = r"C:\YtFactory9\_System\02_Key\service_account.json"
SHEET_URL_FILE = r"C:\YtFactory9\_System\00_Engine\YtFactory9_URL.txt"

# ==========================================
# 2. 블랙바 레이아웃 적용 함수
# ==========================================
def apply_black_bars(image_path, output_path):
    """
    1:1 이미지를 1080x1920 블랙바 레이아웃으로 변환
    
    Args:
        image_path: 처리할 이미지 파일 경로
        output_path: 저장할 파일 경로
    
    Returns:
        bool: 성공 여부
    """
    try:
        # 1. 원본 이미지 로드
        original_img = Image.open(image_path)
        original_width, original_height = original_img.size
        
        # 이미 블랙바가 적용된 이미지인지 확인 (1080x1920 크기)
        if original_width == 1080 and original_height == 1920:
            print(f"   ⏭️ 이미 블랙바 레이아웃이 적용된 이미지입니다. (1080x1920) - 스킵")
            return True
        
        # 2. 1080x1920 검정 배경 생성
        final_img = Image.new('RGB', (1080, 1920), (0, 0, 0))
        
        # 3. 1:1 이미지를 너비 1080에 맞춰 리사이즈 (비율 유지)
        target_width = 1080
        # 비율 유지하면서 리사이즈
        target_height = int(original_height * (target_width / original_width))
        resized_img = original_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        
        # 4. 검정 배경의 중앙(y=420 위치)에 합성
        # y=420은 상단에서 420픽셀 아래 위치 (중앙 정렬)
        paste_y = 420
        # 가로 중앙 정렬
        paste_x = (1080 - target_width) // 2
        
        final_img.paste(resized_img, (paste_x, paste_y))
        
        # 5. 새 파일명으로 저장
        final_img.save(output_path, 'PNG', quality=95)
        print(f"   🎨 블랙바 레이아웃 적용 완료 (1080x1920)")
        return True
    except Exception as e:
        print(f"   ⚠️ 블랙바 레이아웃 적용 실패: {e}")
        return False


# ==========================================
# 3. 시트 관련 함수
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


# ==========================================
# 4. 폴더 내 이미지 변환 함수
# ==========================================
def convert_images_in_folder(folder_path):
    """
    폴더 내의 모든 이미지 파일을 블랙바 레이아웃으로 변환
    파일명이 숫자로만 되어있으면 {숫자}_image_group.png로 변경
    
    Args:
        folder_path: 이미지가 있는 폴더 경로
    
    Returns:
        tuple: (성공 개수, 실패 개수)
    """
    if not os.path.exists(folder_path):
        print(f"❌ 폴더를 찾을 수 없습니다: {folder_path}")
        return (0, 0)
    
    # 지원하는 이미지 확장자
    image_extensions = ['.png', '.jpg', '.jpeg', '.webp', '.bmp']
    
    # 폴더 내의 모든 이미지 파일 찾기
    image_files = []
    for ext in image_extensions:
        # 대소문자 모두 검색
        pattern_lower = os.path.join(folder_path, f"*{ext}")
        pattern_upper = os.path.join(folder_path, f"*{ext.upper()}")
        image_files.extend(glob.glob(pattern_lower))
        image_files.extend(glob.glob(pattern_upper))
    
    # 중복 제거
    image_files = list(set(image_files))
    
    if not image_files:
        print(f"⚠️ 폴더 내에 이미지 파일을 찾을 수 없습니다: {folder_path}")
        return (0, 0)
    
    print(f"📋 발견된 이미지 파일: {len(image_files)}개")
    print(f"📂 폴더: {folder_path}\n")
    
    success_count = 0
    fail_count = 0
    
    for idx, image_path in enumerate(image_files, 1):
        filename = os.path.basename(image_path)
        filename_no_ext = os.path.splitext(filename)[0]  # 확장자 제거
        
        # 파일명이 숫자로만 되어있는지 확인
        if filename_no_ext.isdigit():
            # {숫자}_image_group.png 형식으로 변경
            new_filename = f"{filename_no_ext}_image_group.png"
            output_path = os.path.join(folder_path, new_filename)
            
            # 이미 변환된 파일이 존재하면 스킵
            if os.path.exists(output_path):
                print(f"[{idx}/{len(image_files)}] {filename} → {new_filename} (이미 존재) ⏭️ 스킵")
                continue
            
            print(f"[{idx}/{len(image_files)}] {filename} → {new_filename}", end=" ")
            
            if apply_black_bars(image_path, output_path):
                success_count += 1
                print(f"✅ 완료")
            else:
                fail_count += 1
                print(f"❌ 실패")
        else:
            # 숫자로만 되어있지 않으면 기존 파일명 유지
            print(f"[{idx}/{len(image_files)}] {filename}", end=" ")
            
            if apply_black_bars(image_path, image_path):
                success_count += 1
                print(f"✅ 완료")
            else:
                fail_count += 1
                print(f"❌ 실패")
    
    return (success_count, fail_count)


# ==========================================
# 5. 메인 실행
# ==========================================
def main():
    print("="*50)
    print("🚀 쇼츠 이미지컨버터 v1.0")
    print("   폴더 내 이미지를 블랙바 레이아웃(1080x1920)으로 변환합니다")
    print("="*50)
    print()
    
    # 1. 구글 시트 접속
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_name(JSON_KEY_FILE, scope)
        client = gspread.authorize(creds)
        doc = load_spreadsheet(client)
    except Exception as e:
        print(f"❌ 시트 접속 실패: {e}")
        return

    # 2. 'go'가 들어간 시트 찾기 & 사용자 선택
    all_worksheets = doc.worksheets()
    go_sheets = [ws for ws in all_worksheets if "go" in ws.title.lower()]

    if not go_sheets:
        print("❌ 'go'가 포함된 시트(예: 15go)를 찾을 수 없습니다!")
        return

    print("\n" + "="*40)
    print(" 🎨 [쇼츠 이미지컨버터] 작업할 시트를 선택하세요")
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
            else:
                print("⚠️ 올바른 번호를 입력하세요.")
        except:
            print("⚠️ 숫자를 입력하세요.")

    print(f"✅ 선택된 시트: '{selected_sheet.title}'")

    # 3. 시트 이름에서 채널명 추출 및 폴더 경로 생성
    sheet_title = selected_sheet.title
    channel_match = re.search(r'Ch\d+', sheet_title)
    if not channel_match:
        print(f"❌ 시트 이름에서 채널명을 추출할 수 없습니다: {sheet_title}")
        return
    channel_name = channel_match.group(0)  # 예: "Ch01"
    
    # 출력 경로: C:\YtFactory9\{channel_name}\03_Output\{sheet_title}
    folder_path = f"C:\\YtFactory9\\{channel_name}\\03_Output\\{sheet_title}"
    
    if not os.path.exists(folder_path):
        print(f"❌ 폴더를 찾을 수 없습니다: {folder_path}")
        return
    
    print(f"📂 타겟 폴더: {folder_path}")
    print()
    
    # 이미지 변환 실행
    success_count, fail_count = convert_images_in_folder(folder_path)
    
    # 결과 출력
    print()
    print("="*50)
    print("📊 변환 결과")
    print("="*50)
    print(f"✅ 성공: {success_count}개")
    print(f"❌ 실패: {fail_count}개")
    print(f"📋 총 처리: {success_count + fail_count}개")
    print("="*50)


if __name__ == "__main__":
    main()

