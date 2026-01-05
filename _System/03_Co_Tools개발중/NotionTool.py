"""
Notion API 연동 도구
페이지 생성, 읽기, 수정 기능 제공
"""

import os
import re
from notion_client import Client
from datetime import datetime


# ==========================================
# 1. API 키 로드
# ==========================================
def get_notion_key():
    """
    Notion API 키 로드
    1) 환경변수 NOTION_API_KEY
    2) KeyKeyNotion.txt 파일
    """
    env_key = os.getenv("NOTION_API_KEY")
    if env_key and len(env_key) > 10:
        print(f"💳 Notion 키 로드 (.env): {env_key[:5]}...{env_key[-5:]}")
        return env_key

    key_file = r"C:\YtFactory9\_System\02_Key\KeyKeyNotion.txt"
    if os.path.exists(key_file):
        try:
            with open(key_file, 'r', encoding='utf-8') as f:
                key = f.read().strip()
                # ntn_ 로 시작하는 키 찾기
                found = re.findall(r'(ntn_[a-zA-Z0-9_-]{40,})', key)
                if found:
                    key = found[0]
                if len(key) > 10:
                    print(f"💳 Notion 키 로드 (KeyKeyNotion.txt): {key[:5]}...{key[-5:]}")
                    return key
        except Exception as e:
            print(f"❌ 키 파일 읽기 오류: {e}")

    print("❌ Notion 키를 찾을 수 없습니다. (.env의 NOTION_API_KEY 또는 KeyKeyNotion.txt)")
    return None


# ==========================================
# 2. Notion 클라이언트 초기화
# ==========================================
def get_notion_client():
    """Notion API 클라이언트 생성"""
    api_key = get_notion_key()
    if not api_key:
        return None
    return Client(auth=api_key)


# ==========================================
# 3. 페이지 ID 추출
# ==========================================
def extract_page_id(url_or_id):
    """
    Notion URL에서 페이지 ID 추출
    입력: URL 또는 페이지 ID
    출력: 하이픈이 포함된 페이지 ID (예: 2d8ceb2d-2ad8-80c6-9f20-ddd2c53ca6ff)
    """
    if not url_or_id:
        return None
    
    # 이미 하이픈이 포함된 ID 형식인 경우
    if len(url_or_id) == 36 and url_or_id.count('-') == 4:
        return url_or_id
    
    # URL에서 ID 추출
    if 'notion.so' in url_or_id:
        # URL 형식: https://www.notion.so/ytft-2d8ceb2d2ad880c69f20ddd2c53ca6ff
        match = re.search(r'([a-f0-9]{8})([a-f0-9]{4})([a-f0-9]{4})([a-f0-9]{4})([a-f0-9]{12})', url_or_id)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}-{match.group(4)}-{match.group(5)}"
    
    # 하이픈 없는 ID 형식인 경우
    if len(url_or_id) == 32:
        return f"{url_or_id[:8]}-{url_or_id[8:12]}-{url_or_id[12:16]}-{url_or_id[16:20]}-{url_or_id[20:]}"
    
    return url_or_id


# ==========================================
# 4. 페이지 읽기
# ==========================================
def read_page(page_id_or_url):
    """
    Notion 페이지 읽기
    
    Args:
        page_id_or_url: 페이지 ID 또는 URL
    
    Returns:
        페이지 내용 (딕셔너리)
    """
    client = get_notion_client()
    if not client:
        return None
    
    page_id = extract_page_id(page_id_or_url)
    if not page_id:
        print("❌ 유효하지 않은 페이지 ID 또는 URL입니다.")
        return None
    
    try:
        page = client.pages.retrieve(page_id)
        print(f"✅ 페이지 읽기 성공: {page.get('properties', {}).get('title', {}).get('title', [{}])[0].get('plain_text', '제목 없음')}")
        return page
    except Exception as e:
        print(f"❌ 페이지 읽기 실패: {e}")
        return None


