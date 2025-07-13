# Python 3.13 기반의 Streamlit 권장 이미지 사용
FROM python:3.13-slim-bullseye

# 필요한 시스템 라이브러리 설치
RUN apt-get update && apt-get install -y \
    ffmpeg \
    python3-dev \
    # 필요한 다른 apt 패키지 추가 (packages.txt에 있던 것들)
    libnss3 \
    libxss1 \
    libasound2 \
    libxrandr2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm-dev \
    libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# requirements.txt 복사 및 파이썬 종속성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# Streamlit 앱 실행
EXPOSE 8501
ENTRYPOINT ["streamlit", "run", "main.py", "--server.port=8501", "--server.enableCORS=false", "--server.enableXsrfProtection=false"]