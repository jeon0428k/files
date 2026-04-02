#!/bin/sh
# HP-UX / POSIX sh

usage() {
  echo "Usage: svc {start|stop|restart|kill|check|log|logc|backup} [more...]"
  exit 1
}

LOG_BASE_PATH="./logs"
LOG_FILE_NAME="svc.log"

# restart stop-wait timeout (seconds)
STOP_WAIT_SEC=60

# internal state
STATE_DIR="/tmp/svc_state"
START_WAIT_SEC=15

# ----------------------------
# arg normalize (web -> w1 w2 w3)
# ----------------------------
expand_services() {
  out=""
  for a in "$@"
  do
    case "$a" in
      all)
        out="$out w1 w2 w3"
        ;;
      web)
        out="$out w1 w2 w3"
        ;;
      *)
        out="$out $a"
        ;;
    esac
  done
  echo "$out" | awk '{$1=$1; print}'
}

# ----------------------------
# service mapping
# ----------------------------
resolve_start() {
  case "$1" in
    w1) echo "/Users/jeon/works/wsp/dummy-server/files/web1/start.sh" ;;
    w2) echo "/Users/jeon/works/wsp/dummy-server/files/web2/start.sh" ;;
    w3) echo "/Users/jeon/works/wsp/dummy-server/files/web3/start.sh" ;;
    *) echo "" ;;
  esac
}

resolve_stop() {
  case "$1" in
    w1) echo "/Users/jeon/works/wsp/dummy-server/files/web1/stop.sh" ;;
    w2) echo "/Users/jeon/works/wsp/dummy-server/files/web2/stop.sh" ;;
    w3) echo "/Users/jeon/works/wsp/dummy-server/files/web3/stop.sh" ;;
    *) echo "" ;;
  esac
}

resolve_log() {
  case "$1" in
    w1) echo "/Users/jeon/works/wsp/dummy-server/files/logs/web1.log" ;;
    w2) echo "/Users/jeon/works/wsp/dummy-server/files/logs/web2.log" ;;
    w3) echo "/Users/jeon/works/wsp/dummy-server/files/logs/web3.log" ;;
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

# -DNAME=web1 -> web1
resolve_svc_name() {
  key="`resolve_pskey "$1"`"
  [ -n "$key" ] || return 1
  echo "$key" | sed 's/^-DNAME=//'
}

# w1 -> w1(web1)
svc_label() {
  name="`resolve_svc_name "$1"`"
  if [ -n "$name" ]; then
    echo "$1($name)"
  else
    echo "$1"
  fi
}

resolve_health_url() {
  case "$1" in
    w1) echo "http://127.0.0.1:18081/ping" ;;
    #w2) echo "http://127.0.0.1:18082/ping" ;;
    #w3) echo "http://127.0.0.1:18083/ping" ;;
    #w1) echo "/Users/jeon/works/wsp/dummy-server/files/web1/urlCheck.log" ;;
    w2) echo "/Users/jeon/works/wsp/dummy-server/files/web2/urlCheck.log" ;;
    w3) echo "/Users/jeon/works/wsp/dummy-server/files/web3/urlCheck.log" ;;
    *) echo "" ;;
  esac
}

# ★ backup 대상 source dir 매핑 (환경에 맞게 수정)
resolve_backup_dir() {
  case "$1" in
    w1) echo "/Users/jeon/works/wsp/dummy-server/files/web1" ;;
    w2) echo "/Users/jeon/works/wsp/dummy-server/files/web2" ;;
    w3) echo "/Users/jeon/works/wsp/dummy-server/files/web3" ;;
    *) echo "" ;;
  esac
}

now() {
  date '+%Y-%m-%d %H:%M:%S'
}

backup_date() {
  date '+%Y%m%d'
}

# ----------------------------
# state helpers
# ----------------------------
ensure_state_dir() {
  [ -d "$STATE_DIR" ] || mkdir -p "$STATE_DIR" 2>/dev/null
}

pidfile_path() {
  echo "$STATE_DIR/$1.$2.pid"
}

helperfile_path() {
  echo "$STATE_DIR/$1.$2.helper"
}

rm_pidfile() {
  f="`pidfile_path "$1" "$2"`"
  [ -f "$f" ] && rm -f "$f"
}

read_pidfile() {
  f="`pidfile_path "$1" "$2"`"
  [ -f "$f" ] || return 1
  cat "$f" 2>/dev/null
}

write_pidfile() {
  f="`pidfile_path "$1" "$2"`"
  echo "$3" > "$f"
}

write_helperfile() {
  f="`helperfile_path "$1" "$2"`"
  echo "$3" > "$f"
}

