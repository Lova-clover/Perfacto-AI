# 🚀 AWS ECS Fargate 자동화 가이드

EventBridge Scheduler로 ECS Fargate Task를 **정해진 시간(Asia/Seoul)**에 자동 실행하는 완전 자동화 시스템입니다.

---

## 💰 비용 비교

| 방식 | 월 비용 | 장점 | 단점 |
|------|---------|------|------|
| **EC2 t2.micro 24/7** | $8-10 | 간단 | 항상 실행, 관리 필요 |
| **ECS Fargate (권장)** | **$3-7** | **실행시간만 과금**, 관리 불필요 | 초기 설정 복잡 |

### 예상 비용 계산 (ECS Fargate)
- CPU: 1 vCPU ($0.04048/시간)
- 메모리: 2GB ($0.004445/GB/시간)
- **영상 1개 생성 시간: 10분**
- **하루 3개 영상 (30분)**: 월 15시간 실행
- **월 비용: $3-5** ✨

---

## ⚡ 빠른 시작 (30분 완료)

### 사전 준비
1. AWS CLI 설치 및 설정
   ```bash
   aws configure
   # AWS Access Key ID, Secret Access Key, Region(ap-northeast-2) 입력
   ```

2. Docker 설치
   - Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop)
   - Linux: `sudo apt-get install docker.io`

