#!/bin/bash
# 시스템 상태 확인 스크립트

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "🏥 Perfacto-AI 시스템 상태 확인"
echo "================================"
echo ""

# 1. 메모리 상태
echo "💾 메모리 상태:"
free -h
echo ""

# 2. 디스크 상태
echo "💿 디스크 상태:"
df -h / | tail -n 1
echo ""

# 3. Redis 상태
echo "🔧 Redis 상태:"
if systemctl is-active --quiet redis-server; then
    echo "✅ Redis 실행 중"
    redis-cli ping > /dev/null 2>&1 && echo "✅ Redis PING 정상" || echo "❌ Redis PING 실패"
    echo "   메모리: $(redis-cli info memory | grep used_memory_human | cut -d: -f2)"
else
    echo "❌ Redis 중지됨"
fi
echo ""

# 4. Python 가상환경 확인
echo "🐍 Python 환경:"
if [ -d "$PROJECT_DIR/venv" ]; then
    echo "✅ 가상환경 존재"
    source "$PROJECT_DIR/venv/bin/activate"
    python --version
else
    echo "❌ 가상환경 없음 (deploy.sh 실행 필요)"
fi
echo ""

# 5. .env 파일 확인
echo "⚙️ 설정 파일:"
if [ -f "$PROJECT_DIR/.env" ]; then
    echo "✅ .env 파일 존재"
    # API 키 존재 여부만 체크 (값은 보여주지 않음)
    grep -q "OPENAI_API_KEY=" "$PROJECT_DIR/.env" && echo "   ✅ OPENAI_API_KEY 설정됨" || echo "   ❌ OPENAI_API_KEY 없음"
    grep -q "GOOGLE_API_KEY=" "$PROJECT_DIR/.env" && echo "   ✅ GOOGLE_API_KEY 설정됨" || echo "   ❌ GOOGLE_API_KEY 없음"
    grep -q "AWS_ACCESS_KEY_ID=" "$PROJECT_DIR/.env" && echo "   ✅ AWS_ACCESS_KEY_ID 설정됨" || echo "   ❌ AWS_ACCESS_KEY_ID 없음"
else
    echo "❌ .env 파일 없음 (deploy.sh 실행 필요)"
fi
echo ""

# 6. 크론잡 확인
echo "⏰ 크론잡:"
if crontab -l 2>/dev/null | grep -q "weekly-science-premium\|weekly-chess-premium\|weekly-history-premium"; then
    echo "✅ 크론잡 설정됨"
    crontab -l | grep "weekly-" | wc -l | xargs echo "   설정된 작업 수:"
else
    echo "❌ 크론잡 없음 (cron_setup.sh 실행 필요)"
fi
echo ""

# 7. 최근 로그
echo "📋 최근 로그 (마지막 5줄):"
if [ -f "$PROJECT_DIR/logs/cron.log" ]; then
    tail -n 5 "$PROJECT_DIR/logs/cron.log"
else
    echo "   로그 파일 없음"
fi
echo ""

echo "================================"
echo "✅ 상태 확인 완료"
echo ""
