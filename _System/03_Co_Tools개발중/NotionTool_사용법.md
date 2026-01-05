# Notion API 연동 도구 사용법

## 설치

```bash
pip install notion-client
```

## 기본 설정

1. API 키는 `_System/02_Key/KeyKeyNotion.txt`에 저장되어 있습니다.
2. 기본 페이지 URL: `https://www.notion.so/ytft-2d8ceb2d2ad880c69f20ddd2c53ca6ff`

## 주요 기능

### 1. 페이지 읽기

```python
from NotionTool import read_page

page = read_page("https://www.notion.so/ytft-2d8ceb2d2ad880c69f20ddd2c53ca6ff")
# 또는 페이지 ID만 사용
page = read_page("2d8ceb2d-2ad8-80c6-9f20-ddd2c53ca6ff")
```

### 2. 페이지 생성

```python
from NotionTool import create_page, create_text_block, create_heading_block

new_page = create_page(
    parent_page_id_or_url="https://www.notion.so/ytft-2d8ceb2d2ad880c69f20ddd2c53ca6ff",
    title="새 페이지 제목",
    content=[
        create_heading_block("제목", level=1),
        create_text_block("내용입니다."),
    ]
)
```

### 3. 블록 추가

```python
from NotionTool import add_blocks, create_text_block, create_bullet_list_block

add_blocks(
    page_id_or_url="페이지 ID 또는 URL",
    blocks=[
        create_text_block("추가할 텍스트"),
        create_bullet_list_block("리스트 항목"),
    ]
)
```

### 4. 페이지 제목 변경

```python
from NotionTool import update_page_title

update_page_title("페이지 ID 또는 URL", "새 제목")
```

### 5. 페이지 내용 읽기

```python
from NotionTool import read_all_blocks, extract_page_text

# 모든 블록 읽기
blocks = read_all_blocks("페이지 ID 또는 URL")

# 텍스트만 추출
text = extract_page_text("페이지 ID 또는 URL")
```

## 사용 가능한 블록 타입

- `create_text_block(text)` - 일반 텍스트
- `create_heading_block(text, level=1)` - 제목 (level: 1, 2, 3)
- `create_bullet_list_block(text)` - 불릿 리스트
- `create_numbered_list_block(text)` - 번호 리스트
- `create_code_block(code, language="plain text")` - 코드 블록
- `create_quote_block(text)` - 인용문
- `create_toggle_block(text, children=None)` - 토글 블록

## 예제

```python
from NotionTool import *
from datetime import datetime

BASE_URL = "https://www.notion.so/ytft-2d8ceb2d2ad880c69f20ddd2c53ca6ff"

# 새 페이지 생성
new_page = create_page(
    BASE_URL,
    f"일일 보고서 - {datetime.now().strftime('%Y-%m-%d')}",
    [
        create_heading_block("오늘의 작업", level=1),
        create_bullet_list_block("작업 1 완료"),
        create_bullet_list_block("작업 2 진행 중"),
        create_heading_block("내일 계획", level=1),
        create_numbered_list_block("계획 1"),
        create_numbered_list_block("계획 2"),
    ]
)

# 페이지에 내용 추가
add_blocks(
    new_page['id'],
    [
        create_text_block("추가 내용입니다."),
        create_code_block("def hello():\n    print('Hello!')", language="python"),
    ]
)

# 페이지 제목 변경
update_page_title(new_page['id'], "수정된 제목")

# 페이지 내용 읽기
text = extract_page_text(new_page['id'])
print(text)
```









