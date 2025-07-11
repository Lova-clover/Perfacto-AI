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
    model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    
    _api_key: str = PrivateAttr() 
    _client: Groq = PrivateAttr() 

    def __init__(self, api_key: str, model: str = "meta-llama/llama-4-scout-17b-16e-instruct", **kwargs):
        super().__init__(model=model, **kwargs)
        
        self._api_key = api_key 
        self._client = Groq(api_key=self._api_key) 

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
            chunk_size=700,
            chunk_overlap=150,
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
            search_kwargs={'k': 2, 'fetch_k': 10}
        )
        status.update(label="문서 처리 완료!", state="complete")

    return retriever

def get_document_chain(system_prompt):
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
    return document_chain

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

def get_shorts_script_generation_prompt(user_question_content):
    """
    숏폼 비디오 스크립트 생성을 위한 프롬프트 템플릿을 반환합니다.
    사용자의 질문 내용을 포함하여 LLM이 특정 형식으로 응답하도록 지시합니다.
    """
    return f"""
    당신은 TikTok, YouTube Shorts, Instagram Reels과 같은 숏폼 비디오 스크립트를 작성하는 전문 어시스턴트입니다.
    아래의 '사용자 요청 내용'을 바탕으로, **한국어**로 숏폼 비디오 스크립트를 작성해주세요.

    **작성 원칙:**
    - 매우 간결하고 임팩트 있는 문장을 사용하세요. 각 문장은 하나의 핵심 아이디어에 집중합니다.
    - 시청자의 주의를 즉시 사로잡는 **후크 문장**으로 시작합니다.
    - 문장과 문장 사이에 자연스러운 간결한 휴지(pause)가 필요할 경우 **'…' (말줄임표)**를 사용합니다.
    - 불필요한 설명은 최소화하고, 핵심 메시지를 명확하게 전달합니다.
    - 마지막에는 시청자의 **행동을 유도하는 명확한 Call to Action (CTA)**을 포함합니다 (예: '좋아요 누르고, 다음 게임은 다르게 둬보세요!', '지금 바로 시도해보세요!', '친구에게 공유하세요!').
    - 전체적으로 **에너지 넘치고 몰입감 있는 톤**을 유지합니다.
    - 응답은 스크립트 내용 자체만 포함해야 하며, 어떠한 추가 설명이나 머리말, 꼬리말도 포함하지 마세요.

    **사용자 요청 내용:**
    {user_question_content}
    """