#!/bin/bash
# 크론잡 자동 설정 스크립트

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "⏰ 크론잡 설정 중..."

# 크론잡 추가 (매주 월요일 오전 9시 - 과학)
CRON_SCIENCE="0 9 * * 1 cd $PROJECT_DIR && source venv/bin/activate && python runner.py --job-config deployment/production_job_config.yaml --job-name weekly-science-premium >> logs/cron.log 2>&1"

# 체스 (매주 수요일 오전 9시)
CRON_CHESS="0 9 * * 3 cd $PROJECT_DIR && source venv/bin/activate && python runner.py --job-config deployment/production_job_config.yaml --job-name weekly-chess-premium >> logs/cron.log 2>&1"

# 역사 (매주 금요일 오전 9시)
CRON_HISTORY="0 9 * * 5 cd $PROJECT_DIR && source venv/bin/activate && python runner.py --job-config deployment/production_job_config.yaml --job-name weekly-history-premium >> logs/cron.log 2>&1"

# 기존 크론잡 확인 및 추가
(crontab -l 2>/dev/null | grep -v "weekly-science-premium" | grep -v "weekly-chess-premium" | grep -v "weekly-history-premium"; echo "$CRON_SCIENCE"; echo "$CRON_CHESS"; echo "$CRON_HISTORY") | crontab -

echo "✅ 크론잡이 설정되었습니다!"
echo ""
echo "📅 스케줄:"
echo "  - 과학: 매주 월요일 오전 9시"
echo "  - 체스: 매주 수요일 오전 9시"
echo "  - 역사: 매주 금요일 오전 9시"
echo ""
echo "현재 크론잡 목록:"
crontab -l
echo ""
echo "💡 로그 확인: tail -f $PROJECT_DIR/logs/cron.log"
echo ""
