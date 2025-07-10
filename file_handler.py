# file_handler.py (PyMuPDFLoader 적용 버전)

import os
import tempfile
import streamlit as st
# [수정] PyPDFLoader 대신 PyMuPDFLoader를 import
from langchain_community.document_loaders import PyMuPDFLoader, Docx2txtLoader, TextLoader

def get_documents_from_files(uploaded_files):
    """
    업로드된 파일들을 확장자에 맞는 기본 로더를 사용하여 처리합니다.
    """
    all_documents = []
    
    # [수정] 파일 처리 스피너를 main.py로 옮겨 일관성을 유지합니다.
    for uploaded_file in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_file_path = tmp_file.name

        loader = None
        try:
            if uploaded_file.name.endswith(".pdf"):
                # [수정] PDF 로더를 PyMuPDFLoader로 교체합니다.
                loader = PyMuPDFLoader(tmp_file_path)
            elif uploaded_file.name.endswith(".docx"):
                loader = Docx2txtLoader(tmp_file_path)
            elif uploaded_file.name.endswith(".txt"):
                loader = TextLoader(tmp_file_path, encoding='utf-8')
            
            if loader:
                # [수정] load_and_split() 대신 load()를 사용하여 분할은 다음 단계에서 처리하도록 합니다.
                all_documents.extend(loader.load())

        except Exception as e:
            st.error(f"'{uploaded_file.name}' 파일 처리 중 오류 발생: {e}")
        finally:
            os.remove(tmp_file_path)

    return all_documents
