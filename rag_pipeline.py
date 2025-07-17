import streamlit as st
import os
import faiss
import asyncio
from typing import Optional, List

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import SeleniumURLLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain.retrievers import BM25Retriever, EnsembleRetriever, ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CohereRerank
from langchain_core.runnables import RunnableLambda

from file_handler import get_documents_from_files
from groq import Groq
from langchain.llms.base import LLM
from pydantic import PrivateAttr

# ─────────────────────────────────────────────────────────────────────────────
# ✅ LLM 정의 (GROQ 기반)
class GROQLLM(LLM):
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    _api_key: str = PrivateAttr()
    _client: Groq = PrivateAttr()

    def __init__(self, api_key: str, model: str = "meta-llama/llama-4-scout-17b-16e-instruct", **kwargs):
        super().__init__(model=model, **kwargs)

        # ✅ 수정: Pydantic 안전 방식으로 설정
        object.__setattr__(self, "_api_key", api_key)
        object.__setattr__(self, "_client", Groq(api_key=api_key))

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.6,
            max_completion_tokens=512,
            top_p=0.95,
            stream=False,
            stop=stop,
        )
        return completion.choices[0].message.content

    @property
    def _identifying_params(self):
        return {"model": self.model}

    @property
    def _llm_type(self) -> str:
        return "groq"

# ─────────────────────────────────────────────────────────────────────────────
# ✅ 검색기 생성 함수 (BM25 + FAISS + Cohere Rerank 통합)
def get_retriever_from_source(source_type, source_input):
    documents = []

    with st.status("문서 처리 중...", expanded=True) as status:
        if source_type == "URL":
            status.update(label="URL 컨텐츠를 로드 중입니다...")
            loader = SeleniumURLLoader(urls=[source_input])
            documents = loader.load()

        elif source_type == "Files":
            status.update(label="파일을 파싱하고 있습니다...")
            documents = get_documents_from_files(source_input)

        elif source_type == "FAISS":
            embeddings = HuggingFaceEmbeddings(model_name="jhgan/ko-sbert-sts")
            if os.path.isdir(source_input):
                index_dir = source_input
            else:
                st.error(f"유효하지 않은 경로입니다: {source_input}")
                return None

            retriever = FAISS.load_local(
                index_dir,
                embeddings,
                allow_dangerous_deserialization=True
            ).as_retriever(search_kwargs={"k": 10})
            return retriever

        if not documents:
            status.update(label="문서 로딩 실패.", state="error")
            return None

        status.update(label="문서를 청크(chunk)로 분할 중입니다...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1024,
            chunk_overlap=200,
        )
        splits = text_splitter.split_documents(documents)

        status.update(label="BM25 + FAISS 인덱싱 중...")
        bm25_retriever = BM25Retriever.from_documents(splits)
        bm25_retriever.k = 10

        embeddings = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        vectorstore = FAISS.from_documents(splits, embeddings)
        faiss_retriever = vectorstore.as_retriever(search_kwargs={"k": 10})

        ensemble_retriever = EnsembleRetriever(
            retrievers=[bm25_retriever, faiss_retriever],
            weights=[0.4, 0.6]
        )

        status.update(label="Cohere Reranker 적용 중...")
        reranker = CohereRerank(model="rerank-multilingual-v3.0", top_n=5)
        compression_retriever = ContextualCompressionRetriever(
            base_retriever=ensemble_retriever,
            base_compressor=reranker
        )

        status.update(label="문서 처리 완료!", state="complete")

    return compression_retriever

# ─────────────────────────────────────────────────────────────────────────────
# ✅ RAG 체인 생성
def get_document_chain(system_prompt, retriever):
    rag_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{context}"),
        ]
    )

    groq_api_key = st.secrets["GROQ_API_KEY"]
    llm = GROQLLM(api_key=groq_api_key)

    document_chain = create_stuff_documents_chain(llm, rag_prompt)
    retrieval_chain = create_retrieval_chain(retriever, document_chain)

    # ✅ 래퍼 함수로 감싸기: 답변 + 참고 문단 함께 반환
    def rag_with_sources(inputs: dict):
        result = retrieval_chain.invoke(inputs)
        answer = result.get("answer", "")
        docs = retriever.get_relevant_documents(inputs["input"])
        source_paragraphs = [doc.page_content.strip() for doc in docs[:3]]
        return {"answer": answer, "sources": source_paragraphs}

    return rag_with_sources

# ─────────────────────────────────────────────────────────────────────────────
# ✅ 일반 체인 (RAG 아닌 단순 프롬프트용)
def get_default_chain(system_prompt):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{question}"),
        ]
    )
    groq_api_key = st.secrets["GROQ_API_KEY"]
    llm = GROQLLM(api_key=groq_api_key)
    return prompt | llm | StrOutputParser()

# ─────────────────────────────────────────────────────────────────────────────
# ✅ 주제 인사이트 생성용 LLM 응답 파서
def get_topic_insights_prompt(persona: str, domain: str, audience: str, tone: str, num_topics: int, constraints: str) -> str:
    return f"""
    당신은 {persona} 페르소나를 가진 AI 크리에이터입니다.
    '{domain}' 도메인에 대해 '{audience}' 시청자가 흥미를 느낄만한 **영상 주제를 정확히 {num_topics}개 생성**해주세요.
    전체적인 톤은 '{tone}'으로 유지하고, 다음 제약 사항을 준수해야 합니다: '{constraints}'.

    **주제 생성 규칙 (매우 중요!):**
    - 각 주제는 2~7단어 이내의 간결한 한국어 구문 또는 키워드 형태여야 합니다.
    - 각 주제는 번호나 다른 기호 없이, **하이픈(-)으로 시작해야 합니다.** (예: - 흥미로운 주제)
    - 다른 어떠한 설명, 머리말, 꼬리말, 또는 추가 문구 없이, **오직 {num_topics}개의 주제만 줄바꿈하여 나열해주세요.**

    예시 형식 ({num_topics}개):
    - 첫 번째 주제
    - 두 번째 주제
    - 세 번째 주제
    """

def generate_topic_insights(
    persona: str,
    domain: str,
    audience: str,
    tone: str,
    constraints: str,
    num_topics: int = 3
) -> List[str]:
    prompt_text = get_topic_insights_prompt(persona, domain, audience, tone, num_topics, constraints)
    groq_api_key = st.secrets["GROQ_API_KEY"]
    llm = GROQLLM(api_key=groq_api_key)

    try:
        response = llm._call(prompt_text)
        topics = []
        for line in response.split('\n'):
            if line.strip().startswith('- '):
                topic = line.strip()[2:].strip()
                if topic:
                    topics.append(topic)
        while len(topics) < num_topics:
            topics.append(f"주제 {len(topics)+1}")
        return topics[:num_topics]
    except Exception as e:
        st.error(f"주제 생성 중 오류: {e}")
        return []
