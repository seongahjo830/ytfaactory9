"""ImageMaker 열 사용 수정 작업 로그"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_System', '03_Co_Tools개발중'))

from NotionTool import create_database_entry
from datetime import datetime

# 데이터베이스 ID
DB_ID_RAW = "2d8ceb2d2ad8800c9f76fd47dad66e7d"
DB_ID = f"{DB_ID_RAW[:8]}-{DB_ID_RAW[8:12]}-{DB_ID_RAW[12:16]}-{DB_ID_RAW[16:20]}-{DB_ID_RAW[20:]}"

def log_column_fix():
    """열 사용 수정 작업 로그 기록"""
    work_log = """✅ ImageMaker.py 시트 열 사용 수정 완료

📋 수정 사항:

1. ✅ promptABC (F열) 처리 개선
   - 그룹 내 모든 행의 promptABC 값 확인
   - 그룹 내 첫 번째 행의 promptABC 값을 사용 (돈경1, 돈경2, 돈경3 등)
   - 그룹 내 promptABC가 다르면 경고 메시지 출력
   - 각 행의 promptABC 값을 개별적으로 저장하여 추적

2. ✅ imagetype (J열) 처리 개선
   - 그룹 내 모든 행의 imagetype 값 확인
   - 그룹 내 첫 번째 행의 imagetype 값을 사용 (gemini/flux/fal)
   - 그룹 내 imagetype이 다르면 경고 메시지 출력
   - flux일 때 flux로 생성, fal일 때 fal로 생성하도록 수정
   - 각 행의 imagetype 값을 개별적으로 저장하여 추적

3. ✅ 코드 구조 개선
   - group_rows_info 딕셔너리 추가: 각 그룹의 모든 행 정보 저장
   - 각 행의 row_idx, promptABC, imagetype 정보 저장
   - 그룹 처리 시 첫 번째 행의 값을 대표값으로 사용

4. ✅ 디버깅 정보 추가
   - 그룹 처리 시 promptABC와 imagetype 값 출력
   - 그룹 내 값이 다를 때 경고 메시지 출력

📝 작업 완료 시간: {time_str}
""".format(time_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    entry = create_database_entry(
        DB_ID,
        {
            "이름": {
                "title": [{
                    "text": {
                        "content": f"ImageMaker promptABC/imagetype 처리 수정 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    }
                }]
            },
            "완료": {
                "checkbox": True
            },
            "단계": {
                "select": {
                    "name": "완료"
                }
            },
            "내용요약": {
                "rich_text": [{
                    "text": {
                        "content": work_log
                    }
                }]
            }
        }
    )
    
    if entry:
        print("✅ Notion에 작업 로그 기록 완료!")
        print(f"   항목 ID: {entry.get('id', 'N/A')}")
        return True
    else:
        print("❌ Notion 작업 로그 기록 실패")
        return False

if __name__ == "__main__":
    success = log_column_fix()
    sys.exit(0 if success else 1)








