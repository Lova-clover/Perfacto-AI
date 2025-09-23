import asyncio
import spacy
from langchain_core.documents import Document as LangChainDocument
from langchain_core.runnables import RunnableLambda
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_community.retrievers import BM25Retriever
from langchain_cohere import CohereRerank
from langchain.retrievers import EnsembleRetriever

from .rag_config import RAGConfig
from .redis_cache import get_from_cache, set_to_cache, create_cache_key

# spaCy 언어 모델 로드 (앱 실행 시 한 번만 로드)
try:
    nlp_korean = spacy.load("ko_core_news_sm")
    nlp_english = spacy.load("en_core_web_sm")
    print("✅ spaCy language models loaded successfully.")
except OSError:
    print("⚠️ spaCy 모델을 찾을 수 없습니다. 'requirements.txt'에 모델이 포함되었는지 확인하세요.")
    nlp_korean, nlp_english = None, None

def _split_documents_into_sentences(documents: list[LangChainDocument]) -> list[LangChainDocument]:
    """문서 리스트를 spaCy를 이용해 문장 단위로 분할합니다."""
    sentences = []
    if not nlp_korean or not nlp_english:
        print("spaCy 모델이 로드되지 않아 문장 분할을 건너뜁니다.")
        return documents

    for doc in documents:
        if not doc.page_content or not doc.page_content.strip():
            continue

        # 먼저 한국어 모델로 시도
        nlp_doc = nlp_korean(doc.page_content)
        # 휴리스틱: 한국어 문장이 거의 없으면(알파벳 비율이 높으면) 영어 모델 재시도
        try:
            sents_list = list(nlp_doc.sents)
            if len(sents_list) <= 1 and sum(c.isalpha() and 'a' <= c.lower() <= 'z' for c in doc.page_content) / len(doc.page_content) > 0.5:
                nlp_doc = nlp_english(doc.page_content)
        except ZeroDivisionError: # 빈 page_content에 대한 예외 처리
            continue

        for sent in nlp_doc.sents:
            if sent.text.strip():
                sentences.append(LangChainDocument(page_content=sent.text.strip(), metadata=doc.metadata.copy()))
    
    return sentences


def build_retriever(documents: list[LangChainDocument]):
    """
    문서를 문장 단위로 분해하고, 하이브리드 검색(BM25 + FAISS) 및 Rerank를 수행하는
    전체 RAG 파이프라인을 구성합니다.
    """
    if not documents:
        return None

    # 1. 문서 전체를 문장으로 분할
    print("\n[1단계: 문서 전체를 문장 단위로 분할]")
    sentences = _split_documents_into_sentences(documents)
    if not sentences:
        print("분할된 문장이 없어 Retriever를 생성할 수 없습니다.")
        return None
    print(f"총 {len(sentences)}개의 문장 생성 완료.")

    # ▼▼▼ [수정] Google 임베딩을 OpenAI 임베딩으로 교체 ▼▼▼
    # 2. 임베딩 및 벡터 저장소(FAISS) 생성
    print("\n[2단계: 문장 임베딩 및 벡터 저장소 생성 (OpenAI)]")
    # 모델 이름은 필요에 따라 변경 가능 (예: "text-embedding-3-small")
    embeddings = OpenAIEmbeddings(model="text-embedding-ada-002") 
    try:
        vectorstore = FAISS.from_documents(sentences, embeddings)
        faiss_retriever = vectorstore.as_retriever(search_kwargs={"k": RAGConfig.BM25_TOP_K})
    except Exception as e:
        print(f"FAISS 인덱스 생성 실패: {e}")
        return None
    
    # 3. 키워드 기반 검색(BM25) Retriever 생성
    print("\n[3단계: 키워드 기반 BM25 Retriever 생성]")
    bm25_retriever = BM25Retriever.from_documents(sentences)
    bm25_retriever.k = RAGConfig.BM25_TOP_K

    # 4. 하이브리드 검색을 위한 EnsembleRetriever 생성
    print("\n[4단계: 하이브리드 Ensemble Retriever 구성]")
    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, faiss_retriever],
        weights=[0.5, 0.5]
    )

    # 5. Cohere Rerank 압축기 설정
    print("\n[5단계: Cohere Reranker 구성]")
    cohere_reranker = CohereRerank(model="rerank-multilingual-v3.0", top_n=RAGConfig.RERANK_1_TOP_N)

    # 6. 최종 파이프라인 체인 구성
    def get_cached_or_run_pipeline(query: str):
        cache_key = create_cache_key("final_rag_result_openai", query) # 캐시 키 변경
        
        cached_docs = get_from_cache(cache_key)
        if cached_docs is not None:
            return cached_docs

        print(f"\n[Cache Miss] 질문 '{query}'에 대한 RAG 파이프라인 실행 (OpenAI)")
        
        retrieved_docs = ensemble_retriever.invoke(query)
        print(f"하이브리드 검색 후 {len(retrieved_docs)}개 문장 선별 완료.")

        reranked_docs = cohere_reranker.compress_documents(documents=retrieved_docs, query=query)
        print(f"Cohere Rerank 후 {len(reranked_docs)}개 문장 선별 완료.")
        
        final_docs = [
            doc for doc in reranked_docs 
            if doc.metadata.get('relevance_score', 0) >= RAGConfig.RERANK_2_THRESHOLD
        ][:RAGConfig.FINAL_DOCS_COUNT]

        print(f"최종 {len(final_docs)}개 문장 선별 완료.")
                
        set_to_cache(cache_key, final_docs)
        
        return final_docs

    return RunnableLambda(get_cached_or_run_pipeline)
