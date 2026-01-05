"""
자동 파이프라인 실행 스크립트
이미지메이커 -> 켄번 -> 보이스메이커 -> 머지파이 순서대로 실행
시트 2번으로 전체 파이프라인 실행 후, 시트 3번으로도 자동 실행
1시간 후에 시작
"""
import os
import sys
import subprocess
import time
from datetime import datetime, timedelta

# 현재 스크립트의 디렉토리
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# 실행할 스크립트 목록 (순서대로)
SCRIPTS = [
    {
        "name": "이미지메이커",
        "file": "ImageMaker.py",
        "description": "이미지 생성"
    },
    {
        "name": "켄번",
        "file": "KenBurns.py",
        "description": "켄번 효과 적용"
    },
    {
        "name": "보이스메이커",
        "file": "VoiceMaker.py",
        "description": "음성 생성"
    },
    {
        "name": "머지파이",
        "file": "Mergy.py",
        "description": "최종 영상 조립"
    }
]

def wait_until_time(target_time):
    """지정된 시간까지 대기"""
    current_time = datetime.now()
    wait_seconds = (target_time - current_time).total_seconds()
    
    if wait_seconds <= 0:
        print("⚠️ 지정된 시간이 이미 지났습니다. 즉시 시작합니다.")
        return
    
    print(f"⏰ {target_time.strftime('%Y-%m-%d %H:%M:%S')}까지 대기 중...")
    print(f"   남은 시간: {timedelta(seconds=int(wait_seconds))}")
    
    # 1분 단위로 남은 시간 출력
    while wait_seconds > 0:
        if wait_seconds > 60:
            time.sleep(60)
            wait_seconds -= 60
            remaining = timedelta(seconds=int(wait_seconds))
            print(f"   남은 시간: {remaining}")
        else:
            time.sleep(wait_seconds)
            wait_seconds = 0
    
    print("✅ 시작 시간 도달! 파이프라인을 시작합니다.\n")

def run_script(script_info, sheet_choice="2"):
    """스크립트 실행 (자동으로 시트 선택 입력)"""
    script_name = script_info["name"]
    script_file = script_info["file"]
    script_path = os.path.join(CURRENT_DIR, script_file)
    
    if not os.path.exists(script_path):
        print(f"❌ 스크립트 파일을 찾을 수 없습니다: {script_path}")
        return False
    
    print("=" * 60)
    print(f"🚀 [{script_name}] 실행 시작: {script_info['description']}")
    print("=" * 60)
    print(f"   시트 선택: {sheet_choice}번 (자동 입력)")
    print("=" * 60)
    
    try:
        import threading
        
        # stdout을 실시간으로 출력하기 위한 스레드
        def read_output(pipe):
            """stdout을 읽어서 실시간 출력"""
            try:
                for line in iter(pipe.readline, ''):
                    if line:
                        print(line, end='')
                pipe.close()
            except:
                pass
        
        # stdin에 입력을 전달하기 위한 스레드
        def write_input(pipe, input_value):
            """stdin에 입력 전달"""
            try:
                # 약간의 지연 후 입력 전달 (스크립트가 input()을 호출할 때까지 대기)
                time.sleep(2)  # 스크립트가 시작될 때까지 대기
                # 여러 번 전달하여 안전하게 처리
                for _ in range(5):
                    pipe.write(f"{input_value}\n")
                    pipe.flush()
                    time.sleep(0.5)
            except:
                pass
        
        # Python 스크립트 실행
        process = subprocess.Popen(
            [sys.executable, script_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=CURRENT_DIR
        )
        
        # stdout 읽기 스레드 시작
        output_thread = threading.Thread(
            target=read_output,
            args=(process.stdout,),
            daemon=True
        )
        output_thread.start()
        
        # stdin에 입력 전달 스레드 시작
        input_thread = threading.Thread(
            target=write_input,
            args=(process.stdin, sheet_choice),
            daemon=True
        )
        input_thread.start()
        
        # 프로세스 완료 대기
        return_code = process.wait()
        
        # 스레드 종료 대기
        output_thread.join(timeout=2)
        input_thread.join(timeout=1)
        
        # stdin 닫기
        try:
            process.stdin.close()
        except:
            pass
        
        if return_code == 0:
            print(f"\n✅ [{script_name}] 완료!")
            return True
        else:
            print(f"\n❌ [{script_name}] 실패 (종료 코드: {return_code})")
            return False
            
    except Exception as e:
        print(f"❌ [{script_name}] 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_pipeline_for_sheet(sheet_number):
    """특정 시트 번호로 전체 파이프라인 실행"""
    print("\n" + "=" * 60)
    print(f"📊 시트 {sheet_number}번 파이프라인 시작")
    print("=" * 60)
    
    # 각 스크립트 순차 실행
    for i, script in enumerate(SCRIPTS, 1):
        print(f"\n{'='*60}")
        print(f"📋 [시트 {sheet_number}번] [{i}/{len(SCRIPTS)}] {script['name']} 실행 중...")
        print(f"{'='*60}\n")
        
        success = run_script(script, sheet_choice=str(sheet_number))
        
        if not success:
            print(f"\n❌ [{script['name']}] 실패로 인해 파이프라인이 중단됩니다.")
            print("다음 단계를 계속 진행하시겠습니까? (y/n): ", end="")
            try:
                choice = input().strip().lower()
                if choice != 'y':
                    print("파이프라인을 중단합니다.")
                    return False
            except:
                print("파이프라인을 중단합니다.")
                return False
        
        # 다음 스크립트 실행 전 잠시 대기 (선택사항)
        if i < len(SCRIPTS):
            print(f"\n⏳ 다음 단계로 진행하기 전 3초 대기...")
            time.sleep(3)
    
    print(f"\n✅ 시트 {sheet_number}번 파이프라인 완료!")
    return True

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("🎬 자동 파이프라인 실행 스크립트")
    print("=" * 60)
    print("\n실행 순서:")
    for i, script in enumerate(SCRIPTS, 1):
        print(f"  {i}. {script['name']} - {script['description']}")
    print(f"\n시트 2번으로 전체 파이프라인 실행")
    print(f"→ 완료 후 시트 3번으로도 자동 실행")
    
    # 1시간 후 시간 계산
    start_time = datetime.now() + timedelta(hours=1)
    print(f"\n⏰ 시작 시간: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   현재 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 1시간 대기
    wait_until_time(start_time)
    
    # 시트 2번으로 전체 파이프라인 실행
    success_2 = run_pipeline_for_sheet(2)
    
    if not success_2:
        print("\n❌ 시트 2번 파이프라인이 실패하여 중단됩니다.")
        return
    
    # 시트 2번 완료 후 잠시 대기
    print("\n" + "=" * 60)
    print("⏳ 시트 3번 파이프라인 시작 전 5초 대기...")
    print("=" * 60)
    time.sleep(5)
    
    # 시트 3번으로 전체 파이프라인 실행
    success_3 = run_pipeline_for_sheet(3)
    
    if not success_3:
        print("\n❌ 시트 3번 파이프라인이 실패했습니다.")
        return
    
    print("\n" + "=" * 60)
    print("🎉 모든 파이프라인 작업이 완료되었습니다!")
    print("   - 시트 2번: 완료 ✅")
    print("   - 시트 3번: 완료 ✅")
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n\n❌ 예상치 못한 오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()
    finally:
        input("\n엔터 키를 누르면 종료합니다...")