cleanup_async_meta() {
  svc="$1"
  kind="$2"

  hf="`helperfile_path "$svc" "$kind"`"
  if [ -f "$hf" ]; then
    helper="`cat "$hf" 2>/dev/null`"
    if [ -n "$helper" ] && [ -f "$helper" ]; then
      rm -f "$helper"
    fi
    rm -f "$hf"
  fi

  rm_pidfile "$svc" "$kind"
}

make_exec_helper() {
  ensure_state_dir

  helper="$STATE_DIR/helper_$$_${RANDOM:-0}.sh"

  cat > "$helper" <<'EOF'
#!/bin/sh
mode="$1"
arg1="$2"
arg2="$3"
arg3="$4"

case "$mode" in
  script)
    dir="$arg1"
    base="$arg2"
    cd "$dir" || exit 1
    exec "./$base"
    ;;
  copy)
    src="$arg1"
    dest="$arg2"
    [ -d "$src" ] || exit 3
    [ ! -e "$dest" ] || exit 4
    exec cp -rp "$src" "$dest"
    ;;
  *)
    exit 99
    ;;
esac
EOF

  chmod 700 "$helper" 2>/dev/null || return 1
  echo "$helper"
  return 0
}

# ----------------------------
# process helpers
# ----------------------------
is_alive() {
  PID="$1"
  [ -n "$PID" ] || return 1
  kill -0 "$PID" 2>/dev/null
}

# 조용한 kill (TERM -> WAIT -> KILL)
force_kill_silent() {
  PID="$1"
  WAIT_SEC="${2:-5}"

  if ! is_alive "$PID"; then
    return 0
  fi

  kill -15 "$PID" 2>/dev/null

  i=0
  while [ $i -lt "$WAIT_SEC" ]
  do
    if ! is_alive "$PID"; then
      return 0
    fi
    sleep 1
    i=`expr $i + 1`
  done

  kill -9 "$PID" 2>/dev/null

  if is_alive "$PID"; then
    return 1
  fi

  return 0
}

get_child_pids() {
  ppid="$1"
  ps -ef | awk -v p="$ppid" '$3 == p { print $2 }'
}

kill_tree_silent() {
  root="$1"
  sig="${2:-15}"

  [ -n "$root" ] || return 0
  is_alive "$root" || return 0

  children="`get_child_pids "$root"`"
  for c in $children
  do
    kill_tree_silent "$c" "$sig"
  done

  kill "-$sig" "$root" 2>/dev/null
  return 0
}

force_kill_tree_silent() {
  root="$1"
  wait_sec="${2:-5}"

  [ -n "$root" ] || return 0
  if ! is_alive "$root"; then
    return 0
  fi

  kill_tree_silent "$root" 15

  i=0
  while [ $i -lt "$wait_sec" ]
  do
    if ! is_alive "$root"; then
      return 0
    fi
    sleep 1
    i=`expr $i + 1`
  done

  kill_tree_silent "$root" 9

  if is_alive "$root"; then
    return 1
  fi

  return 0
}

# 서비스 현재 PID 조회 (출력/중복기동 방지용)
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

# ----------------------------
# file check (content contains "OK")
# ----------------------------
file_alive() {
  f="$1"
  [ -n "$f" ] || return 2

  # 파일 없거나 읽기 불가면 FAIL
  [ -f "$f" ] || return 1
  [ -r "$f" ] || return 1

  # 파일 내용에 "OK" 문자열이 있으면 OK
  grep -q "OK" "$f" 2>/dev/null
  return $?
}

# ----------------------------
# health check (http or file)
# ----------------------------
health_alive() {
  target="$1"
  [ -n "$target" ] || return 2

  case "$target" in
    http://*|https://*)
      http_alive "$target"
      return $?
      ;;
    *)
      file_alive "$target"
      return $?
      ;;
  esac
}

# ----------------------------
# async helpers
# ----------------------------
run_script_async() {
  svc="$1"
  kind="$2"
  script="$3"

  [ -n "$script" ] || return 2
  [ -f "$script" ] || return 3
  [ -x "$script" ] || return 4

  dir=`dirname "$script"`
  base=`basename "$script"`

  helper="`make_exec_helper`" || return 5

  nohup "$helper" script "$dir" "$base" "" < /dev/null > /dev/null 2>&1 &
  pid=$!

  write_pidfile "$svc" "$kind" "$pid"
  write_helperfile "$svc" "$kind" "$helper"

  return 0
}

