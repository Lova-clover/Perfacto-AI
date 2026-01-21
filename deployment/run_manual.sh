#!/bin/bash
# 수동 테스트 실행 스크립트

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "🎬 Perfacto-AI 수동 실행 중..."
echo ""

# 가상환경 활성화
source venv/bin/activate

# runner.py 실행
python runner.py \
    --job-config deployment/production_job_config.yaml \
    --job-name weekly-science-premium

echo ""
echo "✅ 실행 완료!"
echo "출력 파일: output/science/"
echo ""
