#!/bin/sh
# HP-UX / POSIX sh

usage() {
  echo "Usage: svc {start|stop|restart|kill|check|log|logc|backup} [more...]"
  exit 1
}

BASE_DIR="/Users/jeon/works/wsp/dummy-server/files"
LOG_BASE_PATH="./logs"
LOG_FILE_NAME="svc.log"

STOP_WAIT_SEC=60
START_WAIT_SEC=10

# ----------------------------
# arg normalize (web/all -> w1 w2 w3)
# ----------------------------
expand_services() {
  out=""
  for a in "$@"; do
    case "$a" in
      all|web) out="$out w1 w2 w3" ;;
      *)       out="$out $a"       ;;
    esac
  done
  echo "$out" | awk '{$1=$1; print}'
}

# ----------------------------
# service mapping
# ----------------------------
resolve_start() {
  case "$1" in
    w1) echo "$BASE_DIR/web1/start.sh" ;;
    w2) echo "$BASE_DIR/web2/start.sh" ;;
    w3) echo "$BASE_DIR/web3/start.sh" ;;
    *) echo "" ;;
  esac
}

resolve_stop() {
  case "$1" in
    w1) echo "$BASE_DIR/web1/stop.sh" ;;
    w2) echo "$BASE_DIR/web2/stop.sh" ;;
    w3) echo "$BASE_DIR/web3/stop.sh" ;;
    *) echo "" ;;
  esac
}

resolve_log() {
  case "$1" in
    w1) echo "$BASE_DIR/logs/web1.log" ;;
    w2) echo "$BASE_DIR/logs/web2.log" ;;
    w3) echo "$BASE_DIR/logs/web3.log" ;;
    *) echo "" ;;
  esac
}

resolve_pskey() {
  case "$1" in
    w1) echo "-DNAME=web1" ;;
    w2) echo "-DNAME=web2" ;;
    w3) echo "-DNAME=web3" ;;
    *) echo "" ;;
  esac
}

resolve_svc_name() {
  key="`resolve_pskey "$1"`"
  [ -n "$key" ] || return 1
  echo "$key" | sed 's/^-DNAME=//'
}

svc_label() {
  name="`resolve_svc_name "$1"`"
  if [ -n "$name" ]; then echo "$1($name)"; else echo "$1"; fi
}

resolve_health_url() {
  case "$1" in
    w1) echo "http://127.0.0.1:18081/ping" ;;
    w2) echo "$BASE_DIR/web2/urlCheck.log" ;;
    w3) echo "$BASE_DIR/web3/urlCheck.log" ;;
    *) echo "" ;;
  esac
}

resolve_backup_dir() {
  case "$1" in
    w1) echo "$BASE_DIR/web1" ;;
    w2) echo "$BASE_DIR/web2" ;;
    w3) echo "$BASE_DIR/web3" ;;
    *) echo "" ;;
  esac
}

now()         { date '+%Y-%m-%d %H:%M:%S'; }
backup_date() { date '+%Y%m%d'; }

# ----------------------------
# process helpers
# ----------------------------
is_alive() {
  PID="$1"
  [ -n "$PID" ] || return 1
  kill -0 "$PID" 2>/dev/null
}

force_kill_silent() {
  PID="$1"
  WAIT_SEC="${2:-5}"

  is_alive "$PID" || return 0

  kill -15 "$PID" 2>/dev/null

  i=0
  while [ $i -lt "$WAIT_SEC" ]; do
    is_alive "$PID" || return 0
    sleep 1
    i=`expr $i + 1`
  done

  kill -9 "$PID" 2>/dev/null
  is_alive "$PID" && return 1 || return 0
}

get_running_pid() {
  svc="$1"
  pskey="`resolve_pskey "$svc"`"
  [ -z "$pskey" ] && return 1
  ps -ef | grep java | grep -e "$pskey" | grep -v grep | awk '{print $2}' | head -1
}

get_running_pids() {
  svc="$1"
  pskey="`resolve_pskey "$svc"`"
  [ -z "$pskey" ] && return 1
  ps -ef | grep java | grep -e "$pskey" | grep -v grep | awk '{print $2}'
}

