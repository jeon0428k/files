#!/bin/sh

usage() {
  echo "Usage:"
  echo "  $0 check <key>"
  echo "  $0 cleanall <key>"
  echo "  $0 cleandup <key>"
  echo ""
  echo "Example:"
  echo "  $0 check -DNAME=web1"
  echo "  $0 cleanall -DNAME=web1"
  echo "  $0 cleandup -DNAME=web1"
  exit 1
}

get_rows() {
  key="$1"
  ps -ef | grep java | grep -- "$key" | grep -v grep
}

get_pids() {
  key="$1"
  get_rows "$key" | awk '{print $2}' | sort -n
}

get_pid_content() {
  key="$1"
  get_rows "$key" | awk '{print "pid=" $2 " content=" $9}'
}

count_pids() {
  key="$1"
  pids=`get_pids "$key"`

  cnt=0
  for pid in $pids
  do
    cnt=`expr $cnt + 1`
  done

  echo "$cnt"
}

check_dup() {
  key="$1"
  pids=`get_pids "$key"`
  details=`get_pid_content "$key"`
  cnt=0
  pid_list=""

  for pid in $pids
  do
    cnt=`expr $cnt + 1`
    if [ -z "$pid_list" ]; then
      pid_list="$pid"
    else
      pid_list="$pid_list $pid"
    fi
  done

  if [ "$cnt" -eq 0 ]; then
    echo "[CHECK] key=$key count=0 status=DOWN"
    return 0
  fi

  if [ "$cnt" -eq 1 ]; then
    echo "[CHECK] key=$key count=1 status=OK pid=$pid_list"
    echo "$details"
    return 0
  fi

  echo "[CHECK] key=$key count=$cnt status=DUPLICATED pids=$pid_list"
  echo "$details"
  return 1
}

kill_pid_list() {
  pids="$1"

  for pid in $pids
  do
    case "$pid" in
      ''|*[!0-9]*)
        echo "[SKIP] invalid pid=$pid"
        ;;
      *)
        echo "[TERM] pid=$pid"
        kill -15 "$pid" 2>/dev/null
        ;;
    esac
  done

  sleep 5

  for pid in $pids
  do
    case "$pid" in
      ''|*[!0-9]*)
        ;;
      *)
        if kill -0 "$pid" 2>/dev/null; then
          echo "[KILL] pid=$pid"
          kill -9 "$pid" 2>/dev/null
        fi
        ;;
    esac
  done
}

cleanup_all() {
  key="$1"
  pids=`get_pids "$key"`
  details=`get_pid_content "$key"`
  cnt=0
  pid_list=""

  for pid in $pids
  do
    cnt=`expr $cnt + 1`
    if [ -z "$pid_list" ]; then
      pid_list="$pid"
    else
      pid_list="$pid_list $pid"
    fi
  done

  if [ "$cnt" -eq 0 ]; then
    echo "[CLEANALL] key=$key count=0 status=DOWN"
    return 0
  fi

  echo "[CLEANALL] key=$key count=$cnt status=KILL-ALL pids=$pid_list"
  echo "$details"
  kill_pid_list "$pid_list"
  return 0
}

cleanup_dup() {
  key="$1"
  pids=`get_pids "$key"`
  details=`get_pid_content "$key"`

  cnt=0
  keep_pid=""
  kill_pids=""

  for pid in $pids
  do
    cnt=`expr $cnt + 1`
    keep_pid="$pid"
  done

  if [ "$cnt" -eq 0 ]; then
    echo "[CLEANDUP] key=$key count=0 status=DOWN"
    return 0
  fi

  if [ "$cnt" -eq 1 ]; then
    echo "[CLEANDUP] key=$key count=1 status=OK keep_pid=$keep_pid"
    echo "$details"
    return 0
  fi

  for pid in $pids
  do
    if [ "$pid" != "$keep_pid" ]; then
      if [ -z "$kill_pids" ]; then
        kill_pids="$pid"
      else
        kill_pids="$kill_pids $pid"
      fi
    fi
  done

  echo "[CLEANDUP] key=$key count=$cnt status=DUPLICATED keep_pid=$keep_pid kill_pids=$kill_pids"
  echo "$details"

  kill_pid_list "$kill_pids"
  return 0
}

action="$1"
key="$2"

[ -n "$action" ] && [ -n "$key" ] || usage

case "$action" in
  check)
    check_dup "$key"
    ;;
  cleanall)
    cleanup_all "$key"
    ;;
  cleandup)
    cleanup_dup "$key"
    ;;
  *)
    usage
    ;;
esac