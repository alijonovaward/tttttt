#!/bin/bash

# Переход в папку, где находится manage.py
cd "$(dirname "$0")"

# Параметры организации и дат
ORG_ID=6
START_DATE="2025-07-13"
END_DATE="2025-07-07"
TODAY=$(date +%F)

# Логи для Errors
LOG_FILE_ERRORS="org${ORG_ID}_${TODAY}_errors.txt"

python manage.py shell <<EOF > "${LOG_FILE_ERRORS}" 2>&1
from datetime import date
from zapp.services.weeks_init import backfill_ErrorReports
from zapp.models import Organization

org = Organization.objects.get(id=${ORG_ID})
start_date = date.fromisoformat("${START_DATE}")
end_date = date.fromisoformat("${END_DATE}")

backfill_ErrorReports(org, start_date, end_date)
EOF

# Логи для Factors
LOG_FILE_FACTORS="org${ORG_ID}_${TODAY}_factors.txt"

python manage.py shell <<EOF > "${LOG_FILE_FACTORS}" 2>&1
from datetime import date
from zapp.services.weeks_init import backfill_FactorReports
from zapp.models import Organization

org = Organization.objects.get(id=${ORG_ID})
start_date = date.fromisoformat("${START_DATE}")
end_date = date.fromisoformat("${END_DATE}")

backfill_FactorReports(org, start_date, end_date)
EOF