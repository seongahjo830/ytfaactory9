@echo off
chcp 65001 >nul
echo ========================================
echo   유튜브 황금 주제 발굴기
echo   패키지 설치 및 실행
echo ========================================
echo.

echo [1/2] 필요한 패키지 설치 중...
echo 이 과정은 처음 한 번만 필요합니다.
echo.
pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo 오류: 패키지 설치에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo [2/2] Streamlit 앱 실행 중...
echo.
echo 브라우저가 자동으로 열립니다.
echo 종료하려면 이 창을 닫거나 Ctrl+C를 누르세요.
echo.

REM Streamlit 앱 실행
streamlit run main.py

pause

