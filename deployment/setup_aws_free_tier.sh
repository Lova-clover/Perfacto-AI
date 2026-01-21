#!/bin/bash
# AWS 프리 티어 (t2.micro) 최적화 스크립트

echo "🆓 AWS 프리 티어 최적화 시작..."

# 1. 스왑 메모리 생성 (2GB)
echo "💾 스왑 메모리 생성 (2GB)..."
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# /etc/fstab에 추가 (재부팅 후에도 유지)
if ! grep -q "/swapfile" /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

# 2. Redis 메모리 제한 설정
echo "🔧 Redis 메모리 제한 설정..."
sudo sed -i 's/^# maxmemory .*/maxmemory 256mb/' /etc/redis/redis.conf
sudo sed -i 's/^# maxmemory-policy .*/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
sudo systemctl restart redis-server

# 3. 시스템 캐시 정리
echo "🧹 시스템 캐시 정리..."
sudo sync
sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'

echo ""
echo "✅ 프리 티어 최적화 완료!"
echo ""
echo "메모리 상태:"
free -h
echo ""
