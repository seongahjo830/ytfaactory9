"""Notion에 작업 로그 기록"""
from NotionTool import get_notion_client, create_database_entry, extract_page_id
from datetime import datetime

# 데이터베이스 URL
DB_URL = "https://www.notion.so/ytft9-2d8ceb2d2ad88087a8c4cb0b973e317e"

# 작업 내용
work_log = """
✅ 작업 완료: YtFactory9 ImageMaker.py Gemini 이미지 생성 방식 교체

주요 변경 사항:
1. generate_image_file 함수를 YtFactory3 구버전 방식으로 교체
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
   - 시트 참조 방식 그대로 유지
   - Flux, Fal 등 다른 이미지 생성 방식 그대로 유지
   - KeyManager는 프롬프트 생성에만 계속 사용

5. 제거된 기능
   - Gemini 이미지 생성에서 KeyManager 사용
   - 복잡한 키 상태 관리 (Alive/Waiting/Dead)
   - 모델 가용성 추적
   - Responsible AI 위반 감지 (YtFactory3 방식에서는 단순 실패 처리)
"""

if __name__ == "__main__":
    client = get_notion_client()
    if not client:
        print("❌ Notion 클라이언트 생성 실패")
        exit(1)
    
    db_id = extract_page_id(DB_URL)
    if not db_id:
        print("❌ 데이터베이스 ID 추출 실패")
        exit(1)
    
    entry = create_database_entry(
        db_id,
        {
            "이름": {
                "title": [{
                    "text": {
                        "content": f"ImageMaker Gemini 이미지 생성 방식 교체 작업 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    }
                }]
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
        print("✅ Notion 항목 추가 완료")
    else:
        print("❌ Notion 항목 추가 실패")








