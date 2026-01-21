#!/bin/bash
# 수동 실행 스크립트 (테스트용)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 가상환경 활성화
if [ ! -d "venv" ]; then
    echo "❌ 가상환경이 없습니다. deploy.sh를 먼저 실행하세요."
    exit 1
fi

source venv/bin/activate

# 작업 선택
echo "📹 Perfacto-AI 수동 실행"
echo ""
echo "작업 선택:"
echo "  1) 프리미엄 과학 (premium_science)"
echo "  2) 프리미엄 체스 (premium_chess)"
echo "  3) 프리미엄 역사 (premium_history)"
echo "  4) AWS 프리 티어용 (aws-free-tier-science)"
echo ""
read -p "선택 (1-4): " choice

case $choice in
    1)
        JOB_NAME="weekly-science-premium"
        CONFIG="deployment/production_job_config.yaml"
        ;;
    2)
        JOB_NAME="weekly-chess-premium"
        CONFIG="deployment/production_job_config.yaml"
        ;;
    3)
        JOB_NAME="weekly-history-premium"
        CONFIG="deployment/production_job_config.yaml"
        ;;
    4)
        JOB_NAME="aws-free-tier-science"
        CONFIG="deployment/aws_free_tier_config.yaml"
        ;;
    *)
        echo "❌ 잘못된 선택"
        exit 1
        ;;
esac

echo ""
echo "🚀 실행 중: $JOB_NAME"
echo "⏳ 이 작업은 5-10분 소요됩니다..."
echo ""

python runner.py \
    --job-config "$CONFIG" \
    --job-name "$JOB_NAME"

echo ""
echo "✅ 완료! 결과는 output/ 폴더를 확인하세요."
echo ""