# ----------------------------
# http check (curl -> wget -> perl)
# ----------------------------
http_alive() {
  url="$1"
  [ -n "$url" ] || return 2

  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 3 "$url" >/dev/null 2>&1
    return $?
  fi

  if command -v wget >/dev/null 2>&1; then
    wget -q -T 3 -O /dev/null "$url" >/dev/null 2>&1
    return $?
  fi

  if command -v perl >/dev/null 2>&1; then
    perl -e '
      use IO::Socket::INET;
      my $url = $ARGV[0];
      $url =~ m{^https?://([^/:]+)(?::(\d+))?(/.*)?$} or exit 2;
      my ($host,$port,$path)=($1,$2||80,$3||"/");
      my $sock = IO::Socket::INET->new(
        PeerAddr=>$host, PeerPort=>$port, Proto=>"tcp", Timeout=>3
      ) or exit 1;
      print $sock "GET $path HTTP/1.0\r\nHost: $host\r\nConnection: close\r\n\r\n";
      my $line = <$sock>;
      exit 1 unless defined $line;
      exit 0 if $line =~ m{^HTTP/\d+\.\d+\s+[23]\d\d};
      exit 1;
    ' "$url" >/dev/null 2>&1
    return $?
  fi

  return 3
}

file_alive() {
  f="$1"
  [ -n "$f" ] || return 2
  [ -f "$f" ] || return 1
  [ -r "$f" ] || return 1
  grep -q "OK" "$f" 2>/dev/null
  return $?
}

health_alive() {
  target="$1"
  [ -n "$target" ] || return 2
  case "$target" in
    http://*|https://*) http_alive "$target"; return $? ;;
    *)                  file_alive "$target"; return $? ;;
  esac
}

# ----------------------------
# do_start / do_stop / do_kill / do_backup
# ----------------------------
do_start() {
  svc="$1"
  script="`resolve_start "$svc"`"
  [ -n "$script" ] || return 2
  [ -f "$script" ] || return 3
  [ -x "$script" ] || return 4

  dir=`dirname "$script"`
  base=`basename "$script"`

  nohup sh -c '
    trap "" HUP INT TSTP
    cd "$1" || exit 1
    "./$2"
  ' sh "$dir" "$base" < /dev/null > /dev/null 2>&1 &
  return 0
}

do_stop() {
  svc="$1"
  script="`resolve_stop "$svc"`"
  [ -n "$script" ] || return 2
  [ -f "$script" ] || return 3
  [ -x "$script" ] || return 4

  dir=`dirname "$script"`
  base=`basename "$script"`

  nohup sh -c '
    trap "" HUP INT TSTP
    cd "$1" || exit 1
    "./$2"
  ' sh "$dir" "$base" < /dev/null > /dev/null 2>&1 &
  return 0
}

# FIX: 동기 실행으로 변경 — 실제 kill 성공/실패를 반환값으로 전달
do_kill() {
  svc="$1"
  pids="`get_running_pids "$svc"`"
  [ -n "$pids" ] || return 0

  rc=0
  for pid in $pids; do
    force_kill_silent "$pid" 5 || rc=1
  done
  return $rc
}

# FIX: 동기 실행으로 변경 — cp 결과를 즉시 반환
do_backup() {
  svc="$1"
  src="`resolve_backup_dir "$svc"`"
  [ -n "$src" ] || return 2
  [ -d "$src" ] || return 3

  ts="`backup_date`"
  dest="${src}_${ts}"

  if [ -e "$dest" ]; then
    echo "[BACKUP-EXISTS] `svc_label "$svc"` ($dest already exists)"
    return 10
  fi

  cp -rp "$src" "$dest"
  return $?
}

wait_down() {
  svc="$1"
  max="${2:-$STOP_WAIT_SEC}"
  i=0
  while [ $i -lt "$max" ]; do
    pid="`get_running_pid "$svc"`"
    [ -z "$pid" ] && return 0
    sleep 1
    i=`expr $i + 1`
  done
  return 1
}

# FIX: sleep 1 대신 실제 PID 폴링 — 기동 확인 후 PID 출력
wait_up() {
  svc="$1"
  max="${2:-$START_WAIT_SEC}"
  i=0
  while [ $i -lt "$max" ]; do
    pid="`get_running_pid "$svc"`"
    if [ -n "$pid" ]; then
      echo "$pid"
      return 0
    fi
    sleep 1
    i=`expr $i + 1`
  done
  return 1
}

# ----------------------------
# check service (process + http)
# ----------------------------
check_service() {
  svc="$1"
  pid="`get_running_pid "$svc"`"
  health="`resolve_health_url "$svc"`"

  if [ -z "$pid" ]; then
    echo "[CHECK] `svc_label "$svc"` (pid=UNKNOWN) (web=SKIP)"
    return 1
  fi

  if [ -n "$health" ]; then
    if health_alive "$health"; then
      echo "[CHECK] `svc_label "$svc"` (pid=$pid) (web=OK, $health)"
      return 0
    else
      rc=$?
      if [ $rc -eq 3 ]; then
        echo "[CHECK] `svc_label "$svc"` (pid=$pid) (web=UNKNOWN(no tool), $health)"
        return 0
      fi
      echo "[CHECK] `svc_label "$svc"` (pid=$pid) (web=FAIL, $health)"
      return 1
    fi
  fi

  echo "[CHECK] `svc_label "$svc"` (pid=$pid) (web=SKIP)"
  return 0
}

