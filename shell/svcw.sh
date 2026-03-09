#!/bin/sh
# HP-UX / POSIX sh
# - 최초 1회만 clear
# - 이후는 고정 화면(덮어쓰기) + 잔상 방지(줄 패딩)
# - pid 모두 존재 + web 모두 OK => SUCCESS, 그 외 FAIL
# - FAIL 인 경우 연속 FAIL 누적 시간 표시

SVC="/Users/jeon/works/wsp/dummy-server/files/svc.sh"

# 출력 폭(줄 잔상 제거용). 보수적으로 크게 잡음.
WIDTH=200

# 고정 화면 높이(출력 줄 수보다 넉넉히)
LINES=20

# 임시 파일 (멀티라인 결과 안정 처리)
TMP="/Users/jeon/works/wsp/dummy-server/files/svc_watch.$$"

# FAIL 누적 시작 시각(epoch seconds). 0이면 현재 FAIL 아님.
FAIL_START=0

# epoch seconds 가져오기 (HP-UX date 에서 %s 미지원일 수 있어 perl fallback)
now_epoch() {
  ts=`date +%s 2>/dev/null`
  case "$ts" in
    ''|*[!0-9]*)
      if command -v perl >/dev/null 2>&1; then
        perl -e 'print time' 2>/dev/null
      else
        echo 0
      fi
      ;;
    *)
      echo "$ts"
      ;;
  esac
}

# seconds -> HH:MM:SS
fmt_hms() {
  s="$1"
  [ -n "$s" ] || s=0
  case "$s" in
    ''|*[!0-9]*)
      echo "00:00:00"
      return
      ;;
  esac
  h=`expr "$s" / 3600`
  m=`expr \( "$s" % 3600 \) / 60`
  ss=`expr "$s" % 60`
  printf "%02d:%02d:%02d" "$h" "$m" "$ss"
}

# 커서 숨김(커서 깜빡임 방지)
trap 'rm -f "$TMP"; printf "\033[?25h"; exit' INT TERM
printf "\033[?25l"

# 최초 1회만 clear + home
printf "\033[2J\033[H"

# 고정 영역 확보(아래로 밀림 방지)
i=0
while [ $i -lt $LINES ]; do
  echo
  i=`expr $i + 1`
done
printf "\033[%sA" "$LINES"

pad_print() {
  # $1: line
  # 줄 끝 잔상 제거를 위해 WIDTH 만큼 공백 패딩 후, WIDTH까지만 출력
  echo "$1" | awk -v w="$WIDTH" '{
    s=$0
    pad=""
    for(i=length(s); i<w; i++) pad=pad " "
    out=s pad
    print substr(out,1,w)
  }'
}

while :
do
  # 화면 맨 위로 이동 (clear는 안함)
  printf "\033[H"

  ts="`date '+%Y-%m-%d %H:%M:%S'`"
  pad_print "========== $ts =========="

  # check 결과를 임시파일로 저장 (멀티라인/잔상/특수환경 안정)
  $SVC check all > "$TMP" 2>&1

  # 결과 출력 (라인 단위 패딩)
  while IFS= read line
  do
    pad_print "$line"
  done < "$TMP"

  pad_print "========================================="

  # 판정 (임시파일 기준으로 계산)
  TOTAL=`grep -c "^\[CHECK\]" "$TMP" 2>/dev/null`
  PID_OK_CNT=`grep "^\[CHECK\]" "$TMP" 2>/dev/null | grep -vc "pid=UNKNOWN"`
  WEB_OK_CNT=`grep "^\[CHECK\]" "$TMP" 2>/dev/null | grep -c "(web=OK"`

  if [ "$TOTAL" -gt 0 ] && [ "$PID_OK_CNT" -eq "$TOTAL" ] && [ "$WEB_OK_CNT" -eq "$TOTAL" ]; then
    # SUCCESS 되면 FAIL 누적 초기화
    FAIL_START=0
    pad_print "SUCCESS"
  else
    now_ts=`now_epoch`
    if [ "$FAIL_START" -eq 0 ] && [ "$now_ts" -gt 0 ]; then
      FAIL_START="$now_ts"
    fi

    if [ "$FAIL_START" -gt 0 ] && [ "$now_ts" -gt 0 ]; then
      elapsed=`expr "$now_ts" - "$FAIL_START"`
      pad_print "FAIL (`fmt_hms "$elapsed"`)"
    else
      pad_print "FAIL"
    fi
  fi

  # 남는 줄 잔상 제거용 빈줄 덮어쓰기
  extra=0
  while [ $extra -lt 5 ]; do
    pad_print ""
    extra=`expr $extra + 1`
  done

  sleep 1
done