# ==========================================
# 5. 페이지 생성
# ==========================================
def create_page(parent_page_id_or_url, title, content=None):
    """
    Notion 페이지 생성
    
    Args:
        parent_page_id_or_url: 부모 페이지 ID 또는 URL
        title: 새 페이지 제목
        content: 페이지 내용 (리스트, 각 항목은 블록 타입)
    
    Returns:
        생성된 페이지 정보
    """
    client = get_notion_client()
    if not client:
        return None
    
    parent_id = extract_page_id(parent_page_id_or_url)
    if not parent_id:
        print("❌ 유효하지 않은 부모 페이지 ID 또는 URL입니다.")
        return None
    
    try:
        # 페이지 속성 설정
        properties = {
            "title": {
                "title": [
                    {
                        "text": {
                            "content": title
                        }
                    }
                ]
            }
        }
        
        # 페이지 생성
        new_page = client.pages.create(
            parent={"page_id": parent_id},
            properties=properties
        )
        
        print(f"✅ 페이지 생성 성공: {title}")
        
        # 내용이 있으면 추가
        if content:
            add_blocks(new_page['id'], content)
        
        return new_page
    except Exception as e:
        print(f"❌ 페이지 생성 실패: {e}")
        return None


# ==========================================
# 6. 블록 추가
# ==========================================
def add_blocks(page_id_or_url, blocks):
    """
    페이지에 블록 추가
    
    Args:
        page_id_or_url: 페이지 ID 또는 URL
        blocks: 추가할 블록 리스트
    
    Returns:
        성공 여부
    """
    client = get_notion_client()
    if not client:
        return False
    
    page_id = extract_page_id(page_id_or_url)
    if not page_id:
        print("❌ 유효하지 않은 페이지 ID 또는 URL입니다.")
        return False
    
    try:
        client.blocks.children.append(block_id=page_id, children=blocks)
        print(f"✅ 블록 추가 성공: {len(blocks)}개")
        return True
    except Exception as e:
        print(f"❌ 블록 추가 실패: {e}")
        return False


# ==========================================
# 7. 텍스트 블록 생성 헬퍼
# ==========================================
def create_text_block(text):
    """일반 텍스트 블록 생성"""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }


def create_heading_block(text, level=1):
    """제목 블록 생성 (level: 1=제목1, 2=제목2, 3=제목3)"""
    heading_type = f"heading_{level}"
    return {
        "object": "block",
        "type": heading_type,
        heading_type: {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }


def create_bullet_list_block(text):
    """불릿 리스트 블록 생성"""
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }


def create_numbered_list_block(text):
    """번호 리스트 블록 생성"""
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }


def create_code_block(code, language="plain text"):
    """코드 블록 생성"""
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": code
                    }
                }
            ],
            "language": language
        }
    }


def create_quote_block(text):
    """인용 블록 생성"""
    return {
        "object": "block",
        "type": "quote",
        "quote": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }


def create_toggle_block(text, children=None):
    """토글 블록 생성"""
    block = {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [
                {
                    "type": "text",
                    "text": {
                        "content": text
                    }
                }
            ]
        }
    }
    if children:
        block["toggle"]["children"] = children
    return block


# ==========================================
# 8. 페이지 속성 업데이트
# ==========================================
def update_page_properties(page_id_or_url, properties):
    """
    페이지 속성 업데이트
    
    Args:
        page_id_or_url: 페이지 ID 또는 URL
        properties: 업데이트할 속성 딕셔너리
    
    Returns:
        성공 여부
    """
    client = get_notion_client()
    if not client:
        return False
    
    page_id = extract_page_id(page_id_or_url)
    if not page_id:
        print("❌ 유효하지 않은 페이지 ID 또는 URL입니다.")
        return False
    
    try:
        client.pages.update(page_id=page_id, properties=properties)
        print("✅ 페이지 속성 업데이트 성공")
        return True
    except Exception as e:
        print(f"❌ 페이지 속성 업데이트 실패: {e}")
        return False


# ==========================================
# 9. 페이지 제목 변경
# ==========================================
def update_page_title(page_id_or_url, new_title):
    """페이지 제목 변경"""
    properties = {
        "title": {
            "title": [
                {
                    "text": {
                        "content": new_title
                    }
                }
            ]
        }
    }
    return update_page_properties(page_id_or_url, properties)


# ==========================================
# 10. 블록 업데이트
# ==========================================
def update_block(block_id, new_content):
    """
    블록 내용 업데이트
    
    Args:
        block_id: 블록 ID
        new_content: 새로운 블록 내용 (블록 객체)
    
    Returns:
        성공 여부
    """
    client = get_notion_client()
    if not client:
        return False
    
    try:
        client.blocks.update(block_id=block_id, **new_content)
        print("✅ 블록 업데이트 성공")
        return True
    except Exception as e:
        print(f"❌ 블록 업데이트 실패: {e}")
        return False