run_copy_async() {
  svc="$1"
  src="$2"
  dest="$3"

  [ -n "$src" ] || return 2
  [ -d "$src" ] || return 3
  [ ! -e "$dest" ] || return 10

  helper="`make_exec_helper`" || return 5

  nohup "$helper" copy "$src" "$dest" "" < /dev/null > /dev/null 2>&1 &
  pid=$!

  write_pidfile "$svc" "backup" "$pid"
  write_helperfile "$svc" "backup" "$helper"

  return 0
}

wait_start_settle() {
  svc="$1"

  i=0
  while [ $i -lt "$START_WAIT_SEC" ]
  do
    spid="`read_pidfile "$svc" start`"
    jpid="`get_running_pid "$svc"`"

    if [ -n "$spid" ] && ! is_alive "$spid"; then
      cleanup_async_meta "$svc" "start"
      return 0
    fi

    if [ -n "$jpid" ]; then
      sleep 1
      spid="`read_pidfile "$svc" start`"
      if [ -n "$spid" ] && ! is_alive "$spid"; then
        cleanup_async_meta "$svc" "start"
      fi
      return 0
    fi

    sleep 1
    i=`expr $i + 1`
  done

  return 0
}

# ----------------------------
# run start/stop/kill/backup
# ----------------------------
do_start() {
  svc="$1"
  script="`resolve_start "$svc"`"

  run_script_async "$svc" "start" "$script"
  return $?
}

do_stop() {
  svc="$1"
  script="`resolve_stop "$svc"`"

  run_script_async "$svc" "stop" "$script"
  return $?
}

do_kill() {
  svc="$1"
  pids="`get_running_pids "$svc"`"

  if [ -n "$pids" ]; then
    (
      rc=0
      for pid in $pids
      do
        force_kill_silent "$pid" 5 || rc=1
      done
      exit $rc
    ) >/dev/null 2>&1 &
  fi

  for kind in start stop backup
  do
    hpid="`read_pidfile "$svc" "$kind"`"
    if [ -n "$hpid" ]; then
      force_kill_tree_silent "$hpid" 5 >/dev/null 2>&1
      cleanup_async_meta "$svc" "$kind"
    fi
  done

  return 0
}

# backup: {source_dir}_{timestamp} 로 전체 copy (cp -rp)
do_backup() {
  svc="$1"
  src="`resolve_backup_dir "$svc"`"
  [ -n "$src" ] || return 2
  [ -d "$src" ] || return 3

  ts="`backup_date`"
  dest="${src}_${ts}"

  # 이미 백업 폴더 존재하면 즉시 중지
  if [ -e "$dest" ]; then
    echo "[BACKUP-EXISTS] `svc_label "$svc"` ($dest already exists)"
    return 10
  fi

  run_copy_async "$svc" "$src" "$dest"
  return $?
}

wait_down() {
  svc="$1"
  max="${2:-$STOP_WAIT_SEC}"

  i=0
  while [ $i -lt "$max" ]
  do
    pid="`get_running_pid "$svc"`"
    [ -z "$pid" ] && return 0
    sleep 1
    i=`expr $i + 1`
  done
  return 1
}

