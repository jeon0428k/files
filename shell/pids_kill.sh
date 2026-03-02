#!/bin/ksh

if [ "$#" -eq 0 ]; then
  echo "Usage: kill_pids.sh pid1 pid2 pid3 ..."
  exit 1
fi

EXIT_CODE=0

for PID in "$@"
do
  # numeric check
  case "$PID" in
    *[!0-9]*)
      echo "[SKIP] Invalid PID: $PID"
      EXIT_CODE=1
      continue
      ;;
  esac

  # check process exists
  if ! ps -p "$PID" >/dev/null 2>&1; then
    echo "[NOT FOUND] PID $PID"
    EXIT_CODE=1
    continue
  fi

  echo "[TERM] Sending SIGTERM to PID $PID"
  kill "$PID" >/dev/null 2>&1

  sleep 2

  if ps -p "$PID" >/dev/null 2>&1; then
    echo "[KILL] Sending SIGKILL to PID $PID"
    kill -9 "$PID" >/dev/null 2>&1

    sleep 1

    if ps -p "$PID" >/dev/null 2>&1; then
      echo "[FAILED] Could not kill PID $PID"
      EXIT_CODE=1
    else
      echo "[KILLED] PID $PID"
    fi
  else
    echo "[KILLED] PID $PID"
  fi
done

exit $EXIT_CODE