# ==========================================
# 11. 블록 삭제
# ==========================================
def delete_block(block_id):
    """
    블록 삭제
    
    Args:
        block_id: 블록 ID
    
    Returns:
        성공 여부
    """
    client = get_notion_client()
    if not client:
        return False
    
    try:
        client.blocks.delete(block_id=block_id)
        print("✅ 블록 삭제 성공")
        return True
    except Exception as e:
        print(f"❌ 블록 삭제 실패: {e}")
        return False


# ==========================================
# 12. 페이지의 모든 블록 읽기
# ==========================================
def read_all_blocks(page_id_or_url):
    """
    페이지의 모든 블록 읽기
    
    Args:
        page_id_or_url: 페이지 ID 또는 URL
    
    Returns:
        블록 리스트
    """
    client = get_notion_client()
    if not client:
        return None
    
    page_id = extract_page_id(page_id_or_url)
    if not page_id:
        print("❌ 유효하지 않은 페이지 ID 또는 URL입니다.")
        return None
    
    try:
        blocks = []
        cursor = None
        
        while True:
            if cursor:
                response = client.blocks.children.list(block_id=page_id, start_cursor=cursor)
            else:
                response = client.blocks.children.list(block_id=page_id)
            
            blocks.extend(response.get('results', []))
            
            if not response.get('has_more'):
                break
            cursor = response.get('next_cursor')
        
        print(f"✅ 블록 읽기 성공: {len(blocks)}개")
        return blocks
    except Exception as e:
        print(f"❌ 블록 읽기 실패: {e}")
        return None


# ==========================================
# 13. 페이지 내용을 텍스트로 추출
# ==========================================
def extract_page_text(page_id_or_url):
    """
    페이지의 모든 텍스트 내용 추출
    
    Args:
        page_id_or_url: 페이지 ID 또는 URL
    
    Returns:
        텍스트 내용 (문자열)
    """
    blocks = read_all_blocks(page_id_or_url)
    if not blocks:
        return ""
    
    texts = []
    for block in blocks:
        block_type = block.get('type')
        rich_text = block.get(block_type, {}).get('rich_text', [])
        
        for text_obj in rich_text:
            text_content = text_obj.get('plain_text', '')
            if text_content:
                texts.append(text_content)
    
    return '\n'.join(texts)


# ==========================================
# 14. 데이터베이스에 항목 추가
# ==========================================
def create_database_entry(database_id_or_url, properties):
    """
    Notion 데이터베이스에 항목 추가
    
    Args:
        database_id_or_url: 데이터베이스 ID 또는 URL (하이픈 포함/미포함 모두 가능)
        properties: 항목 속성 딕셔너리
            예: {
                "이름": {"title": [{"text": {"content": "항목 이름"}}]},
                "완료": {"checkbox": True},
                "단계": {"select": {"name": "진행중"}},
                "내용요약": {"rich_text": [{"text": {"content": "내용"}}]}
            }
    
    Returns:
        생성된 항목 정보 또는 None
    """
    client = get_notion_client()
    if not client:
        return None
    
    # 데이터베이스 ID 처리 (URL이면 추출, 이미 ID면 하이픈 추가)
    if database_id_or_url.startswith("http"):
        database_id = extract_page_id(database_id_or_url)
    else:
        database_id = database_id_or_url.strip()
        # 하이픈이 없고 32자리면 하이픈 추가
        if len(database_id) == 32 and '-' not in database_id:
            database_id = f"{database_id[:8]}-{database_id[8:12]}-{database_id[12:16]}-{database_id[16:20]}-{database_id[20:]}"
    
    if not database_id:
        print("❌ 유효하지 않은 데이터베이스 ID 또는 URL입니다.")
        return None
    
    try:
        new_entry = client.pages.create(
            parent={"database_id": database_id},
            properties=properties
        )
        print(f"✅ 데이터베이스 항목 추가 성공")
        return new_entry
    except Exception as e:
        print(f"❌ 데이터베이스 항목 추가 실패: {e}")
        return None


