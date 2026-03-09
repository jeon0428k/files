#!/bin/sh

ANYFRAME_HOME=/app/anyframe      # ← 환경에 맞게
MAIL_CLASS=com.anyframe.batch.common.util.MailUtil

TO="$1"
SUBJECT="$2"
BODY_FILE="$3"

$ANYFRAME_HOME/bin/batch-run.sh $MAIL_CLASS \
  -to "$TO" \
  -subject "$SUBJECT" \
  -body "$BODY_FILE"


# ./send_anyframe_mail.sh ops@company.com "WEB DOWN" /tmp/mail_body.txt
