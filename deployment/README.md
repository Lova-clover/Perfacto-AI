# 🚀 Perfacto-AI 배포 가이드

AWS 또는 DigitalOcean Ubuntu 서버에서 자동으로 영상을 생성하고 업로드하는 시스템입니다.

## ⚡ 빠른 시작

### 1. 서버에 파일 업로드

**GitHub 방식 (권장):**
```bash
git clone https://github.com/Lova-clover/Perfecto-AI.git ~/perfacto-ai
cd ~/perfacto-ai/deployment
```

### 2. 자동 배포 실행

```bash
chmod +x deploy.sh
./deploy.sh
```

### 3. API 키 설정

```bash
nano ~/perfacto-ai/.env
```

필수 키 입력:
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `AWS_ACCESS_KEY_ID` (Polly TTS 사용 시)
- `AWS_SECRET_ACCESS_KEY`

### 4. 테스트 실행

```bash
./run_manual.sh
```

### 5. 자동화 설정

```bash
./cron_setup.sh
```

## 📋 주요 파일

- `production_job_config.yaml` - 작업 설정
- `deploy.sh` - 자동 배포 스크립트
- `.env.example` - 환경 변수 예제

## 🔧 문제 해결

```bash
./health_check.sh
tail -f ~/perfacto-ai/logs/production.log
```

## 📚 상세 문서

상세한 가이드는 마크다운 파일들을 참고하세요.