3. Terraform 설치 (선택)
   - [Terraform 다운로드](https://www.terraform.io/downloads)

---

## 📦 1단계: 로컬에서 Docker 테스트

```bash
# .env 파일 생성
cp deployment/.env.example .env
nano .env  # API 키 입력

# Docker 이미지 빌드
docker build -t perfacto-ai .

# 로컬 테스트 실행
docker run --env-file .env perfacto-ai \
  --job-config deployment/production_job_config.yaml \
  --job-name weekly-science-premium
```

영상이 정상 생성되면 다음 단계로!

---

## 🚀 2단계: ECS Fargate 배포

### 자동 배포 스크립트 사용

```bash
cd deployment
chmod +x deploy_ecs.sh
./deploy_ecs.sh
```

스크립트가 자동으로 수행:
1. ECR 저장소 생성
2. Docker 이미지 빌드 & 푸시
3. ECS Task Definition 등록
4. 안내에 따라 Secrets Manager 설정

### 또는 수동 배포

#### 2-1. ECR 저장소 생성

```bash
aws ecr create-repository \
  --repository-name perfacto-ai \
  --region ap-northeast-2
```

#### 2-2. Docker 이미지 푸시

```bash
# ECR 로그인
aws ecr get-login-password --region ap-northeast-2 | \
  docker login --username AWS --password-stdin \
  YOUR_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com

# 이미지 태그 & 푸시
docker tag perfacto-ai:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/perfacto-ai:latest

docker push YOUR_ACCOUNT_ID.dkr.ecr.ap-northeast-2.amazonaws.com/perfacto-ai:latest
```

#### 2-3. Secrets Manager에 API 키 등록

```bash
aws secretsmanager create-secret \
  --name perfacto-ai/openai-api-key \
  --secret-string "sk-proj-YOUR_KEY" \
  --region ap-northeast-2

aws secretsmanager create-secret \
  --name perfacto-ai/google-api-key \
  --secret-string "AIza-YOUR_KEY" \
  --region ap-northeast-2

aws secretsmanager create-secret \
  --name perfacto-ai/aws-access-key-id \
  --secret-string "AKIA-YOUR_KEY" \
  --region ap-northeast-2

aws secretsmanager create-secret \
  --name perfacto-ai/aws-secret-access-key \
  --secret-string "YOUR_SECRET" \
  --region ap-northeast-2
```

#### 2-4. ECS Task Definition 등록

```bash
# ecs-task-definition.json 수정 (YOUR_ACCOUNT_ID 교체)
sed -i 's/YOUR_ACCOUNT_ID/123456789012/g' deployment/ecs-task-definition.json

# 등록
aws ecs register-task-definition \
  --cli-input-json file://deployment/ecs-task-definition.json
```

---

## ⏰ 3단계: EventBridge Scheduler 설정

### Terraform 사용 (권장)

```bash
cd deployment

# terraform.tfvars 생성
cat > terraform.tfvars <<EOF
account_id        = "123456789012"
subnet_ids        = ["subnet-xxxxx", "subnet-yyyyy"]
security_group_id = "sg-xxxxx"
EOF

# Terraform 실행
terraform init
terraform plan
terraform apply
```

### 또는 AWS Console 사용

1. **EventBridge Scheduler** 이동
2. **스케줄 생성** 클릭
3. 설정:
   - **이름**: `perfacto-ai-science-daily`
   - **스케줄 표현식**: `cron(0 9 * * ? *)`
   - **시간대**: `Asia/Seoul`
   - **대상**: ECS Fargate Task
   - **클러스터**: `perfacto-ai-cluster`
   - **Task Definition**: `perfacto-ai-task:latest`
   - **명령 오버라이드**:
     ```json
     [
       "--job-config",
       "deployment/production_job_config.yaml",
       "--job-name",
       "weekly-science-premium"
     ]
     ```

---

## 📊 스케줄 설정 예시

| 작업 | 실행 시간 | Cron 표현식 | 설명 |
|------|-----------|-------------|------|
| 과학 | 매일 오전 9시 | `cron(0 9 * * ? *)` | Asia/Seoul |
| 체스 | 매일 오후 2시 | `cron(0 14 * * ? *)` | Asia/Seoul |
| 역사 | 매일 오후 7시 | `cron(0 19 * * ? *)` | Asia/Seoul |

**Cron 표현식 형식**: `cron(분 시 일 월 요일 년)`
- `0 9 * * ? *`: 매일 오전 9시
- `0 */6 * * ? *`: 6시간마다
- `0 9 ? * MON *`: 매주 월요일 오전 9시

---

## 🔍 모니터링 & 문제 해결

### CloudWatch Logs 확인

```bash
# 최근 로그 확인
aws logs tail /ecs/perfacto-ai --follow
```

### ECS Task 수동 실행 (테스트)

```bash
aws ecs run-task \
  --cluster perfacto-ai-cluster \
  --task-definition perfacto-ai-task \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=ENABLED}"
```

### 일반적인 문제

#### 1. Task가 실패 (Exit Code 1)
- **CloudWatch Logs 확인**: API 키 오류, 메모리 부족 등
- **해결**: Secrets Manager 키 확인, 메모리 증가

#### 2. Docker 이미지 푸시 실패
- **ECR 로그인 재시도**
- **Docker Desktop 실행 확인**

#### 3. Secrets Manager 접근 실패
- **IAM Role 권한 확인**: Task Execution Role에 `secretsmanager:GetSecretValue` 권한 필요

---

## 🎯 고급 설정

### 메모리/CPU 조정

`ecs-task-definition.json` 수정:
```json
{
  "cpu": "2048",      // 2 vCPU (더 빠름)
  "memory": "4096"    // 4GB (대용량 작업)
}
```

### S3에 영상 자동 업로드

1. S3 버킷 생성
   ```bash
   aws s3 mb s3://perfacto-ai-videos
   ```

2. Task Role에 S3 권한 추가
   ```json
   {
     "Effect": "Allow",
     "Action": ["s3:PutObject"],
     "Resource": "arn:aws:s3:::perfacto-ai-videos/*"
   }
   ```

3. `runner.py`에서 S3 업로드 코드 추가

---

## 💡 비용 절약 팁

1. **Fargate Spot 사용** (최대 70% 할인)
   - `eventbridge-scheduler.tf`에서 `capacityProviderStrategy` 추가

2. **필요한 시간만 실행**
   - 주 3회만 실행: 월 $1-2

3. **CloudWatch Logs 보존 기간 단축**
   - 7일 → 3일로 변경

---

## 📞 지원

문제 발생 시:
1. CloudWatch Logs 확인
2. ECS Task 상태 확인
3. GitHub Issues 등록

---

## 🎉 완료!

이제 **완전 자동화된 영상 생성 시스템**이 구축되었습니다!

- ✅ 정해진 시간에 자동 실행
- ✅ 실행 시간만큼만 과금
- ✅ 서버 관리 불필요
- ✅ CloudWatch로 모니터링

**매일 오전 9시, 오후 2시, 오후 7시**에 자동으로 영상이 생성됩니다! 🚀
