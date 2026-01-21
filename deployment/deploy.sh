#!/bin/bash
# Perfacto-AI 완전 자동 배포 스크립트 (Ubuntu 22.04 LTS)

set -e

echo "🚀 Perfacto-AI 배포를 시작합니다..."

# 프로젝트 디렉토리
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 1. 시스템 패키지 업데이트 및 설치
echo "📦 시스템 패키지 설치 중..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3.11 python3.11-venv python3-pip \
    ffmpeg imagemagick \
    redis-server \
    git curl wget

# 2. Redis 시작
echo "🔧 Redis 시작..."
sudo systemctl enable redis-server
sudo systemctl start redis-server

# 3. Python 가상환경 생성
echo "🐍 Python 가상환경 생성..."
if [ ! -d "venv" ]; then
    python3.11 -m venv venv
fi
source venv/bin/activate

# 4. Python 패키지 설치
echo "📚 Python 패키지 설치..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 5. 디렉토리 생성
echo "📁 디렉토리 생성..."
mkdir -p output/{science,chess,history,free_tier}
mkdir -p logs
mkdir -p assets/fonts

# 6. .env 파일 설정 (없으면 생성)
if [ ! -f .env ]; then
    echo "⚙️ .env 파일 생성..."
    cp deployment/.env.example .env
    echo ""
    echo "⚠️  다음 명령어로 API 키를 입력하세요:"
    echo "    nano .env"
    echo ""
    echo "필수 키:"
    echo "  - OPENAI_API_KEY"
    echo "  - GOOGLE_API_KEY"
    echo "  - AWS_ACCESS_KEY_ID (Polly 사용 시)"
    echo "  - AWS_SECRET_ACCESS_KEY"
    echo ""
fi

# 7. 권한 설정
echo "🔐 권한 설정..."
chmod +x deployment/*.sh
chmod +x runner.py

echo ""
echo "✅ 배포가 완료되었습니다!"
echo ""
echo "📋 다음 단계:"
echo "1. API 키 설정: nano .env"
echo "2. 테스트 실행: cd deployment && ./run_manual.sh"
echo "3. 자동화 설정: ./cron_setup.sh"
echo ""
echo "🆓 AWS 프리 티어 사용 시:"
echo "   ./setup_aws_free_tier.sh 먼저 실행하세요"
echo ""
