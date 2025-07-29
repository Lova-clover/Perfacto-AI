class RAGConfig:
    """RAG 파이프라인의 모든 설정값을 관리하는 클래스"""
    # 3순위 (고정 권장)
    CHUNK_SIZE = 400
    BM25_K1 = 1.2
    BM25_B = 0.75

    # 2순위 (중간 영향)
    BM25_TOP_K = 50
    RERANK_1_TOP_N = 20
    FAISS_TOP_K = 15
    RERANK_2_TOP_N = 5

    # 1순위 (성능에 가장 큰 영향)
    RERANK_1_THRESHOLD = 0.5
    RERANK_2_THRESHOLD = 0.2
    FINAL_DOCS_COUNT = 5
    
    # 임베딩 배치 설정
    EMBEDDING_BATCH_SIZE = 250
