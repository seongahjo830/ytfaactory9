# 1시간 후 두 배치 파일 실행 및 옵션 1 자동 선택 스크립트

Write-Host "⏰ 1시간 후 실행 예정입니다..." -ForegroundColor Yellow
Write-Host "실행 시간: $(Get-Date)" -ForegroundColor Cyan

# 1시간 대기 (3600초)
Start-Sleep -Seconds 3600

Write-Host "`n🚀 실행 시작: $(Get-Date)" -ForegroundColor Green

# 첫 번째 배치 파일 실행 (보이스메이커)
Write-Host "`n📢 보이스메이커 실행 중..." -ForegroundColor Cyan
$voiceMakerPath = "C:\YtFactory9\_System\00_Engine\020 ❤️ 보이스메이커.bat"
$voiceMakerDir = Split-Path -Parent $voiceMakerPath

# Python 스크립트에 "1" 입력을 전달하기 위해 임시 입력 파일 생성
$inputFile = Join-Path $env:TEMP "voice_input.txt"
"1" | Out-File -FilePath $inputFile -Encoding ASCII

# cmd.exe를 통해 입력 리다이렉션 사용
$process1 = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd /d `"$voiceMakerDir`" && python VoiceMaker.py < `"$inputFile`"" -Wait -NoNewWindow -PassThru

Remove-Item $inputFile -ErrorAction SilentlyContinue

if ($process1.ExitCode -eq 0) {
    Write-Host "✅ 보이스메이커 완료" -ForegroundColor Green
} else {
    Write-Host "⚠️ 보이스메이커 실행 중 오류 발생 (종료 코드: $($process1.ExitCode))" -ForegroundColor Yellow
}

# 두 번째 배치 파일 실행 (켄번)
Write-Host "`n🎬 켄번 실행 중..." -ForegroundColor Cyan
$kenBurnsPath = "C:\YtFactory9\_System\00_Engine\011 켄번.bat"
$kenBurnsDir = Split-Path -Parent $kenBurnsPath

# Python 스크립트에 "1" 입력을 전달하기 위해 임시 입력 파일 생성
$inputFile2 = Join-Path $env:TEMP "kenburns_input.txt"
"1" | Out-File -FilePath $inputFile2 -Encoding ASCII

# cmd.exe를 통해 입력 리다이렉션 사용
$process2 = Start-Process -FilePath "cmd.exe" -ArgumentList "/c", "cd /d `"$kenBurnsDir`" && python KenBurns.py < `"$inputFile2`"" -Wait -NoNewWindow -PassThru

Remove-Item $inputFile2 -ErrorAction SilentlyContinue

if ($process2.ExitCode -eq 0) {
    Write-Host "✅ 켄번 완료" -ForegroundColor Green
} else {
    Write-Host "⚠️ 켄번 실행 중 오류 발생 (종료 코드: $($process2.ExitCode))" -ForegroundColor Yellow
}

Write-Host "`n🎉 모든 작업 완료: $(Get-Date)" -ForegroundColor Green
Write-Host "아무 키나 누르면 종료됩니다..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

