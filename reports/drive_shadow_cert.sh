#!/bin/bash
API_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2)
COOKIE=/tmp/cookies.txt
LOG=/app/reports/shadow_cert_progress.log
> $LOG
for i in $(seq 1 24); do
  sleep 30
  RESP=$(curl -s -b $COOKIE -X POST "$API_URL/api/arbicore/certification/shadow/tick")
  STATUS=$(echo "$RESP" | python3 -c "import sys,json;d=json.load(sys.stdin);r=d.get('run') or {};print(r.get('status','?'),r.get('cycles_completed','?'),'/',r.get('target_cycles','?'))" 2>/dev/null)
  echo "$(date +%H:%M:%S) tick $i status=$STATUS" >> $LOG
  echo "$RESP" | python3 -c "import sys,json;d=json.load(sys.stdin);r=d.get('run') or {};sys.exit(0 if r.get('status') in ('PASS','WARNING','FAIL','ABORTED') else 1)" 2>/dev/null
  if [ $? -eq 0 ]; then
    echo "$(date +%H:%M:%S) TERMINAL reached; stopping loop" >> $LOG
    break
  fi
done
