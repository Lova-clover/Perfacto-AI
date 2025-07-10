# rag_pipeline.py

import streamlit as st
import asyncio
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_community.document_loaders import SeleniumURLLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain.chains.combine_documents import create_stuff_documents_chain
from file_handler import get_documents_from_files
import faiss
from langchain.embeddings import HuggingFaceEmbeddings
import os
import requests
from langchain.llms.base import LLM
from typing import Optional, List
from groq import Groq
from pydantic import PrivateAttr 

class GROQLLM(LLM):
    # model은 기본값을 가집니다.
    model: str = "deepseek-r1-distill-llama-70b"

    # client와 마찬가지로 api_key도 내부적으로 관리되는 속성이므로 PrivateAttr로 설정합니다.
    _api_key: str = PrivateAttr() # 이 줄을 추가합니다. _api_key로 이름을 바꾸고 PrivateAttr로 선언
    _client: Groq = PrivateAttr() # 이 줄은 이미 있을 겁니다.

    def __init__(self, api_key: str, model: str = "deepseek-r1-distill-llama-70b", **kwargs):
        # 부모 클래스(LLM, Pydantic Model)의 __init__을 호출합니다.
        # model 인자는 Pydantic 유효성 검사를 위해 명시적으로 전달합니다.
        super().__init__(model=model, **kwargs)

        # PrivateAttr로 선언한 _api_key를 초기화합니다.
        self._api_key = api_key # self.api_key 대신 self._api_key를 사용합니다.

        # PrivateAttr로 선언한 _client를 초기화합니다.
        # Groq 클라이언트 생성 시 _api_key를 사용합니다.
        self._client = Groq(api_key=self._api_key) # self.api_key 대신 self._api_key를 사용합니다.

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        completion = self._client.chat.completions.create( # _client를 사용합니다.
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

            # 위험 감수하고 로드 허용 (본인이 만든 인덱스라면 OK)
            retriever = FAISS.load_local(
                index_dir,
                embeddings,
                allow_dangerous_deserialization=True
            ).as_retriever()
            return retriever

        if not documents:
            status.update(label="문서 로딩 실패.", state="error")
            return None

        status.update(label="문서를 청크(chunk)로 분할 중입니다...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""],
            is_separator_regex=False,
        )
        splits = text_splitter.split_documents(documents)

        status.update(label="임베딩 모델을 로컬에 로드 중입니다...")
        embeddings = HuggingFaceEmbeddings(model_name='jhgan/ko-sbert-sts')

        status.update(label=f"{len(splits)}개의 청크를 임베딩하고 있습니다...")
        vectorstore = FAISS.from_documents(splits, embeddings)

        retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={'k': 3, 'fetch_k': 20}
        )
        status.update(label="문서 처리 완료!", state="complete")

    return retriever

def get_document_chain(system_prompt):
    rag_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{input}"),
        ]
    )
    groq_api_key = st.secrets["GROQ_API_KEY"]  # 여기 변경
    llm = GROQLLM(api_key=groq_api_key)
    document_chain = create_stuff_documents_chain(llm, rag_prompt)
    return document_chain

def get_default_chain(system_prompt):
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("user", "{question}"),
        ]
    )
    groq_api_key = st.secrets["GROQ_API_KEY"]  # 여기 변경
    llm = GROQLLM(api_key=groq_api_key)
    return prompt | llm | StrOutputParser()