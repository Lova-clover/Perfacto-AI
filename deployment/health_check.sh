#!/bin/bash
# 헬스 체크 스크립트

echo "🏥 Perfacto-AI 헬스 체크"
echo "=========================="
echo ""

# Redis 상태
echo "1. Redis 상태:"
if systemctl is-active --quiet redis-server; then
    echo "   ✅ Redis: 실행 중"
else
    echo "   ❌ Redis: 중지됨"
fi
echo ""

# Python 환경
echo "2. Python 환경:"
if [ -d "venv" ]; then
    echo "   ✅ 가상환경: 존재"
    source venv/bin/activate
    echo "   Python 버전: $(python --version)"
else
    echo "   ❌ 가상환경: 없음"
fi
echo ""

# .env 파일
echo "3. 환경 변수:"
if [ -f ".env" ]; then
    echo "   ✅ .env 파일: 존재"
    if grep -q "OPENAI_API_KEY=sk-" .env; then
        echo "   ✅ OPENAI_API_KEY: 설정됨"
    else
        echo "   ⚠️  OPENAI_API_KEY: 미설정"
    fi
else
    echo "   ❌ .env 파일: 없음"
fi
echo ""

# 디스크 공간
echo "4. 디스크 공간:"
df -h . | tail -1
echo ""

# 최근 로그
echo "5. 최근 로그 (마지막 5줄):"
if [ -f "logs/production.log" ]; then
    tail -5 logs/production.log
else
    echo "   ⚠️  로그 파일 없음"
fi
echo ""
