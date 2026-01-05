"""ImageMaker.py에서 사용하는 시트 열 확인"""
import re

# 시트 열 구조 (이미지에서 확인)
COLUMNS = {
    'A': 'id',
    'B': 'script',
    'C': 'image_group',
    'D': 'duration',
    'E': 'subtype',
    'F': 'promptABC',
    'G': '(공란)',
    'H': 'image_prompt',
    'I': 'voice',
    'J': 'imagetype',
    'K': 'sound',
    'L': 'voice_tool',
    'M': 'fal_RootImage'
}

# 코드에서 사용하는 열 (확인된 내용)
USED_COLUMNS = {
    'B (row[1])': 'script - 텍스트 데이터',
    'C (row[2])': 'image_group - 그룹 ID',
    'F (row[5])': 'promptABC - 프롬프트 스타일 키워드',
    'H (cell 8)': 'image_prompt - 생성된 이미지 프롬프트 (읽기/쓰기)',
    'J (cell 10)': 'imagetype - 이미지 타입 (gemini/flux/fal)',
    'M (cell 13)': 'fal_RootImage - Fal 참조 이미지 키워드'
}

UNUSED_COLUMNS = {
    'A': 'id',
    'D': 'duration',
    'E': 'subtype',
    'G': '(공란)',
    'I': 'voice',
    'K': 'sound',
    'L': 'voice_tool'
}

print("=" * 60)
print("📊 ImageMaker.py 시트 열 사용 현황")
print("=" * 60)

print("\n✅ 사용 중인 열:")
for col, desc in USED_COLUMNS.items():
    print(f"   {col:15} → {desc}")

print(f"\n📈 사용 중: {len(USED_COLUMNS)}개 열")

print("\n❌ 사용하지 않는 열:")
for col, name in UNUSED_COLUMNS.items():
    print(f"   {col:15} → {name}")

print(f"\n📉 미사용: {len(UNUSED_COLUMNS)}개 열")

print("\n" + "=" * 60)
print(f"전체 {len(COLUMNS)}개 열 중 {len(USED_COLUMNS)}개 사용 ({len(USED_COLUMNS)/len(COLUMNS)*100:.1f}%)")
print("=" * 60)








