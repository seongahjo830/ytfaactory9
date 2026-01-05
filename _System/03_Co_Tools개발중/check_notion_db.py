"""Notion 데이터베이스 확인 및 항목 추가"""
from NotionTool import get_notion_client, create_database_entry, read_database_entries, extract_page_id
from datetime import datetime
import sys

# 데이터베이스 URL
DB_URL = "https://www.notion.so/ytft9-2d8ceb2d2ad88087a8c4cb0b973e317e"

def check_and_add_entry():
    """데이터베이스 확인 후 항목 추가"""
    client = get_notion_client()
    if not client:
        print("❌ Notion 클라이언트 생성 실패")
        return False
    
    db_id = extract_page_id(DB_URL)
    if not db_id:
        print("❌ 데이터베이스 ID 추출 실패")
        return False
    
    # 기존 항목 확인
    print("\n📋 기존 데이터베이스 항목 확인 중...")
    existing_entries = read_database_entries(db_id)
    
    if existing_entries:
        print(f"\n✅ 데이터베이스에 {len(existing_entries)}개 항목이 있습니다.")
        print("\n최근 5개 항목:")
        for i, entry in enumerate(existing_entries[:5], 1):
            props = entry.get('properties', {})
            name_prop = props.get('이름', {}).get('title', [])
            name = name_prop[0].get('plain_text', '제목 없음') if name_prop else '제목 없음'
            stage_prop = props.get('단계', {}).get('select', {})
            stage = stage_prop.get('name', '없음') if stage_prop else '없음'
            print(f"  {i}. {name} (단계: {stage})")
    else:
        print("⚠️ 데이터베이스에 항목이 없습니다.")
    
    # 새 항목 추가
    print("\n📝 새 항목 추가 중...")
    work_log = """✅ 작업 완료: YtFactory9 ImageMaker.py Gemini 이미지 생성 방식 교체

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
   - Responsible AI 위반 감지 (YtFactory3 방식에서는 단순 실패 처리)"""
    
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
        print("\n✅ Notion 항목 추가 완료!")
        print(f"   항목 ID: {entry.get('id', 'N/A')}")
        
        # 추가 확인: 다시 읽어서 확인
        print("\n🔄 추가 확인: 데이터베이스 다시 읽기...")
        updated_entries = read_database_entries(db_id)
        if updated_entries:
            latest_entry = updated_entries[0]  # 가장 최근 항목
            props = latest_entry.get('properties', {})
            name_prop = props.get('이름', {}).get('title', [])
            name = name_prop[0].get('plain_text', '제목 없음') if name_prop else '제목 없음'
            print(f"   최신 항목: {name}")
            if "ImageMaker Gemini" in name:
                print("   ✅ 확인 완료: 새 항목이 정상적으로 추가되었습니다!")
                return True
            else:
                print("   ⚠️ 경고: 새 항목이 최신 항목이 아닙니다.")
        return True
    else:
        print("\n❌ Notion 항목 추가 실패")
        return False

if __name__ == "__main__":
    success = check_and_add_entry()
    sys.exit(0 if success else 1)








