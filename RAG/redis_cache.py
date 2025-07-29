import redis
import os
import json
import hashlib
from langchain_core.documents import Document

# --- Redis 클라이언트 초기화 ---
redis_client = None
# 1. REDIS_URL 환경 변수 확인 (Upstash 등 클라우드 Redis용)
redis_url = os.getenv("REDIS_URL")

try:
    if redis_url:
        print("REDIS_URL을 사용하여 Redis에 연결합니다...")
        # Upstash의 'tcp://' 프로토콜을 'redis://'로 변경
        if redis_url.startswith("tcp://"):
            redis_url = "redis://" + redis_url[len("tcp://"):]
        
        # URL에서 직접 연결
        redis_client = redis.from_url(redis_url, decode_responses=True)
    else:
        # 2. REDIS_URL이 없으면 기존 방식으로 연결 (로컬 개발용)
        print("REDIS_HOST/PORT를 사용하여 Redis에 연결합니다...")
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            password=os.getenv("REDIS_PASSWORD", None),
            decode_responses=True
        )

    # 연결 테스트
    redis_client.ping()
    print("✅ Redis connection successful.")

except redis.exceptions.ConnectionError as e:
    print(f"⚠️ Redis connection failed: {e}. Caching will be disabled.")
    redis_client = None
except Exception as e:
    print(f"⚠️ An unexpected error occurred with Redis: {e}. Caching will be disabled.")
    redis_client = None


# 캐시 유효 시간 (초), 24시간
CACHE_TTL = 86400

def get_from_cache(key: str) -> list[Document] | None:
    """지정된 키에 해당하는 캐시된 문서 리스트를 가져옵니다."""
    if not redis_client:
        return None
    
    cached_data = redis_client.get(key)
    
    if cached_data:
        print(f"⚡️ Cache HIT for key: {key}")
        # JSON 문자열을 파싱하여 LangChain Document 객체 리스트로 복원
        docs_as_dicts = json.loads(cached_data)
        return [Document(page_content=d['page_content'], metadata=d['metadata']) for d in docs_as_dicts]
        
    print(f"🐢 Cache MISS for key: {key}")
    return None

def set_to_cache(key: str, value: list[Document]):
    """문서 리스트를 직렬화하여 Redis에 저장합니다."""
    if not redis_client:
        return

    # LangChain Document 객체 리스트를 JSON으로 직렬화 가능한 딕셔너리 리스트로 변환
    docs_as_dicts = [{'page_content': doc.page_content, 'metadata': doc.metadata} for doc in value]
    
    # JSON 문자열로 변환하여 Redis에 저장 (TTL 설정 포함)
    redis_client.setex(key, CACHE_TTL, json.dumps(docs_as_dicts))
    print(f"📦 Cached result for key: {key}")

def create_cache_key(prefix: str, content: str) -> str:
    """콘텐츠의 해시값을 기반으로 안정적인 캐시 키를 생성합니다."""
    # MD5 해시를 사용하여 일관된 길이의 키 생성
    content_hash = hashlib.md5(content.encode()).hexdigest()
    return f"{prefix}:{content_hash}"
