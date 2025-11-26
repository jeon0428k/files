#!/bin/ksh
#
# ============================================
#  TASK_SCRIPT 반복 실행 Controller (9분 간격)
# ============================================

# 실행할 스크립트 절대경로
TASK_SCRIPT="/home/myuser/test.sh"

# 실행 주기 (초) → 9분 = 540초
INTERVAL=540

# PID 저장 파일
PID_FILE="/home/myuser/task.pid"


# --------------------------------------------
# start
# --------------------------------------------
function start {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")

        # 이미 실행 중이면 종료
        if ps -p $PID >/dev/null 2>&1; then
            print "이미 실행 중입니다. (PID=$PID)"
            exit 0
        else
            print "PID 파일 존재하지만 해당 PID는 실행 중이 아님 → pid 파일 삭제"
            rm -f "$PID_FILE"
        fi
    fi

    # 백그라운드에서 무한 반복 실행
    (
        while true
        do
            $TASK_SCRIPT
            sleep $INTERVAL
        done
    ) &

    echo $! > "$PID_FILE"
    print "시작됨 (PID=$(cat $PID_FILE))"
}


# --------------------------------------------
# stop
# --------------------------------------------
function stop {
    if [ ! -f "$PID_FILE" ]; then
        print "실행 중이 아닙니다."
        exit 0
    fi

    PID=$(cat "$PID_FILE")

    if ps -p $PID >/dev/null 2>&1; then
        kill $PID
        print "중지됨 (PID=$PID)"
        rm -f "$PID_FILE"
    else
        print "프로세스 없음 → pid 파일 삭제"
        rm -f "$PID_FILE"
    fi
}


# --------------------------------------------
# status
# --------------------------------------------
function status {
    if [ ! -f "$PID_FILE" ]; then
        print "실행 중이 아닙니다."
        exit 0
    fi

    PID=$(cat "$PID_FILE")

    if ps -p $PID >/dev/null 2>&1; then
        print "실행 중 (PID=$PID)"
    else
        print "정지됨 (pid 파일은 있으나 프로세스 없음)"
    fi
}


# --------------------------------------------
# 명령 처리
# --------------------------------------------
case "$1" in
    start)
        start ;;
    stop)
        stop ;;
    status)
        status ;;
    *)
        print "사용법: $0 {start|stop|status}"
        exit 1 ;;
esac