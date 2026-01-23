#!/bin/bash
# ECS Fargate 자동 배포 스크립트 (AWS CLI 필요)

set -e

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 Perfacto-AI ECS Fargate 배포 시작"
echo "======================================"
echo ""

# AWS 계정 정보
read -p "AWS Account ID: " AWS_ACCOUNT_ID
read -p "AWS Region (기본: ap-northeast-2): " AWS_REGION
AWS_REGION=${AWS_REGION:-ap-northeast-2}

ECR_REPO_NAME="perfacto-ai"
ECR_REPO_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO_NAME}"

echo ""
echo -e "${YELLOW}1단계: ECR 저장소 생성${NC}"
if aws ecr describe-repositories --repository-names ${ECR_REPO_NAME} --region ${AWS_REGION} 2>/dev/null; then
    echo "✅ ECR 저장소 이미 존재"
else
    aws ecr create-repository \
        --repository-name ${ECR_REPO_NAME} \
        --region ${AWS_REGION} \
        --image-scanning-configuration scanOnPush=true
    echo "✅ ECR 저장소 생성 완료"
fi

echo ""
echo -e "${YELLOW}2단계: Docker 이미지 빌드${NC}"
cd ..
docker build -t ${ECR_REPO_NAME}:latest .
echo "✅ Docker 이미지 빌드 완료"

echo ""
echo -e "${YELLOW}3단계: ECR 로그인${NC}"
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_REPO_URI}
echo "✅ ECR 로그인 완료"

echo ""
echo -e "${YELLOW}4단계: Docker 이미지 태그 & 푸시${NC}"
docker tag ${ECR_REPO_NAME}:latest ${ECR_REPO_URI}:latest
docker push ${ECR_REPO_URI}:latest
echo "✅ Docker 이미지 푸시 완료"

echo ""
echo -e "${YELLOW}5단계: Secrets Manager에 API 키 등록${NC}"
echo "다음 명령어로 API 키를 등록하세요:"
echo ""
echo -e "${GREEN}aws secretsmanager create-secret --name perfacto-ai/openai-api-key --secret-string \"YOUR_OPENAI_KEY\" --region ${AWS_REGION}${NC}"
echo -e "${GREEN}aws secretsmanager create-secret --name perfacto-ai/google-api-key --secret-string \"YOUR_GOOGLE_KEY\" --region ${AWS_REGION}${NC}"
echo -e "${GREEN}aws secretsmanager create-secret --name perfacto-ai/aws-access-key-id --secret-string \"YOUR_AWS_ACCESS_KEY\" --region ${AWS_REGION}${NC}"
echo -e "${GREEN}aws secretsmanager create-secret --name perfacto-ai/aws-secret-access-key --secret-string \"YOUR_AWS_SECRET_KEY\" --region ${AWS_REGION}${NC}"
echo ""
read -p "API 키 등록이 완료되었으면 Enter를 누르세요..."

echo ""
echo -e "${YELLOW}6단계: ECS Task Definition 등록${NC}"
# JSON 파일 수정 (YOUR_ACCOUNT_ID 교체)
sed "s/YOUR_ACCOUNT_ID/${AWS_ACCOUNT_ID}/g" deployment/ecs-task-definition.json > /tmp/ecs-task-definition.json

aws ecs register-task-definition \
    --cli-input-json file:///tmp/ecs-task-definition.json \
    --region ${AWS_REGION}
echo "✅ ECS Task Definition 등록 완료"

echo ""
echo -e "${YELLOW}7단계: Terraform으로 인프라 생성${NC}"
echo "다음 단계를 수행하세요:"
echo ""
echo "1. deployment/eventbridge-scheduler.tf 파일 수정"
echo "   - account_id 변수 설정"
echo "   - subnet_ids 설정 (VPC Subnet ID)"
echo "   - security_group_id 설정"
echo ""
echo "2. Terraform 실행:"
echo -e "${GREEN}cd deployment${NC}"
echo -e "${GREEN}terraform init${NC}"
echo -e "${GREEN}terraform plan${NC}"
echo -e "${GREEN}terraform apply${NC}"
echo ""

echo ""
echo "======================================"
echo -e "${GREEN}✅ 배포 완료!${NC}"
echo ""
echo "📋 다음 단계:"
echo "1. AWS Console → ECS → Clusters → perfacto-ai-cluster 확인"
echo "2. EventBridge Scheduler 확인:"
echo "   - perfacto-ai-science-daily (매일 오전 9시)"
echo "   - perfacto-ai-chess-daily (매일 오후 2시)"
echo "   - perfacto-ai-history-daily (매일 오후 7시)"
echo "3. CloudWatch Logs → /ecs/perfacto-ai 로그 확인"
echo ""
echo "💰 예상 비용: 월 $5-10 (실행 시간만 과금)"
echo ""
