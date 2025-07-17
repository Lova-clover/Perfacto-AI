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
import llama_index.core.schema

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
    documents = [] # 최종적으로 텍스트 스플리터에 전달될 Document 객체 리스트

    with st.status("문서 처리 중...", expanded=True) as status:
        if source_type == "URL":
            status.update(label="URL 컨텐츠를 로드 중입니다...")
            loader = SeleniumURLLoader(urls=[source_input])
            raw_documents = loader.load() # SeleniumURLLoader가 반환하는 원본 문서

            # raw_documents의 각 항목이 LangchainDocument 객체이고 page_content를 가지고 있는지 확인
            for doc in raw_documents:
                content_to_use = ""
                metadata_to_use = {}

                if isinstance(doc, llama_index.core.schema.Document):
                    # LlamaIndex Document인 경우 'text' 속성 사용
                    content_to_use = doc.text
                    metadata_to_use = doc.metadata
                    st.warning(f"경고: URL 로드된 문서가 LlamaIndex Document입니다. 'text' 속성을 사용합니다.")
                elif hasattr(doc, 'page_content'):
                    # Langchain Document인 경우 'page_content' 속성 사용
                    content_to_use = doc.page_content
                    metadata_to_use = doc.metadata
                else:
                    # 그 외의 경우, 객체 전체를 문자열로 변환
                    content_to_use = str(doc)
                    metadata_to_use = getattr(doc, 'metadata', {})
                    st.warning(f"경고: URL 로드된 문서에서 'page_content'나 'text'를 찾을 수 없습니다. 문서 객체 전체를 content로 사용합니다. 객체 타입: {type(doc)}")
                
                documents.append(LangchainDocument(page_content=content_to_use, metadata=metadata_to_use))

        elif source_type == "Files":
            status.update(label="파일을 파싱하고 있습니다...")
            raw_documents = get_documents_from_files(source_input) # LlamaParse를 통해 파싱된 원본 문서

            # raw_documents의 각 항목이 LangchainDocument 객체이고 page_content를 가지고 있는지 확인
            for doc in raw_documents:
                content_to_use = ""
                metadata_to_use = {}
                
                if isinstance(doc, llama_index.core.schema.Document):
                    # LlamaIndex Document인 경우 'text' 속성 사용
                    content_to_use = doc.text
                    metadata_to_use = doc.metadata
                    st.warning(f"경고: 파일에서 파싱된 문서가 LlamaIndex Document입니다. 'text' 속성을 사용합니다.")
                elif hasattr(doc, 'page_content'):
                    # Langchain Document인 경우 'page_content' 속성 사용
                    content_to_use = doc.page_content
                    metadata_to_use = doc.metadata
                else:
                    # 그 외의 경우, 객체 전체를 문자열로 변환
                    content_to_use = str(doc)
                    metadata_to_use = getattr(doc, 'metadata', {})
                    st.warning(f"경고: 파일에서 파싱된 문서에서 'page_content'나 'text'를 찾을 수 없습니다. 문서 객체 전체를 content로 사용합니다. 객체 타입: {type(doc)}")
                
                documents.append(LangchainDocument(page_content=content_to_use, metadata=metadata_to_use))


        elif source_type == "FAISS":
            status.update(label="FAISS 인덱스를 로드 중입니다...")
            if not os.path.exists(source_input):
                status.update(label=f"오류: FAISS 인덱스 경로를 찾을 수 없습니다: {source_input}", state="error")
                return None
            try:
                embedding = GoogleGenerativeAIEmbeddings(
                    model="models/embedding-001"
                )
                # allow_dangerous_deserialization=True는 FAISS 인덱스가 외부에서 생성되었을 때 필요할 수 있습니다.
                # 보안에 유의하여 사용하십시오.
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
        splits = text_splitter.split_documents(documents) # 이 부분에서 오류가 해결되어야 합니다.

        status.update(label="BM25 + FAISS 인덱싱 중...")
        bm25_retriever = BM25Retriever.from_documents(splits)

        embedding = GoogleGenerativeAIEmbeddings(model="models/embedding-001")
        faiss_vectorstore = FAISS.from_documents(splits, embedding)
        faiss_retriever = faiss_vectorstore.as_retriever()

        ensemble_retriever = EnsembleRetriever(
            retrievers=[bm25_retriever, faiss_retriever], weights=[0.5, 0.5]
        )

        compressor = CohereRerank()
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=compressor, base_retriever=ensemble_retriever
        )
        status.update(label="문서 처리 및 인덱싱 완료.", state="complete")
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

        # page_content와 출처 URL을 추출합니다
        source_info = []
        for doc in docs[:3]:
            content = doc.page_content.strip()
            source = doc.metadata.get('source', 'N/A') # 메타데이터에서 출처를 가져오고, 없으면 'N/A'로 기본값 설정
            source_info.append({"content": content, "source": source})

        return {"answer": answer, "sources": source_info} # 딕셔너리 리스트를 반환합니다

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