# ==========================================
# 15. 데이터베이스 항목 읽기
# ==========================================
def read_database_entries(database_id_or_url, filter_dict=None, sorts=None, page_size=100):
    """
    Notion 데이터베이스의 항목들을 읽기
    
    Args:
        database_id_or_url: 데이터베이스 ID 또는 URL
        filter_dict: 필터 딕셔너리 (선택적)
        sorts: 정렬 딕셔너리 리스트 (선택적)
        page_size: 한 번에 가져올 항목 수 (기본값: 100)
    
    Returns:
        항목 리스트 또는 None
    """
    client = get_notion_client()
    if not client:
        return None
    
    database_id = extract_page_id(database_id_or_url)
    if not database_id:
        print("❌ 유효하지 않은 데이터베이스 ID 또는 URL입니다.")
        return None
    
    try:
        # 데이터베이스 ID 처리 (URL이면 추출, 이미 ID면 하이픈 추가)
        if database_id_or_url.startswith("http"):
            database_id = extract_page_id(database_id_or_url)
        else:
            database_id = database_id_or_url.strip()
            # 하이픈이 없고 32자리면 하이픈 추가
            if len(database_id) == 32 and '-' not in database_id:
                database_id = f"{database_id[:8]}-{database_id[8:12]}-{database_id[12:16]}-{database_id[16:20]}-{database_id[20:]}"
        
        if not database_id:
            print("❌ 유효하지 않은 데이터베이스 ID 또는 URL입니다.")
            return None
        
        all_entries = []
        cursor = None
        
        while True:
            # notion-client의 올바른 사용법: databases.query() 메서드 사용
            # 하지만 일부 버전에서는 없을 수 있으므로 try-except로 처리
            query_kwargs = {"database_id": database_id}
            if page_size:
                query_kwargs["page_size"] = page_size
            if filter_dict:
                query_kwargs["filter"] = filter_dict
            if sorts:
                query_kwargs["sorts"] = sorts
            if cursor:
                query_kwargs["start_cursor"] = cursor
            
            # notion-client 2.x에서는 query() 메서드가 있어야 함
            # 없으면 버전 문제이므로 에러 발생
            if hasattr(client.databases, 'query'):
                response = client.databases.query(**query_kwargs)
            else:
                # 구버전 호환: search API 사용 시도
                raise AttributeError("databases.query() 메서드를 사용할 수 없습니다. notion-client 버전을 확인하세요.")
            
            all_entries.extend(response.get('results', []))
            
            if not response.get('has_more'):
                break
            cursor = response.get('next_cursor')
        
        print(f"✅ 데이터베이스 항목 읽기 성공: {len(all_entries)}개")
        return all_entries
    except AttributeError as e:
        print(f"❌ 데이터베이스 항목 읽기 실패: {e}")
        print("   💡 notion-client를 최신 버전으로 업데이트하세요: pip install --upgrade notion-client")
        return None
    except Exception as e:
        print(f"❌ 데이터베이스 항목 읽기 실패: {e}")
        return None


# ==========================================
# 16. 예제 사용법
# ==========================================
if __name__ == "__main__":
    # 기본 페이지 URL
    BASE_PAGE_URL = "https://www.notion.so/ytft-2d8ceb2d2ad880c69f20ddd2c53ca6ff"
    
    print("=" * 50)
    print("Notion API 연동 도구 테스트")
    print("=" * 50)
    
    # 1. 페이지 읽기
    print("\n1. 페이지 읽기 테스트")
    page = read_page(BASE_PAGE_URL)
    if page:
        print(f"   페이지 ID: {page.get('id')}")
    
    # 2. 새 페이지 생성
    print("\n2. 새 페이지 생성 테스트")
    new_page = create_page(
        BASE_PAGE_URL,
        f"테스트 페이지 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        [
            create_heading_block("제목 1", level=1),
            create_text_block("이것은 일반 텍스트입니다."),
            create_heading_block("제목 2", level=2),
            create_bullet_list_block("불릿 리스트 항목 1"),
            create_bullet_list_block("불릿 리스트 항목 2"),
            create_numbered_list_block("번호 리스트 항목 1"),
            create_numbered_list_block("번호 리스트 항목 2"),
            create_code_block("print('Hello, Notion!')", language="python"),
            create_quote_block("이것은 인용문입니다."),
        ]
    )
    
    if new_page:
        print(f"   생성된 페이지 ID: {new_page.get('id')}")
        print(f"   생성된 페이지 URL: {new_page.get('url', 'N/A')}")
    
    # 3. 페이지 내용 읽기
    print("\n3. 페이지 블록 읽기 테스트")
    if new_page:
        blocks = read_all_blocks(new_page['id'])
        if blocks:
            print(f"   읽은 블록 수: {len(blocks)}")
    
    # 4. 텍스트 추출
    print("\n4. 페이지 텍스트 추출 테스트")
    if new_page:
        text = extract_page_text(new_page['id'])
        print(f"   추출된 텍스트:\n{text[:200]}...")
    
    print("\n" + "=" * 50)
    print("테스트 완료!")
    print("=" * 50)


