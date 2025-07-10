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

class GROQLLM(LLM):
    # 이 부분은 @dataclass에서 정의했던 변수들을 명시적으로 선언합니다.
    # 초기화는 __init__에서 이루어집니다.
    model: str
    client: Groq

    def __init__(self, api_key: str, model: str = "deepseek-r1-distill-llama-70b", **kwargs):
        """
        Groq LLM 모델을 초기화합니다.
        model과 client 인자는 LLM의 __init__에서 요구하는 것일 수 있으므로 명시적으로 받습니다.
        """
        # ★★★ 가장 중요한 부분: 부모 클래스(LLM)의 __init__ 메서드를 호출합니다. ★★★
        # LangChain의 LLM 클래스가 내부적으로 요구하는 다른 인자들이 있을 수 있으므로,
        # **kwargs를 통해 모든 추가 인자를 전달합니다.
        super().__init__(**kwargs)

        # 이제 당신의 클래스 변수들을 초기화합니다.
        self.api_key = api_key
        self.model = model
        # Groq 클라이언트는 여기서 초기화합니다.
        self.client = Groq(api_key=self.api_key)

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        messages = [{"role": "user", "content": prompt}]
        completion = self.client.chat.completions.create(
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