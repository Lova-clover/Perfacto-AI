# main.py (최종 클린 버전)

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from rag_pipeline import get_retriever_from_source, get_document_chain, get_default_chain
from web_ingest import full_web_ingest
from script_generator import generate_script # This import seems unused in the original main.py, keep for consistency if it's part of a larger plan.
from image_generator import generate_images_for_topic
from elevenlabs_tts import generate_tts, TTS_TEMPLATES
from whisper_asr import transcribe_audio_with_timestamps, generate_ass_subtitle, SUBTITLE_TEMPLATES
from video_maker import create_video_with_segments, add_subtitles_to_video
from deep_translator import GoogleTranslator # This import seems unused in the original main.py, keep for consistency if it's part of a larger plan.
import os

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
if "last_user_query" not in st.session_state:
    st.session_state.last_user_query = ""

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

# Display chat messages
for i, message in enumerate(st.session_state["messages"]):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and "sources" in message and message["sources"]:
            with st.expander("참고한 출처 보기"):
                for j, source in enumerate(message["sources"]):
                    st.info(f"**출처 {j+1}**\n\n{source.page_content}")
                    st.divider()
        # Add video generation button next to assistant's message
        if message["role"] == "assistant" and message["content"]:
            # Ensure a unique key for each button if multiple assistant messages are displayed
            if st.button("🎥 영상 만들기", key=f"generate_video_button_{i}"):
                with st.spinner("✨ 영상 제작을 시작합니다..."):
                    try:
                        ai_answer_script = message["content"]
                        
                        # --- 1. Text-to-Speech (TTS) 생성 ---
                        audio_output_dir = "assets"
                        os.makedirs(audio_output_dir, exist_ok=True)
                        audio_path = os.path.join(audio_output_dir, "generated_audio.mp3")
                        
                        # Using a Korean male voice template
                        st.write("🗣️ 음성 파일 생성 중...")
                        generate_tts(
                            text=ai_answer_script,
                            save_path=audio_path,
                            template_name="korean_male" # You can choose other templates from elevenlabs_tts.TTS_TEMPLATES
                        )
                        st.success(f"음성 파일 생성 완료: {audio_path}")

                        # --- 2. Audio Transcription (ASR) 및 Subtitle (ASS) 파일 생성 ---
                        subtitle_output_dir = "assets"
                        os.makedirs(subtitle_output_dir, exist_ok=True)
                        ass_path = os.path.join(subtitle_output_dir, "generated_subtitle.ass")

                        st.write("📝 자막 생성을 위한 음성 분석 중...")
                        segments = transcribe_audio_with_timestamps(audio_path)
                        generate_ass_subtitle(
                            segments=segments,
                            ass_path=ass_path,
                            template_name="default" # You can choose other templates from whisper_asr.SUBTITLE_TEMPLATES
                        )
                        st.success(f"자막 파일 생성 완료: {ass_path}")

                        # --- 3. 이미지 생성 ---
                        # Use the last user query as the topic for image generation
                        image_query = st.session_state.last_user_query if st.session_state.last_user_query else "abstract background"
                        num_images = max(1, len(segments)) # One image per segment, minimum 1
                        image_output_dir = "assets"
                        os.makedirs(image_output_dir, exist_ok=True)
                        
                        st.write(f"🖼️ '{image_query}' 관련 이미지 {num_images}장 생성 중...")
                        image_paths = generate_images_for_topic(image_query, num_images)
                        
                        if not image_paths:
                            st.warning("이미지 생성에 실패했습니다. 기본 이미지를 사용합니다.")
                            # Fallback if no images are generated
                            image_paths = ["assets/default_image.jpg"] # Ensure you have a default_image.jpg in assets

                        st.success(f"이미지 {len(image_paths)}장 생성 완료.")

                        # --- 4. 비디오 생성 (자막 제외) ---
                        video_output_dir = "assets"
                        os.makedirs(video_output_dir, exist_ok=True)
                        temp_video_path = os.path.join(video_output_dir, "temp_video.mp4")
                        final_video_path = os.path.join(video_output_dir, "final_video_with_subs.mp4")

                        st.write("🎬 비디오 클립 조합 및 오디오 통합 중...")
                        created_video_path = create_video_with_segments(
                            image_paths=image_paths,
                            segments=segments,
                            audio_path=audio_path,
                            topic_title=image_query, # Use image_query or a refined topic
                            include_topic_title=True,
                            bgm_path="", # Add a BGM path here if desired, e.g., "assets/bgm.mp3"
                            save_path=temp_video_path
                        )
                        st.success(f"기본 비디오 생성 완료: {created_video_path}")

                        # --- 5. 비디오에 자막 추가 ---
                        st.write("📝 비디오에 자막 추가 중...")
                        final_video_with_subs_path = add_subtitles_to_video(
                            input_video_path=created_video_path,
                            ass_path=ass_path,
                            output_path=final_video_path
                        )
                        st.success(f"✅ 최종 영상 생성 완료: {final_video_with_subs_path}")

                        # --- 6. 결과 표시 및 다운로드 링크 제공 ---
                        st.video(final_video_with_subs_path)
                        with open(final_video_with_subs_path, "rb") as file:
                            st.download_button(
                                label="영상 다운로드",
                                data=file,
                                file_name="generated_multimodal_video.mp4",
                                mime="video/mp4"
                            )
                        
                        # Clean up temporary video file (optional)
                        if os.path.exists(temp_video_path):
                            os.remove(temp_video_path)
                        # Optionally remove audio and ass files if not needed after final video is made
                        # if os.path.exists(audio_path):
                        #     os.remove(audio_path)
                        # if os.path.exists(ass_path):
                        #     os.remove(ass_path)
                        # Optionally remove generated images if no longer needed
                        # for img_path in image_paths:
                        #     if os.path.exists(img_path):
                        #         os.remove(img_path)

                    except Exception as e:
                        st.error(f"❌ 영상 생성 중 오류가 발생했습니다: {e}")
                        st.exception(e) # Display full traceback for debugging

user_input = st.chat_input("궁금한 내용을 물어보세요!")

if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.last_user_query = user_input # Store the last user query for image generation
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