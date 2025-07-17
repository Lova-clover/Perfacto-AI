import os
import tempfile
from llama_parse import LlamaParse
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
import streamlit as st

# LlamaParse를 사용하기 위한 parser 객체 초기화
LLAMA_CLOUD_API_KEY = st.secrets["LLAMA_CLOUD_API_KEY"]
parser = LlamaParse(api_key=LLAMA_CLOUD_API_KEY, result_type="markdown")

def get_documents_from_files(uploaded_files):
    """
    업로드된 파일 리스트를 LlamaParse를 사용하여 문서를 로드하고 구조화합니다.
    """
    all_documents = []
    for uploaded_file in uploaded_files:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                tmp_file_path = tmp_file.name
            
            # LlamaParse를 사용하여 파일 파싱
            # LlamaParse는 비동기적으로 작동할 수 있으므로, 여기서는 간단한 동기 방식으로 호출합니다.
            # 복잡한 앱에서는 asyncio를 사용하는 것이 좋습니다.
            import asyncio
            documents = asyncio.run(parser.aload_data(tmp_file_path))
            all_documents.extend(documents)
        
        finally:
            # 처리 후 임시 파일 삭제
            if 'tmp_file_path' in locals() and os.path.exists(tmp_file_path):
                os.remove(tmp_file_path)
            
    return all_documents