# rag_pipeline.py (Version 1: BM25 + Cohere)
import streamlit as st
import os
import faiss
import asyncio
from typing import Optional, List

# --- 필수 임포트 ---
import streamlit as st 
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import SeleniumURLLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains import create_retrieval_chain
from langchain.retrievers import BM25Retriever, ContextualCompressionRetriever # EnsembleRetriever는 더 이상 필요하지 않음
from langchain.retrievers.document_compressors import CohereRerank
from langchain_core.runnables import RunnableLambda
from langchain_core.documents import Document as LangchainDocument
import llama_index.core.schema

from file_handler import get_documents_from_files
from groq import Groq
from langchain.llms.base import LLM
from pydantic import PrivateAttr

COHERE_API_KEY = st.secrets["COHERE_API_KEY"]

# ─────────────────────────────────────────────────────────────────────────────
# ✅ LLM 정의 (GROQ 기반)
class GROQLLM(LLM):
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    _api_key: str = PrivateAttr()
    _client: Groq = PrivateAttr()

    def __init__(self, api_key: str, model: str = "meta-llama/llama-4-scout-17b-16e-instruct", **kwargs):
        super().__init__(model=model, **kwargs)
        object.__setattr__(self, "_api_key", api_key)
        object.__setattr__(self, "_client", Groq(api_key=api_key))

    @property
    def _llm_type(self) -> str:
        return "groq_llm"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        chat_completion = self._client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=self.model,
            stop=stop,
            temperature=0.0
        )
        return chat_completion.choices[0].message.content

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model}



# ─────────────────────────────────────────────────────────────────────────────
# ✅ Retriever 정의
def get_retriever_from_source(source_type, source_input):
    documents = [] 

    with st.status("문서 처리 중...", expanded=True) as status:
        if source_type == "URL":
            status.update(label="URL 컨텐츠를 로드 중입니다...")
            loader = SeleniumURLLoader(urls=[source_input])
            raw_documents = loader.load()
            for doc in raw_documents:
                content_to_use = getattr(doc, 'page_content', str(doc))
                metadata_to_use = getattr(doc, 'metadata', {})
                documents.append(LangchainDocument(page_content=content_to_use, metadata=metadata_to_use))

        elif source_type == "Files":
            status.update(label="파일을 파싱하고 있습니다...")
            raw_documents = get_documents_from_files(source_input)
            for doc in raw_documents:
                content_to_use = getattr(doc, 'page_content', getattr(doc, 'text', str(doc)))
                metadata_to_use = getattr(doc, 'metadata', {})
                documents.append(LangchainDocument(page_content=content_to_use, metadata=metadata_to_use))

        elif source_type == "FAISS":
            status.update(label="FAISS 인덱스를 로드 중입니다...")
            if not os.path.exists(source_input):
                status.update(label=f"오류: FAISS 인덱스 경로를 찾을 수 없습니다: {source_input}", state="error")
                return None
            try:
                embedding = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
                vectorstore = FAISS.load_local(source_input, embedding, allow_dangerous_deserialization=True)
                retriever = vectorstore.as_retriever()
                status.update(label="FAISS 인덱스 로드 완료.", state="complete")
                return retriever
            except Exception as e:
                status.update(label=f"FAISS 인덱스 로드 중 오류 발생: {e}", state="error")
                return None

        if not documents:
            status.update(label="문서 로딩 실패. (내용이 없거나 파싱 오류)", state="error")
            return None

        status.update(label="문서를 청크(chunk)로 분할 중입니다...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1024,
            chunk_overlap=200,
        )
        splits = text_splitter.split_documents(documents)

        # === START: MODIFIED FOR BM25 + COHERE ===
        status.update(label="BM25 인덱싱 및 Cohere 리랭커 설정 중...")
        bm25_retriever = BM25Retriever.from_documents(splits)

        compressor = CohereRerank(model="rerank-multilingual-v3.0", cohere_api_key=COHERE_API_KEY)
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=compressor, base_retriever=bm25_retriever
        )
        status.update(label="BM25 + Cohere 리트리버 생성 완료.", state="complete")
        # === END: MODIFIED FOR BM25 + COHERE ===
        
        return compression_retriever

# ─────────────────────────────────────────────────────────────────────────────
# ✅ RAG Chain 정의
def get_document_chain(llm, prompt):
    return create_stuff_documents_chain(llm, prompt)

def get_retrieval_chain(retriever, document_chain):
    return create_retrieval_chain(retriever, document_chain)

# ─────────────────────────────────────────────────────────────────────────────
# ✅ 기본 LLM 체인 정의
def get_default_chain(system_prompt: str):
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder("chat_history"),
        ("human", "{question}"),
    ])
    llm = GROQLLM(api_key=st.secrets["GROQ_API_KEY"])
    output_parser = StrOutputParser()
    return prompt | llm | output_parser

# ─────────────────────────────────────────────────────────────────────────────
# ✅ 영상 주제 인사이트 생성 함수
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
    
    llm = GROQLLM(api_key=st.secrets["GROQ_API_KEY"])
    output_parser = StrOutputParser()
    topic_chain = ChatPromptTemplate.from_messages([
        ("system", "당신은 주어진 매개변수에 따라 영상 주제를 생성하는 전문 AI 크리에이터입니다. 지시 사항을 엄격히 준수하세요."),
        ("human", "{prompt_text}")
    ]) | llm | output_parser
    
    try:
        response_text = topic_chain.invoke({"prompt_text": prompt_text})
        topics = [line.strip().lstrip('- ').strip() for line in response_text.split('\n') if line.strip().startswith('-')]
        return topics[:num_topics]
    except Exception as e:
        st.error(f"주제 인사이트 생성 중 오류 발생: {e}")
        return []

# ─────────────────────────────────────────────────────────────────────────────
# ✅ RAG 답변 및 출처 추출 함수 (Streamlit 표시용)
def rag_with_sources(inputs: dict):
    llm = GROQLLM(api_key=st.secrets["GROQ_API_KEY"])
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "당신은 질문에 답변하고 제공된 참조 문서에서 관련 정보를 추출하는 유용한 AI 비서입니다. 제공된 참조 문서의 내용을 바탕으로 질문에 답변해주세요. 만약 제공된 문서에 질문과 관련된 충분한 정보가 없다면, '제공된 문서로는 해당 질문에 대한 충분한 정보를 찾을 수 없습니다.'라고 명확히 밝히고, **추가 문서 업로드를 요청하지 마세요.** 답변은 항상 한국어로 하세요.\n\n{context}"),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ])

    document_chain = get_document_chain(llm, prompt)
    retrieval_chain = get_retrieval_chain(st.session_state.retriever, document_chain)
    
    response = retrieval_chain.invoke(inputs)
    
    answer = response["answer"]
    
    source_info = []
    unique_sources = set()

    for doc in response["context"]:
        content = ""
        source_url = ""

        if hasattr(doc, 'page_content'):
            content = doc.page_content.strip()
            source_url = doc.metadata.get('source', 'N/A')
        else:
            content = str(doc).strip()
            source_url = 'N/A'

        if source_url != 'N/A' and source_url not in unique_sources:
            source_info.append({"content": content, "source": source_url})
            unique_sources.add(source_url)
        elif source_url == 'N/A' and content and content not in unique_sources:
            source_info.append({"content": content, "source": source_url})
            unique_sources.add(content)

    return {"answer": answer, "sources": source_info}
