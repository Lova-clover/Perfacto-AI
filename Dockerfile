# Perfacto-AI ECS Fargate용 최적화 Dockerfile
FROM python:3.11-slim

# 작업 디렉토리
WORKDIR /app

# 시스템 패키지 설치 (최소화)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    imagemagick \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 캐싱을 위한 requirements 먼저 복사
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 프로젝트 파일 복사
COPY . .

# 출력 디렉토리 생성
RUN mkdir -p output/{science,chess,history} logs assets/fonts

# 환경변수 기본값 (ECS Task Definition에서 오버라이드)
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Seoul

# 헬스체크용 스크립트
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# runner.py 실행
# ECS Task Definition에서 CMD를 오버라이드하여 job-name 지정
ENTRYPOINT ["python", "runner.py"]
CMD ["--job-config", "deployment/production_job_config.yaml", "--job-name", "weekly-science-premium"]
