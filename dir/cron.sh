#!/bin/bash
#
# ============================================
#  crontab 제어 스크립트
# --------------------------------------------
#  기능:
#    - start  : crontab에 스케줄 등록
#    - stop   : crontab에서 스케줄 삭제
#    - status : 현재 등록 여부 확인
#
#  사용방법:
#    1) 실행 권한 부여
#         chmod +x cron_control.sh
#
#    2) CRON 등록
#         ./cron_control.sh start
#
#    3) CRON 삭제
#         ./cron_control.sh stop
#
#    4) CRON 등록 상태 확인
#         ./cron_control.sh status
#
# ============================================

# 실행할 스크립트 경로 (원하는 경로로 변경)
CRON_JOB_PATH="/path/to/script.sh"

# CRON 등록 라인 (예: 5분마다 실행)
CRON_JOB="*/5 * * * * $CRON_JOB_PATH"

# 경로에서 실행 파일명만 추출
CRON_JOB_FILE=$(basename "$CRON_JOB_PATH")


function start_cron() {
    # 이미 등록되어 있는지 확인
    crontab -l 2>/dev/null | grep -F "$CRON_JOB" > /dev/null
    if [ $? -eq 0 ]; then
        echo "$CRON_JOB_FILE 이미 등록됨"
        exit 0
    fi

    # 등록
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "$CRON_JOB_FILE 등록됨"
}

function stop_cron() {
    # 삭제
    crontab -l 2>/dev/null | grep -v -F "$CRON_JOB" | crontab -
    echo "$CRON_JOB_FILE 삭제됨"
}

function status_cron() {
    crontab -l 2>/dev/null | grep -F "$CRON_JOB" > /dev/null
    if [ $? -eq 0 ]; then
        echo "$CRON_JOB_FILE (등록됨)"
    else
        echo "$CRON_JOB_FILE (등록 안됨)"
    fi
}

# 명령 처리
case "$1" in
    start)
        start_cron
        ;;
    stop)
        stop_cron
        ;;
    status)
        status_cron
        ;;
    *)
        echo "사용법: $0 {start|stop|status}"
        exit 1
esac