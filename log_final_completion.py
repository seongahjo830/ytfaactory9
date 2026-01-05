"""ImageMaker YtFactory3 방식 완전 교체 작업 완료 로그"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '_System', '03_Co_Tools개발중'))

from NotionTool import create_database_entry
from datetime import datetime

# 데이터베이스 ID
DB_ID_RAW = "2d8ceb2d2ad8800c9f76fd47dad66e7d"
DB_ID = f"{DB_ID_RAW[:8]}-{DB_ID_RAW[8:12]}-{DB_ID_RAW[12:16]}-{DB_ID_RAW[16:20]}-{DB_ID_RAW[20:]}"

def log_final_completion():
    """최종 완료 로그 기록"""
    work_log = """✅ YtFactory9 ImageMaker.py 완전히 YtFactory3 방식으로 교체 완료!

📋 주요 변경 사항:

1. ✅ 프롬프트 생성 방식 변경
   - 일괄 생성(병렬 처리) 제거
   - YtFactory3 방식: 각 그룹을 순차적으로 처리하면서 필요할 때 프롬프트 생성
   - KeyManager 제거, 단순한 api_keys 순차 시도 방식
   - generate_prompt_text 함수를 YtFactory3 방식으로 완전 교체

2. ✅ 이미지 생성 방식 변경
   - generate_image_file 함수를 YtFactory3 구버전 방식으로 교체
   - KeyManager 제거, 단순한 키 순차 시도 방식으로 변경
   - LAST_SUCCESSFUL_KEY 전역 변수 사용
   - 성공한 키를 우선 사용하는 로직

3. ✅ 메인 루프 변경
   - 복잡한 사이클 재시도 로직 제거
   - YtFactory3 방식: 단순한 순차 처리 루프
   - 각 그룹을 하나씩 처리하면서 프롬프트 생성 → 이미지 생성

4. ✅ 유지된 기능
   ✅ 시트 참조 방식 그대로 유지
   ✅ Flux, Fal 등 다른 이미지 생성 방식 그대로 유지
   ✅ 미드트로/아웃트로 비디오 복사 기능 유지

5. ❌ 제거된 기능
   ❌ 프롬프트 일괄 생성 (prepare_prompts_batch)
   ❌ 이미지 병렬 생성 (process_images_parallel)
   ❌ Gemini 이미지 생성에서 KeyManager 사용
   ❌ 복잡한 키 상태 관리 (Alive/Waiting/Dead)
   ❌ 모델 가용성 추적
   ❌ ThreadPoolExecutor를 사용한 병렬 처리

📝 작업 완료 시간: {time_str}
""".format(time_str=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    entry = create_database_entry(
        DB_ID,
        {
            "이름": {
                "title": [{
                    "text": {
                        "content": f"ImageMaker 완전 YtFactory3 방식 교체 완료 - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
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
        print("✅ Notion에 최종 완료 로그 기록 완료!")
        print(f"   항목 ID: {entry.get('id', 'N/A')}")
        return True
    else:
        print("❌ Notion 작업 로그 기록 실패")
        return False

if __name__ == "__main__":
    success = log_final_completion()
    sys.exit(0 if success else 1)








