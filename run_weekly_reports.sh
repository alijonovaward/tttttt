#!/bin/bash

# Переход в папку, где находится manage.py
cd "$(dirname "$0")"

ORG_ID=4
TODAY=$(date +%F)
LOG_FILE="org${ORG_ID}_${TODAY}.txt"

python manage.py shell <<EOF > "${LOG_FILE}" 2>&1
from datetime import date
from zapp.services.weeks_init import backfill_and_analyze_for_org_with_prompt
from zapp.models import Organization

org = Organization.objects.get(id=${ORG_ID})
start_date = date(2025, 4, 7)
end_date = date(2025, 6, 29)

backfill_and_analyze_for_org_with_prompt(org, start_date, end_date, None)
EOF