# 🚀 Perfacto-AI 완전 자동 배포 가이드

AWS EC2 또는 DigitalOcean에서 **한 번에 배포**하고 자동으로 영상을 생성하는 시스템입니다.

## ⚡ 5분 안에 완료하기

### 1️⃣ 서버 접속 & 프로젝트 클론

```bash
git clone https://github.com/Lova-clover/Perfecto-AI.git ~/perfacto-ai
cd ~/perfacto-ai
```

### 2️⃣ 원클릭 배포 실행

```bash
chmod +x deployment/*.sh
./deployment/deploy.sh
```

배포 완료! 다음이 자동으로 설치됩니다:
- Python 3.11 + 가상환경
- FFmpeg, ImageMagick
- Redis Server
- 모든 Python 패키지

### 3️⃣ API 키 설정 (필수)

```bash
nano .env
```

**필수 키 입력:**
```bash
OPENAI_API_KEY=sk-proj-...
GOOGLE_API_KEY=AIza...
AWS_ACCESS_KEY_ID=AKIA...        # Polly TTS용
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-northeast-2
```

Ctrl+X → Y → Enter로 저장

### 4️⃣ 테스트 실행

```bash
cd deployment
./run_manual.sh
```

작업 선택하면 **5-10분 후** `output/` 폴더에 영상이 생성됩니다!

### 5️⃣ 자동화 설정 (선택)

```bash
./cron_setup.sh
```

**자동 스케줄:**
- 🔬 과학: 매주 월요일 오전 9시
- ♟️ 체스: 매주 수요일 오전 9시
- 📜 역사: 매주 금요일 오전 9시

---

## 🆓 AWS 프리 티어 (t2.micro) 사용자

메모리 1GB 서버를 위한 **특별 최적화:**

```bash
./deployment/setup_aws_free_tier.sh
```

**자동 최적화:**
- 2GB 스왑 메모리 생성
- Redis 메모리 200MB 제한
- 불필요한 서비스 중지

**프리 티어용 설정 사용:**
```bash
cd deployment
./run_manual.sh
# → 4번 선택: AWS 프리 티어용
```

---

## 📋 주요 파일

| 파일 | 설명 |
|------|------|
| `deploy.sh` | 한 번에 모든 설치 |
| `run_manual.sh` | 수동 실행 (테스트용) |
| `cron_setup.sh` | 자동화 크론잡 설정 |
| `health_check.sh` | 시스템 상태 확인 |
| `setup_aws_free_tier.sh` | 프리 티어 최적화 |
| `production_job_config.yaml` | 프로덕션 작업 설정 |
| `aws_free_tier_config.yaml` | 프리 티어 전용 설정 |
| `personas_premium.yaml` | 프리미엄 5단계 페르소나 |
| `.env.example` | 환경변수 예제 |

---

## 🔍 상태 확인

```bash
./deployment/health_check.sh
```

**확인 항목:**
- 메모리/디스크 상태
- Redis 실행 여부
- Python 환경
- API 키 설정 여부
- 크론잡 등록 여부
- 최근 로그

---

## 🎯 프리미엄 페르소나 (5단계 체인)

### 과학 (premium_science)
P1 트렌드 분석 → P2 과학 검증 → P3 바이럴 스크립트 → P4 자막 최적화 → P5 썸네일 제목

### 체스 (premium_chess)
C1 트렌드 분석 → C2 전략 검증 → C3 스토리 스크립트 → C4 자막 최적화 → C5 썸네일 제목

### 역사 (premium_history)
H1 트렌드 분석 → H2 역사 검증 → H3 스토리텔링 → H4 자막 최적화 → H5 썸네일 제목

---

## 💡 문제 해결

### Redis 연결 실패
```bash
sudo systemctl restart redis-server
```

### 메모리 부족
```bash
# 스왑 확인
free -h

# 프리 티어 최적화 실행
./deployment/setup_aws_free_tier.sh
```

### 크론잡 로그 확인
```bash
tail -f ~/perfacto-ai/logs/cron.log
```

---

## 📞 지원

문제가 생기면 `health_check.sh` 결과를 확인하세요!

## 🔧 문제 해결

```bash
./health_check.sh
tail -f ~/perfacto-ai/logs/production.log
```

## 📚 상세 문서

상세한 가이드는 마크다운 파일들을 참고하세요.
