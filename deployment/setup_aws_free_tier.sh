#!/bin/bash
# AWS 프리 티어 (t2.micro 1GB RAM) 최적화 스크립트

set -e

echo "🆓 AWS 프리 티어 최적화를 시작합니다..."

# 1. 스왑 메모리 생성 (2GB)
echo "💾 스왑 메모리 생성..."
if [ ! -f /swapfile ]; then
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "✅ 2GB 스왑 메모리 생성 완료"
else
    echo "✅ 스왑 메모리 이미 존재"
fi

# 2. Redis 메모리 제한 (200MB)
echo "🔧 Redis 메모리 제한 설정..."
sudo tee -a /etc/redis/redis.conf > /dev/null <<EOF

# Perfacto-AI AWS Free Tier 최적화
maxmemory 200mb
maxmemory-policy allkeys-lru
save ""
appendonly no
EOF

sudo systemctl restart redis-server
echo "✅ Redis 메모리 제한: 200MB"

# 3. 시스템 메모리 최적화
echo "⚙️ 시스템 최적화..."
sudo sysctl vm.swappiness=60
sudo sysctl vm.vfs_cache_pressure=50
echo "✅ 메모리 최적화 완료"

# 4. 불필요한 서비스 중지
echo "🛑 불필요한 서비스 중지..."
sudo systemctl disable snapd --now 2>/dev/null || true
sudo systemctl disable unattended-upgrades --now 2>/dev/null || true

echo ""
echo "✅ AWS 프리 티어 최적화 완료!"
echo ""
echo "📊 메모리 현황:"
free -h
echo ""
echo "💡 사용 권장사항:"
echo "  1. aws_free_tier_config.yaml 사용"
echo "  2. 한 번에 하나의 작업만 실행"
echo "  3. upload: false로 설정 후 수동 업로드"
echo ""
