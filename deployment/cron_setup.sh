#!/bin/bash
# 크론잡 자동 설정 스크립트

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "⏰ 크론잡 설정 중..."

# 크론잡 추가 (매주 월요일 오전 9시)
CRON_CMD="0 9 * * 1 cd $PROJECT_DIR && source venv/bin/activate && python runner.py --job-config deployment/production_job_config.yaml --job-name weekly-science-premium >> logs/cron.log 2>&1"

# 기존 크론잡 확인
if crontab -l 2>/dev/null | grep -q "weekly-science-premium"; then
    echo "⚠️  크론잡이 이미 존재합니다."
else
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "✅ 크론잡이 추가되었습니다: 매주 월요일 오전 9시"
fi

echo ""
echo "현재 크론잡 목록:"
crontab -l
echo ""
