# main.py (최종 클린 버전)

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from rag_pipeline import get_retriever_from_source, get_document_chain, get_default_chain
from web_ingest import full_web_ingest

# API 키 로드
load_dotenv()

# --- 앱 기본 설정 ---
st.set_page_config(page_title="Multimodal RAG Chatbot", page_icon="🤖")
st.title("🤖 멀티모달 파일/URL 분석 RAG 챗봇")
st.markdown(
    """
안녕하세요! 이 챗봇은 웹사이트 URL이나 업로드된 파일(PDF, DOCX, TXT)의 내용을 분석하고 답변합니다.
"""
)

# --- 세션 상태 초기화 ---
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "retriever" not in st.session_state:
    st.session_state.retriever = None
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = "당신은 문서 분석 전문가 AI 어시스턴트입니다. 주어진 문서의 텍스트와 테이블을 정확히 이해하고 상세하게 답변해주세요."

# --- 사이드바 UI ---
with st.sidebar:
    st.header("⚙️ 설정")
    st.divider()
    st.subheader("🤖 AI 페르소나 설정")
    prompt_input = st.text_area(
        "AI의 역할을 설정해주세요.", value=st.session_state.system_prompt, height=150
    )
    if st.button("페르소나 적용"):
        st.session_state.system_prompt = prompt_input
        st.toast("AI 페르소나가 적용되었습니다.")
    st.divider()
    st.subheader("🔎 분석 대상 설정")
    url_input = st.text_input("검색 키워드 입력", placeholder="ex) 인공지능 윤리")
    uploaded_files = st.file_uploader(
        "파일 업로드 (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True
    )
    st.info("LlamaParse는 테이블, 텍스트가 포함된 문서 분석에 최적화되어 있습니다.", icon="ℹ️")
    
    if st.button("분석 시작"):
        st.session_state.messages = []
        st.session_state.retriever = None

        source_type = None
        source_input = None

        if uploaded_files:
            source_type = "Files"
            source_input = uploaded_files

        elif url_input:
            # ✅ 키워드 기반 웹 크롤링 + 벡터화 + 저장
            with st.spinner("웹페이지를 수집하고 벡터화하는 중입니다..."):
                text_path, index_dir, error = full_web_ingest(url_input)
                if not error:
                    source_type = "FAISS"
                    source_input = index_dir  # 폴더 경로
        else:
            st.warning("검색 키워드 또는 파일을 입력해주세요.")
        if source_input:
            st.session_state.retriever = get_retriever_from_source(source_type, source_input)
            if st.session_state.retriever:
                st.success("분석이 완료되었습니다! 이제 질문해보세요.")

    st.divider()
    if st.button("대화 초기화"):
        st.session_state.clear()
        st.rerun()

for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "sources" in message and message["sources"]:
            with st.expander("참고한 출처 보기"):
                for i, source in enumerate(message["sources"]):
                    st.info(f"**출처 {i+1}**\n\n{source.page_content}")
                    st.divider()

user_input = st.chat_input("궁금한 내용을 물어보세요!")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)

    try:
        chat_history = [
            HumanMessage(content=msg["content"]) if msg["role"] == "user" 
            else AIMessage(content=msg["content"])
            for msg in st.session_state.messages[:-1]
        ]
        
        if st.session_state.retriever:
            with st.chat_message("assistant"):
                with st.spinner("관련 문서를 검색하고 답변을 생성 중입니다..."):
                    retriever = st.session_state.retriever
                    source_documents = retriever.get_relevant_documents(user_input)
                    document_chain = get_document_chain(st.session_state.system_prompt)
                    
                    ai_answer = document_chain.invoke({
                        "input": user_input,
                        "chat_history": chat_history,
                        "context": source_documents
                    })
                    
                    st.markdown(ai_answer)
                    
                    st.session_state.messages.append({
                        "role": "assistant", "content": ai_answer, "sources": source_documents
                    })
                    
                    if source_documents:
                        with st.expander("참고한 출처 보기"):
                            for i, source in enumerate(source_documents):
                                st.info(f"**출처 {i+1}**\n\n{source.page_content}")
                                st.divider()
        else:
            chain = get_default_chain(st.session_state.system_prompt)
            with st.chat_message("assistant"):
                container = st.empty()
                ai_answer = ""
                for token in chain.stream({"question": user_input, "chat_history": chat_history}):
                    ai_answer += token
                    container.markdown(ai_answer)
                st.session_state.messages.append({"role": "assistant", "content": ai_answer, "sources": []})

    except Exception as e:
        st.chat_message("assistant").error(f"죄송합니다, 답변을 생성하는 중 오류가 발생했습니다.\n\n오류: {e}")
        st.session_state.messages.pop()
