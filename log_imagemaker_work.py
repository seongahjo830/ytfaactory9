"""ImageMaker 작업 완료 로그를 Notion에 기록"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_System', '03_Co_Tools개발중'))

from NotionTool import create_database_entry
from datetime import datetime

# 데이터베이스 ID
DB_ID_RAW = "2d8ceb2d2ad8800c9f76fd47dad66e7d"
DB_ID = f"{DB_ID_RAW[:8]}-{DB_ID_RAW[8:12]}-{DB_ID_RAW[12:16]}-{DB_ID_RAW[16:20]}-{DB_ID_RAW[20:]}"

def log_imagemaker_completion():
    """ImageMaker 작업 완료 로그 기록"""
    work_log = """✅ YtFactory9 ImageMaker.py Gemini 이미지 생성 방식 교체 작업 완료

📋 주요 변경 사항:

1. generate_image_file 함수 교체
   - YtFactory3 구버전 방식으로 완전 교체
   - KeyManager 제거, 단순한 키 순차 시도 방식으로 변경
   - LAST_SUCCESSFUL_KEY 전역 변수 사용
   - 성공한 키를 우선 사용하는 로직

2. 함수 시그니처 변경
   - 기존: generate_image_file(prompt, filename, key_manager, save_dir)
   - 변경: generate_image_file(prompt, filename, api_keys, save_dir)

3. 호출 부분 수정
   - process_images_parallel 함수에 api_keys 파라미터 추가
   - main 함수에서 api_keys 전달

4. 유지된 기능
   ✅ 시트 참조 방식 그대로 유지
   ✅ Flux, Fal 등 다른 이미지 생성 방식 그대로 유지
   ✅ KeyManager는 프롬프트 생성에만 계속 사용

5. 제거된 기능
   ❌ Gemini 이미지 생성에서 KeyManager 사용
   ❌ 복잡한 키 상태 관리 (Alive/Waiting/Dead)
   ❌ 모델 가용성 추적
   ❌ Responsible AI 위반 감지 (YtFactory3 방식에서는 단순 실패 처리)

📝 작업 완료 시간: {time_str}
""".format(time_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    entry = create_database_entry(
        DB_ID,
        {
            "이름": {
                "title": [{
                    "text": {
                        "content": f"ImageMaker Gemini 이미지 생성 방식 교체 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
    success = log_imagemaker_completion()
    sys.exit(0 if success else 1)

