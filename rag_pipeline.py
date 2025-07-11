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
    당신은 TikTok, YouTube Shorts, Instagram Reels과 같은 **매력적이고 바이럴성 있는 숏폼 비디오 스크립트**를 작성하는 전문 크리에이터입니다.
    아래 '사용자 요청 내용'을 바탕으로, **다음 원칙을 엄격히 준수하여 한국어로 스크립트를 작성해주세요.**

    **🌟 숏폼 스크립트 작성 원칙 (매우 중요!):**
    1.  **초강력 후크 (0-5초):** 시청자의 스크롤을 멈추게 할 강력한 한 문장으로 시작하세요!
        예시: "혹시 아직도 이걸 모른다고요? 🤯", "이거 하나면 끝장나요! 🔥", "일본 음식? 외국인은 이거 못 먹어요! 😱"
    2.  **간결하고 임팩트 있는 문장:** 한 문장에 하나의 핵심 아이디어만 담고, 불필요한 서술어를 최소화합니다.
    3.  **대화체 / 구어체 사용:** 친구에게 말하듯이 친근하고 활기찬 톤을 유지합니다.
    4.  **시각적 요소 강조:** 스크립트 내용이 영상으로 어떻게 표현될지 상상할 수 있도록 생동감 있게 묘사합니다.
    5.  **적절한 이모지 사용 (선택 사항이나 권장):** 텍스트 중간에 감정을 강조하는 이모지를 활용해 시각적 재미를 더합니다.
    6.  **템포 조절:** 문장과 문장 사이에 자연스러운 **간결한 휴지(pause)가 필요할 경우 반드시 '…' (말줄임표)**를 사용합니다.
    7.  **명확하고 행동을 유도하는 Call to Action (CTA):** 마지막에는 시청자에게 좋아요, 댓글, 공유, 팔로우, 또는 특정 행동을 유도하는 문장을 넣습니다.
        예시: "좋아요 누르고, 다음 꿀팁도 받아가세요! 👍", "지금 바로 시도해보세요! #꿀팁", "친구에게 이 영상을 공유하세요! 🚀"
    8.  **결과물은 스크립트 내용 자체만 포함:** 어떠한 머리말("다음은 쇼츠 스크립트입니다:"), 꼬리말, 설명도 없이 오직 스크립트 본문만 출력합니다.

    ---
    **사용자 요청 내용:**
    {user_question_content}
    ---

    **생성할 숏폼 스크립트:**
    """