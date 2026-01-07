@echo off
chcp 65001 >nul
echo ========================================
echo   깃허브에 업로드 중...
echo ========================================
echo.

REM Git 초기화 (이미 되어있으면 스킵)
if not exist .git (
    echo [1/5] Git 저장소 초기화 중...
    git init
) else (
    echo [1/5] Git 저장소가 이미 초기화되어 있습니다.
)

echo.
echo [2/5] 원격 저장소 설정 중...
git remote remove origin 2>nul
git remote add origin https://github.com/seongahjo830/searching.git

echo.
echo [3/5] 파일 추가 중...
git add .

echo.
echo [4/5] 커밋 중...
git commit -m "유튜브 황금 주제 발굴기 - 트렌딩 주제 발굴 기능 추가"

echo.
echo [5/5] 깃허브에 푸시 중...
git branch -M main
git push -u origin main

echo.
echo ========================================
echo   완료!
echo ========================================
echo.
echo 만약 인증 오류가 발생하면:
echo 1. GitHub에서 Personal Access Token 생성
echo 2. 비밀번호 대신 토큰 사용
echo.
pause

