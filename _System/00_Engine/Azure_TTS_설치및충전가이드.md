# Azure TTS 설치 및 충전 가이드

## 1. Azure Speech SDK 설치

```bash
pip install azure-cognitiveservices-speech
```

## 2. Azure 계정 생성 및 Speech Service 생성

### 2.1 Azure 계정 생성
1. https://azure.microsoft.com/ko-kr/free/ 접속
2. "무료로 시작" 클릭
3. Microsoft 계정으로 로그인
4. 신용카드 정보 입력 (무료 체험용, 실제로는 과금되지 않음)

### 2.2 Speech Service 리소스 생성
1. Azure Portal (https://portal.azure.com) 접속
2. "리소스 만들기" 클릭
3. "Speech" 검색
4. "Speech" 선택 후 "만들기" 클릭
5. 다음 정보 입력:
   - **구독**: 무료 체험 구독 선택
   - **리소스 그룹**: 새로 만들기 또는 기존 그룹 선택
   - **지역**: `Korea Central` (koreacentral) 권장
   - **이름**: 원하는 이름 (예: `YtFactory9-Speech`)
   - **가격 책정 계층**: `Free F0` (무료) 또는 `Standard S0` (유료)
6. "검토 + 만들기" → "만들기" 클릭

### 2.3 키 및 리전 정보 확인
1. 생성된 Speech Service 리소스로 이동
2. 왼쪽 메뉴에서 "키 및 엔드포인트" 클릭
3. 다음 정보 복사:
   - **키 1** 또는 **키 2** (32자리 16진수)
   - **위치/지역** (예: `koreacentral`)

## 3. 키 파일에 정보 저장

`C:\YtFactory9\_System\02_Key\KeyKey_azure.txt` 파일을 열고 다음 형식으로 저장:

```
[AZURE]
KEY=여기에_키_붙여넣기
REGION=koreacentral
```

또는 기존 KeyKey*.txt 파일에 추가:

```
[AZURE]
KEY=abc123def456...
REGION=koreacentral
```

## 4. Azure 충전 방법

### 4.1 무료 체험
- Azure는 **$200 크레딧**을 무료로 제공 (30일간)
- Speech Service는 무료 티어(F0)에서 월 5백만자까지 무료

### 4.2 유료 계정으로 전환
1. Azure Portal 접속
2. "구독" 메뉴로 이동
3. 구독 선택 → "청구" 섹션
4. 결제 방법 추가
5. Speech Service 가격 책정 계층을 `Standard S0`로 변경

### 4.3 가격 정보
- **무료 티어 (F0)**: 월 5백만자 무료, 이후 사용 불가
- **표준 티어 (S0)**: 
  - 첫 5백만자: 무료
  - 이후: $4.00 / 1백만자
  - 실시간 음성 합성: $15.00 / 시간

## 5. 현재 상태 확인

VoiceMaker 실행 시:
- Azure SDK가 설치되어 있으면: Azure TTS 사용 시도
- Azure SDK가 없거나 키가 없으면: **자동으로 Edge TTS로 전환** (무료)

## 6. Edge TTS 사용 권장

**Edge TTS는 완전 무료**이므로 Azure를 충전하지 않아도 사용 가능합니다:
- 무료, 제한 없음
- 고품질 음성
- 빠른 속도

Azure를 사용하려면 위의 단계를 따라 설정하세요.