# ----------------------------
# entry
# ----------------------------
action="$1"
shift

[ -n "$action" ] && [ $# -ge 1 ] || usage

case "$action" in
  start|stop|restart|kill|check|log|logc|backup) ;;
  *) usage ;;
esac

set -- `expand_services "$@"`

# Ctrl+Z(TSTP) 시 스크립트 자체가 STOPPED로 남지 않도록 exit 처리.
# log/logc는 아래에서 _log_cleanup으로 override함.
trap 'exit 0' TSTP

# ----------------------------
# log / logc
# Ctrl+C(INT) / Ctrl+Z(TSTP) / TERM 시 백그라운드 프로세스 정리
#
# [문제] tail | awk & 에서 $!는 awk PID만 반환 → tail PID 미추적
#        Ctrl+Z 시 tail이 STOPPED 상태로 프로세스 테이블에 잔존
#
# [해결]
#   1. FIFO로 파이프라인 분리 → tail PID와 awk/tee PID를 각각 추적
#   2. cleanup 시 kill -CONT로 STOPPED 프로세스 먼저 깨운 후 kill -TERM
#      (STOPPED 프로세스는 재개되어야 시그널을 처리할 수 있는 OS가 있음)
#   3. kill -CONT -- -$$ 로 그룹 내 미추적 프로세스(logc 중간 awk 등)도 함께 정리
# ----------------------------
if [ "$action" = "log" ] || [ "$action" = "logc" ]; then

  out_file=""

  if [ "$action" = "logc" ]; then
    mkdir -p "$LOG_BASE_PATH" || { echo "ERROR: cannot create log dir: $LOG_BASE_PATH"; exit 1; }
    out_file="$LOG_BASE_PATH/$LOG_FILE_NAME"

    if [ -f "$out_file" ]; then
      ts=`date +%Y%m%d_%H%M%S`
      mv "$out_file" "$LOG_BASE_PATH/svc_${ts}.log"
    fi

    : > "$out_file" || { echo "ERROR: cannot create log file: $out_file"; exit 1; }
    echo "`now` | LOG OUTPUT -> $out_file"
  fi

  _tmpdir="/tmp/.svc_log_$$"
  _bg_pids=""

  _log_cleanup() {
    trap '' INT TERM TSTP
    # 1) 프로세스 그룹 전체에 SIGCONT: STOPPED 프로세스를 먼저 깨움
    #    (Ctrl+Z 직후 tail/awk가 stopped 상태일 수 있으므로)
    kill -CONT -- -$$ 2>/dev/null
    # 2) 추적된 tail + awk/tee PID에 SIGTERM
    [ -n "$_bg_pids" ] && kill $_bg_pids 2>/dev/null
    rm -rf "$_tmpdir" 2>/dev/null
    exit 0
  }
  trap '_log_cleanup' INT TERM TSTP

  mkdir -p "$_tmpdir" || _tmpdir=""

  for svc in "$@"; do
    logfile="`resolve_log "$svc"`"
    if [ -z "$logfile" ]; then echo "ERROR: unknown service: $svc"; continue; fi
    if [ ! -f "$logfile" ]; then echo "ERROR: log not found: $logfile"; continue; fi
    echo "`now` | TAIL `svc_label "$svc"` -> $logfile"

    # FIFO로 파이프라인 분리해 tail PID를 별도 추적
    _fifo=""
    if [ -n "$_tmpdir" ]; then
      _fifo="$_tmpdir/pipe_$svc"
      mkfifo "$_fifo" 2>/dev/null || _fifo=""
    fi

    if [ -p "$_fifo" ]; then
      # tail PID 추적
      tail -f "$logfile" > "$_fifo" &
      _bg_pids="$_bg_pids $!"

      if [ -n "$out_file" ]; then
        # logc: tee PID 추적. kill tee → awk SIGPIPE → (fifo 닫힘) → tail SIGPIPE
        awk -v svc="$svc" '{print "[" svc "] " $0; fflush()}' < "$_fifo" | tee -a "$out_file" &
      else
        # log: awk PID 추적. kill awk → (fifo 닫힘) → tail SIGPIPE
        awk -v svc="$svc" '{print "[" svc "] " $0; fflush()}' < "$_fifo" &
      fi
      _bg_pids="$_bg_pids $!"
    else
      # mkfifo 불가 시 fallback: 마지막 PID만 추적 + 그룹 kill로 보완
      if [ -n "$out_file" ]; then
        tail -f "$logfile" | awk -v svc="$svc" '{print "[" svc "] " $0; fflush()}' | tee -a "$out_file" &
      else
        tail -f "$logfile" | awk -v svc="$svc" '{print "[" svc "] " $0; fflush()}' &
      fi
      _bg_pids="$_bg_pids $!"
    fi
  done

  wait
  exit 0