# ----------------------------
# check service (process + http/file)
# ----------------------------
check_service() {
  svc="$1"
  pid="`get_running_pid "$svc"`"
  health="`resolve_health_url "$svc"`"

  # 프로세스 DOWN
  if [ -z "$pid" ]; then
    # DOWN이면 web 확인 의미 없어서 SKIP 고정
    echo "[CHECK] `svc_label "$svc"` (pid=UNKNOWN) (web=SKIP)"
    return 1
  fi

  # 프로세스 UP
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

ensure_state_dir

# web -> w1 w2 w3 로 확장
set -- `expand_services "$@"`

# log / logc: 다중 tail
if [ "$action" = "log" ] || [ "$action" = "logc" ]; then
  LOG_PIDS=""
  out_file=""

  cleanup_logs() {
    for p in $LOG_PIDS
    do
      force_kill_tree_silent "$p" 3 >/dev/null 2>&1
    done
    exit 0
  }

  trap 'cleanup_logs' INT TERM EXIT

  if [ "$action" = "logc" ]; then
    out_file="$LOG_BASE_PATH/$LOG_FILE_NAME"

    # 기존 파일 있으면 백업
    if [ -f "$out_file" ]; then
      ts=`date +%Y%m%d_%H%M%S`
      mv "$out_file" "$LOG_BASE_PATH/svc_${ts}.log"
    fi

    # 새 파일 생성
    : > "$out_file" || {
      echo "ERROR: cannot create log file: $out_file"
      exit 1
    }

    echo "`now` | LOG OUTPUT -> $out_file"
  fi

  for svc in "$@"
  do
    logfile="`resolve_log "$svc"`"
    if [ -z "$logfile" ]; then
      echo "ERROR: unknown service: $svc"
      continue
    fi
    if [ ! -f "$logfile" ]; then
      echo "ERROR: log not found: $logfile"
      continue
    fi
    echo "`now` | TAIL `svc_label "$svc"` -> $logfile"

    (
      tail -f "$logfile" 2>/dev/null | awk -v svc="$svc" -v out="$out_file" '
        {
          line="[" svc "] " $0
          print line
          if (out != "") {
            print line >> out
            close(out)
          }
        }
      '
    ) &
    pid=$!
    LOG_PIDS="$LOG_PIDS $pid"
  done

  wait
  exit 0
fi

rc_all=0

# restart: stop(병렬 호출만) → down 대기 → start(호출만)
if [ "$action" = "restart" ]; then
  # 1) STOP phase
  for svc in "$@"
  do
    pid="`get_running_pid "$svc"`"
    if do_stop "$svc"; then
      if [ -n "$pid" ]; then
        echo "[STOP] `svc_label "$svc"` (pid=$pid)"
      else
        echo "[STOP] `svc_label "$svc"` (pid=UNKNOWN)"
      fi
    else
      echo "[STOP-FAIL] `svc_label "$svc"`"
      rc_all=1
    fi
  done

  for svc in "$@"
  do
    if wait_down "$svc" "$STOP_WAIT_SEC"; then
      cleanup_async_meta "$svc" "stop"
      :
    else
      pid="`get_running_pid "$svc"`"
      if [ -n "$pid" ]; then
        echo "[STOP-WAIT-TIMEOUT] `svc_label "$svc"` (pid=$pid)"
        rc_all=1
      fi
    fi
  done

  for svc in "$@"
  do
    if do_start "$svc"; then
      wait_start_settle "$svc"
      pid="`get_running_pid "$svc"`"
      if [ -n "$pid" ]; then
        echo "[START] `svc_label "$svc"` (pid=$pid)"
      else
        echo "[START] `svc_label "$svc"` (pid=UNKNOWN)"
      fi
    else
      echo "[START-FAIL] `svc_label "$svc"`"
      rc_all=1
    fi
  done

  exit $rc_all
fi

# check
if [ "$action" = "check" ]; then
  for svc in "$@"
  do
    check_service "$svc" || rc_all=1
  done
  exit $rc_all
fi

# start/stop/kill/backup
for svc in "$@"
do
  case "$action" in
    start)
      oldpid="`get_running_pid "$svc"`"
      if [ -n "$oldpid" ]; then
        echo "[START] `svc_label "$svc"` (pid=$oldpid) (ALREADY RUNNING)"
        continue
      fi

      if do_start "$svc"; then
        wait_start_settle "$svc"
        pid="`get_running_pid "$svc"`"
        if [ -n "$pid" ]; then
          echo "[START] `svc_label "$svc"` (pid=$pid)"
        else
          echo "[START] `svc_label "$svc"` (pid=UNKNOWN)"
        fi
      else
        echo "[START-FAIL] `svc_label "$svc"`"
        rc_all=1
      fi
      ;;
    stop)
      pid="`get_running_pid "$svc"`"
      if do_stop "$svc"; then
        if [ -n "$pid" ]; then
          echo "[STOP] `svc_label "$svc"` (pid=$pid)"
        else
          echo "[STOP] `svc_label "$svc"` (pid=UNKNOWN)"
        fi
      else
        echo "[STOP-FAIL] `svc_label "$svc"`"
        rc_all=1
      fi
      ;;
    kill)
      pid="`get_running_pid "$svc"`"
      if do_kill "$svc"; then
        if [ -n "$pid" ]; then
          echo "[KILL] `svc_label "$svc"` (pid=$pid)"
        else
          echo "[KILL] `svc_label "$svc"` (pid=UNKNOWN)"
        fi
      else
        echo "[KILL-FAIL] `svc_label "$svc"`"
        rc_all=1
      fi
      ;;
    backup)
      do_backup "$svc"
      rc=$?

      if [ "$rc" -eq 0 ]; then
        # 어떤 경로로 백업되는지 즉시 확인 가능하도록 출력만 해줌(실제 복사는 BG)
        src="`resolve_backup_dir "$svc"`"
        echo "[BACKUP] `svc_label "$svc"` ($src -> ${src}_`backup_date`)"
      elif [ "$rc" -eq 10 ]; then
        # do_backup 에서 이미 [BACKUP-EXISTS] 메시지 출력함
        rc_all=1
        :
      else
        echo "[BACKUP-FAIL] `svc_label "$svc"`"
        rc_all=1
      fi
      ;;
  esac
done

exit $rc_all