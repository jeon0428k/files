#!/bin/ksh

if [ "$#" -eq 0 ]; then
  echo "Usage: show_pid_ports.sh pid1 pid2 pid3 ..."
  exit 1
fi

for PID in "$@"
do
  # numeric check
  case "$PID" in
    *[!0-9]*)
      echo "[SKIP] Invalid PID: $PID"
      continue
      ;;
  esac

  # check process exists
  if ! ps -p "$PID" >/dev/null 2>&1; then
    echo "[NOT FOUND] PID $PID"
    continue
  fi

  echo "========================================"
  echo "[PROCESS] PID $PID"
  echo "----------------------------------------"

  # process info
  ps -p "$PID" -o pid,ppid,user,etime,time,args

  echo "----------------------------------------"
  echo "[PORTS] PID $PID"

  # ports used by this PID (LISTEN only)
  PORTS=$(netstat -Aan | awk -v pid="$PID" '
    $NF == pid && $0 ~ /LISTEN/ {
      split($4, a, ".")
      print a[length(a)]
    }
  ')

  if [ -z "$PORTS" ]; then
    echo "No listening ports"
  else
    for P in $PORTS
    do
      echo "Listening Port: $P"
    done
  fi

done

echo "========================================"
exit 0
