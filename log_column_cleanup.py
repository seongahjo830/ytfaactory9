"""ImageMaker F열/J열 자동 정리 기능 추가 로그"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_System', '03_Co_Tools개발중'))

from NotionTool import create_database_entry
from datetime import datetime

# 데이터베이스 ID
DB_ID_RAW = "2d8ceb2d2ad8800c9f76fd47dad66e7d"
DB_ID = f"{DB_ID_RAW[:8]}-{DB_ID_RAW[8:12]}-{DB_ID_RAW[12:16]}-{DB_ID_RAW[16:20]}-{DB_ID_RAW[20:]}"

def log_column_cleanup():
    """F열/J열 자동 정리 기능 추가 로그 기록"""
    work_log = """✅ ImageMaker.py F열/J열 자동 정리 기능 추가 완료

📋 추가된 기능:

1. ✅ F열(promptABC) 자동 정리
   - 이미지 그룹의 첫 번째 행(대표행)만 F열 값 유지
   - 나머지 행의 F열이 채워져 있으면 자동으로 비우기
   - 시트에 일괄 업데이트 (10개씩 묶어서)

2. ✅ J열(imagetype) 자동 정리
   - 이미지 그룹의 첫 번째 행(대표행)만 J열 값 유지
   - 나머지 행의 J열이 채워져 있으면 자동으로 비우기
   - 시트에 일괄 업데이트 (10개씩 묶어서)

3. ✅ 정리 로직
   - 그룹화 완료 후 자동으로 F열과 J열 정리
   - 각 그룹의 첫 번째 행인지 확인 (row_mapping 사용)
   - 첫 번째 행이 아닌 행들의 F열(6번째 컬럼)과 J열(10번째 컬럼) 비우기
   - 배치 업데이트로 효율적 처리

4. ✅ 사용자 경험 개선
   - 정리 진행 상황 출력
   - 정리된 셀 개수 표시
   - 이미 정리되어 있으면 메시지 출력

📝 작업 완료 시간: {time_str}
""".format(time_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    entry = create_database_entry(
        DB_ID,
        {
            "이름": {
                "title": [{
                    "text": {
                        "content": f"ImageMaker F열/J열 자동 정리 기능 추가 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
    success = log_column_cleanup()
    sys.exit(0 if success else 1)








