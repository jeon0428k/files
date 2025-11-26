#!/bin/ksh
#
# ============================================
#  MULTI TASK CONTROLLER (AIX/ksh 전용)
#  파일명으로 자동 PID_FILE 및 TASK_SCRIPT 매핑
# ============================================

# 현재 스크립트 이름
SCRIPT_NAME=$(basename $0)          # 예: task_ctl1.ksh

# task_ctl1.ksh → test1.sh 자동 매핑
TASK_NUM=$(print $SCRIPT_NAME | sed 's/[^0-9]//g')   # 숫자만 추출 (1,2,3,...)
TASK_SCRIPT="/home/myuser/test${TASK_NUM}.sh"

# PID 파일도 자동 생성 (스크립트별 고유)
PID_FILE="/home/myuser/${SCRIPT_NAME}.pid"

# 실행 주기 (초) → 9분 = 540초
INTERVAL=540


# --------------------------------------------
# start
# --------------------------------------------
function start {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")

        if ps -p $PID >/dev/null 2>&1; then
            print "이미 실행 중입니다. (PID=$PID)"
            exit 0
        else
            print "pid 파일 존재하지만 실행 중 아님 → 삭제"
            rm -f "$PID_FILE"
        fi
    fi

    (
        while true
        do
            $TASK_SCRIPT
            sleep $INTERVAL
        done
    ) &

    echo $! > "$PID_FILE"
    print "시작됨 → TASK_SCRIPT=${TASK_SCRIPT}, PID=$(cat $PID_FILE)"
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
        print "실행 중 → TASK_SCRIPT=${TASK_SCRIPT}, PID=$PID"
    else
        print "정지됨 (pid 파일만 존재)"
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