@echo off
chcp 65001 >nul
echo ========================================
echo   유튜브 황금 주제 발굴기 실행 중...
echo ========================================
echo.

REM 패키지 설치 확인
echo [1/2] 필요한 패키지 확인 중...
pip show streamlit >nul 2>&1
if errorlevel 1 (
    echo 패키지가 설치되어 있지 않습니다. 설치를 시작합니다...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo 오류: 패키지 설치에 실패했습니다.
        pause
        exit /b 1
    )
) else (
    echo 패키지가 이미 설치되어 있습니다.
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

