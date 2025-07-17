
import os
import tempfile
from llama_parse import LlamaParse
# from langchain.text_splitter import RecursiveCharacterTextSplitter # 이 임포트는 여기서 필요 없음
from langchain_community.vectorstores import FAISS # 이 임포트는 여기서 필요 없음
from langchain_google_genai import GoogleGenerativeAIEmbeddings # 이 임포트는 여기서 필요 없음
import streamlit as st
import asyncio

# Langchain의 Document 클래스를 명시적으로 임포트
from langchain_core.documents import Document as LangchainDocument 

# LlamaParse를 사용하기 위한 parser 객체 초기화
LLAMA_CLOUD_API_KEY = st.secrets["LLAMA_CLOUD_API_KEY"]
parser = LlamaParse(api_key=LLAMA_CLOUD_API_KEY, result_type="markdown")

def get_documents_from_files(uploaded_files):
    """
    업로드된 파일 리스트를 LlamaParse를 사용하여 문서를 로드하고 Langchain Document 객체로 변환합니다.
    """
    all_documents = []
    for uploaded_file in uploaded_files:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name
            
            # LlamaParse를 사용하여 파일 파싱
            llama_documents = asyncio.run(parser.aload_data(tmp_file_path))
            
            # LlamaIndex Document 객체를 Langchain Document 객체로 변환
            # LlamaIndex Document는 'text' 속성에 내용을, 'metadata' 속성에 메타데이터를 가집니다.
            for doc in llama_documents:
                langchain_doc = LangchainDocument(
                    page_content=doc.text, # LlamaIndex Document의 'text' 속성 사용
                    metadata={**doc.metadata, "source": uploaded_file.name} # 원본 파일 이름 추가 등 필요한 메타데이터 병합
                )
                all_documents.append(langchain_doc)
        
        finally:
            # 처리 후 임시 파일 삭제
            if os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)
            
    return all_documents