"""ImageMaker 속도 개선 작업 로그"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_System', '03_Co_Tools개발중'))

from NotionTool import create_database_entry
from datetime import datetime

# 데이터베이스 ID
DB_ID_RAW = "2d8ceb2d2ad8800c9f76fd47dad66e7d"
DB_ID = f"{DB_ID_RAW[:8]}-{DB_ID_RAW[8:12]}-{DB_ID_RAW[12:16]}-{DB_ID_RAW[16:20]}-{DB_ID_RAW[20:]}"

def log_speed_fix():
    """속도 개선 작업 로그 기록"""
    work_log = """✅ ImageMaker.py 속도 개선 완료 (YtFactory3 방식)

📋 수정 사항:

1. ✅ F열/J열 정리 기능 선택적 활성화
   - 기본값: 비활성화 (빠른 실행)
   - 환경변수 YTF_CLEANUP_COLUMNS=1로 활성화 가능
   - 배치 크기 증가: 10개 -> 100개 (API 호출 최소화)
   - 대기 시간 감소: 0.5초 -> 0.2초

2. ✅ retry_on_quota_exceeded 제거
   - YtFactory3 방식: 60초 대기 없이 직접 시도
   - 시트 읽기/쓰기 시 retry_on_quota_exceeded 제거
   - 에러 발생 시 스킵하고 계속 진행 (빠른 실패)

3. ✅ 제거된 retry_on_quota_exceeded 사용:
   - selected_sheet.get_all_values() - 직접 시도
   - selected_sheet.cell() - 직접 시도
   - selected_sheet.update_cell() - 직접 시도
   - selected_sheet.update_cells() - 직접 시도

4. ✅ 유지된 retry_on_quota_exceeded:
   - load_spreadsheet() - 시트 접속 시에만 사용 (필수)

5. ✅ 성능 개선
   - 60초 대기 제거로 빠른 실행
   - API 호출 최소화
   - 에러 발생 시에도 계속 진행

📝 작업 완료 시간: {time_str}
""".format(time_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    entry = create_database_entry(
        DB_ID,
        {
            "이름": {
                "title": [{
                    "text": {
                        "content": f"ImageMaker 속도 개선 (60초 대기 제거) - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
    success = log_speed_fix()
    sys.exit(0 if success else 1)








