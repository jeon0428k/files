#!/bin/sh
# HP-UX / POSIX sh
# Anyframe Batch 런처로 "메일 발송 Job" 실행하는 스크립트 템플릿

# ----------------------------
# 1) 환경 설정 (프로젝트에 맞게 수정)
# ----------------------------
JAVA_HOME="/usr/java"                  # 환경에 맞게
ANYFRAME_HOME="/app/anyframe-batch"    # Anyframe Batch 설치/배포 경로(예시)
APP_HOME="/app/my-batch-app"           # 배치 어플리케이션(메일 Job 포함) 경로(예시)

# Anyframe Batch 런처(예시)
MAIN_CLASS="com.sds.anyframe.batch.launcher.BatchJobLauncher"

# classpath: Anyframe runtime + your app libs
CP=""
CP="${CP}:${ANYFRAME_HOME}/lib/*"
CP="${CP}:${APP_HOME}/lib/*"
CP="${CP}:${APP_HOME}/conf"

LOG_DIR="${APP_HOME}/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/mail_send.`date +%Y%m%d`.log"

# ----------------------------
# 2) 입력값
# ----------------------------
TO="$1"          # 수신자 (필수)
SUBJECT="$2"     # 제목 (필수)
shift 2

if [ -z "$TO" ] || [ -z "$SUBJECT" ]; then
  echo "Usage: $0 <to> <subject> [body text ...]" 1>&2
  exit 2
fi

# 본문: 나머지 인자를 한 줄로 합치거나, 없으면 기본 메시지
BODY_TEXT="$*"
if [ -z "$BODY_TEXT" ]; then
  BODY_TEXT="(no message body)"
fi

# ----------------------------
# 3) 본문 파일 생성 (메일 Job에서 읽게)
# ----------------------------
TMP_BODY="/tmp/anyframe_mail_body.$$"
(
  echo "TO      : $TO"
  echo "SUBJECT : $SUBJECT"
  echo "TIME    : `date '+%Y-%m-%d %H:%M:%S'`"
  echo "----------------------------------------"
  echo "$BODY_TEXT"
) > "$TMP_BODY"

# ----------------------------
# 4) Anyframe Batch Job 실행
#    - 아래 args 규칙은 "프로젝트의 Job 파라미터 규칙"에 맞춰 바꿔야 함
#    - 예: jobName=MAIL_SEND, param.to, param.subject, param.bodyFile
# ----------------------------
JOB_NAME="MAIL_SEND"   # 너희 쪽에서 정의한 메일 발송 Job 이름으로 변경

echo "`date '+%F %T'` | START | to=$TO subject=$SUBJECT" >> "$LOG_FILE"

"$JAVA_HOME/bin/java" \
  -cp "$CP" \
  "$MAIN_CLASS" \
  jobName="$JOB_NAME" \
  param.to="$TO" \
  param.subject="$SUBJECT" \
  param.bodyFile="$TMP_BODY" \
  >> "$LOG_FILE" 2>&1

RC=$?

rm -f "$TMP_BODY"

if [ $RC -eq 0 ]; then
  echo "`date '+%F %T'` | OK    | rc=$RC" >> "$LOG_FILE"
  exit 0
else
  echo "`date '+%F %T'` | FAIL  | rc=$RC (see $LOG_FILE)" >> "$LOG_FILE"
  exit $RC
fi