fi

rc_all=0

# ----------------------------
# restart
# ----------------------------
if [ "$action" = "restart" ]; then
  for svc in "$@"; do
    pid="`get_running_pid "$svc"`"
    if do_stop "$svc"; then
      if [ -n "$pid" ]; then echo "[STOP] `svc_label "$svc"` (pid=$pid)"
      else echo "[STOP] `svc_label "$svc"` (pid=UNKNOWN)"; fi
    else
      echo "[STOP-FAIL] `svc_label "$svc"`"
      rc_all=1
    fi
  done

  for svc in "$@"; do
    if ! wait_down "$svc" "$STOP_WAIT_SEC"; then
      pid="`get_running_pid "$svc"`"
      if [ -n "$pid" ]; then
        echo "[STOP-WAIT-TIMEOUT] `svc_label "$svc"` (pid=$pid)"
        rc_all=1
      fi
    fi
  done

  for svc in "$@"; do
    if do_start "$svc"; then
      # FIX: sleep 1 대신 wait_up으로 실제 기동 확인
      pid="`wait_up "$svc" "$START_WAIT_SEC"`"
      if [ -n "$pid" ]; then echo "[START] `svc_label "$svc"` (pid=$pid)"
      else echo "[START] `svc_label "$svc"` (pid=UNKNOWN)"; fi
    else
      echo "[START-FAIL] `svc_label "$svc"`"
      rc_all=1
    fi
  done

  exit $rc_all
fi

# ----------------------------
# check
# ----------------------------
if [ "$action" = "check" ]; then
  for svc in "$@"; do
    check_service "$svc" || rc_all=1
  done
  exit $rc_all
fi

# ----------------------------
# start / stop / kill / backup
# ----------------------------
for svc in "$@"; do
  case "$action" in
    start)
      oldpid="`get_running_pid "$svc"`"
      if [ -n "$oldpid" ]; then
        echo "[START] `svc_label "$svc"` (pid=$oldpid) (ALREADY RUNNING)"
        continue
      fi

      if do_start "$svc"; then
        # FIX: sleep 1 대신 wait_up으로 실제 기동 확인
        pid="`wait_up "$svc" "$START_WAIT_SEC"`"
        if [ -n "$pid" ]; then echo "[START] `svc_label "$svc"` (pid=$pid)"
        else echo "[START] `svc_label "$svc"` (pid=UNKNOWN)"; fi
      else
        echo "[START-FAIL] `svc_label "$svc"`"
        rc_all=1
      fi
      ;;
    stop)
      pid="`get_running_pid "$svc"`"
      if do_stop "$svc"; then
        if [ -n "$pid" ]; then echo "[STOP] `svc_label "$svc"` (pid=$pid)"
        else echo "[STOP] `svc_label "$svc"` (pid=UNKNOWN)"; fi
      else
        echo "[STOP-FAIL] `svc_label "$svc"`"
        rc_all=1
      fi
      ;;
    kill)
      # FIX: do_kill이 동기 실행으로 바뀌어 실제 실패 시 KILL-FAIL 출력 가능
      pid="`get_running_pid "$svc"`"
      if do_kill "$svc"; then
        if [ -n "$pid" ]; then echo "[KILL] `svc_label "$svc"` (pid=$pid)"
        else echo "[KILL] `svc_label "$svc"` (pid=UNKNOWN)"; fi
      else
        echo "[KILL-FAIL] `svc_label "$svc"`"
        rc_all=1
      fi
      ;;
    backup)
      # FIX: do_backup이 동기 실행으로 바뀌어 성공 시에만 완료 메시지 출력
      src="`resolve_backup_dir "$svc"`"
      do_backup "$svc"
      rc=$?
      if [ "$rc" -eq 0 ]; then
        echo "[BACKUP] `svc_label "$svc"` ($src -> ${src}_`backup_date`)"
      elif [ "$rc" -ne 10 ]; then
        echo "[BACKUP-FAIL] `svc_label "$svc"`"
        rc_all=1
      fi
      ;;
  esac
done

exit $rc_all
