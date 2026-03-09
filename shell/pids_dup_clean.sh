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
  rows=`get_rows "$key"`
  pids=`echo "$rows" | awk '{print $2}'`
  cnt=0

  for pid in $pids
  do
    cnt=`expr $cnt + 1`
  done

  if [ "$cnt" -eq 0 ]; then
    echo "[CHECK] key=$key count=0 status=DOWN"
    return 0
  fi

  if [ "$cnt" -eq 1 ]; then
    echo "[CHECK] key=$key count=1 status=OK pid=$pids"
    return 0
  fi

  echo "[CHECK] key=$key count=$cnt status=DUPLICATED pids=$pids"
  return 1
}

kill_pid_list() {
  pids="$1"

  for pid in $pids
  do
    echo "[TERM] pid=$pid"
    kill -15 "$pid" 2>/dev/null
  done

  sleep 5

  for pid in $pids
  do
    if kill -0 "$pid" 2>/dev/null; then
      echo "[KILL] pid=$pid"
      kill -9 "$pid" 2>/dev/null
    fi
  done
}

cleanup_all() {
  key="$1"
  rows=`get_rows "$key"`
  pids=`echo "$rows" | awk '{print $2}' | sort -n`
  cnt=0

  for pid in $pids
  do
    cnt=`expr $cnt + 1`
  done

  if [ "$cnt" -eq 0 ]; then
    echo "[CLEANALL] key=$key count=0 status=DOWN"
    return 0
  fi

  echo "[CLEANALL] key=$key count=$cnt status=KILL-ALL pids=$pids"
  echo "$rows"
  kill_pid_list "$pids"
  return 0
}

cleanup_dup() {
  key="$1"
  rows=`get_rows "$key"`
  pids=`echo "$rows" | awk '{print $2}' | sort -n`

  cnt=0
  keep_pid=""

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
    return 0
  fi

  kill_pids=""
  for pid in $pids
  do
    if [ "$pid" != "$keep_pid" ]; then
      kill_pids="$kill_pids $pid"
    fi
  done

  echo "[CLEANDUP] key=$key count=$cnt status=DUPLICATED keep_pid=$keep_pid kill_pids=`echo "$kill_pids" | awk '{$1=$1; print}'`"
  echo "$rows"

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