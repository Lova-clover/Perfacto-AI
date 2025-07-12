# main.py

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from rag_pipeline import get_retriever_from_source, get_document_chain, get_default_chain, get_shorts_script_generation_prompt, generate_topic_insights
from web_ingest import full_web_ingest
from image_generator import generate_images_for_topic
from elevenlabs_tts import generate_tts, TTS_TEMPLATES
from whisper_asr import transcribe_audio_with_timestamps, generate_ass_subtitle, SUBTITLE_TEMPLATES
from video_maker import create_video_with_segments, add_subtitles_to_video
from deep_translator import GoogleTranslator
import os
import requests # 기본 이미지 다운로드를 위해 추가
import re
import json # for constraints parsing

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
    st.session_state.system_prompt = "당신은 문서 분석 전문가 AI 어시스턴트이자, 숏폼(Short-form) 영상 제작을 위한 스크립트 전문가입니다. 주어진 문서의 텍스트와 테이블을 정확히 이해하고, 짧고 간결하며 핵심 내용을 담은 쇼츠 영상 스크립트를 제작해주세요. 스크립트 외에는 어떤 답변도 해서는 안됩니다. 또한 마크다운과 같은 기호는 전부 제거해주세요."
if "last_user_query" not in st.session_state:
    st.session_state.last_user_query = ""
if "video_topic" not in st.session_state:
    st.session_state.video_topic = "" # 영상 주제 초기화
if "edited_script_content" not in st.session_state:
    st.session_state.edited_script_content = "" # 수정 가능한 스크립트 내용 초기화
if "selected_tts_template" not in st.session_state:
    st.session_state.selected_tts_template = "educational"
if "selected_subtitle_template" not in st.session_state:
    st.session_state.selected_subtitle_template = "educational"
if "bgm_path" not in st.session_state:
    st.session_state.bgm_path = None
if "include_voice" not in st.session_state:
    st.session_state.include_voice = True # 음성 포함 여부 초기화
if "generated_topics" not in st.session_state:
    st.session_state.generated_topics = []
if "selected_video_topic" not in st.session_state:
    st.session_state.selected_video_topic = ""

# --- 사이드바 UI ---
with st.sidebar:
    st.header("⚙️ 설정")
    st.divider()

    st.subheader("👨‍🏫 전문가 페르소나 설정 (주제 생성)")
    expert_persona_name = st.text_input("페르소나 이름 (예: 교육 전문가)", value="교육 전문가")
    expert_domain = st.text_input("전문 분야 (예: 최신 IT 트렌드)", value="최신 IT 트렌드")
    expert_audience = st.text_input("대상 독자 (예: 일반인, 개발자)", value="일반인")
    expert_tone = st.text_input("톤 (예: 정보성, 유익한)", value="정보성")
    expert_format = st.text_input("출력 형식 (예: 10가지 주제 목록)", value="10가지 주제 목록")
    expert_constraints_str = st.text_area("추가 조건 (JSON 형식)", value='{"길이": "최대 100자", "포함 키워드": "인공지능, 빅데이터"}')

    if st.button("주제 생성"):
        try:
            constraints_dict = json.loads(expert_constraints_str)
            topic_prompt = generate_topic_insights(
                persona=expert_persona_name,
                domain=expert_domain,
                audience=expert_audience,
                tone=expert_tone,
                format=expert_format,
                constraints=expert_constraints_str # Pass as string as per function signature
            )
            st.session_state.messages.append(HumanMessage(content=f"**[전문가 페르소나] 주제 생성 요청:**\n{topic_prompt}"))
            
            with st.spinner("주제를 생성 중입니다..."):
                topic_llm_chain = get_default_chain(system_prompt=expert_persona_name) # Use expert persona as system prompt
                generated_topics_raw = topic_llm_chain.invoke({"question": topic_prompt, "chat_history": []})
                
                # Assuming topics are separated by newlines, split and clean them
                st.session_state.generated_topics = [
                    topic.strip() for topic in generated_topics_raw.split('\n') if topic.strip()
                ]
                
                ai_answer = "다음 주제들이 생성되었습니다:\n" + "\n".join(st.session_state.generated_topics)
                st.session_state.messages.append(AIMessage(content=ai_answer))
                st.session_state.selected_video_topic = st.session_state.generated_topics[0] if st.session_state.generated_topics else ""
        except json.JSONDecodeError:
            st.error("추가 조건이 올바른 JSON 형식이 아닙니다.")
        except Exception as e:
            st.error(f"주제 생성 중 오류 발생: {e}")

    if st.session_state.generated_topics:
        st.subheader("🎬 콘텐츠 제작자 페르소나 (스크립트 생성)")
        st.session_state.selected_video_topic = st.selectbox(
            "생성된 주제 중 하나를 선택하세요:", 
            st.session_state.generated_topics,
            index=st.session_state.generated_topics.index(st.session_state.selected_video_topic) 
            if st.session_state.selected_video_topic in st.session_state.generated_topics 
            else 0
        )
        if st.button("스크립트 생성"):
            if st.session_state.selected_video_topic:
                script_generation_prompt = get_shorts_script_generation_prompt(
                    user_question_content=st.session_state.selected_video_topic,
                    script_persona="매력적이고 바이럴성 있는 숏폼 비디오 스크립트를 작성하는 전문 크리에이터"
                )
                st.session_state.messages.append(HumanMessage(content=f"**[콘텐츠 제작자 페르소나] 스크립트 생성 요청 (주제: {st.session_state.selected_video_topic}):**\n{script_generation_prompt}"))
                
                with st.spinner("스크립트를 생성 중입니다..."):
                    script_llm_chain = get_default_chain(system_prompt="당신은 숏폼 비디오 스크립트 전문가입니다.")
                    generated_script = script_llm_chain.invoke({"question": script_generation_prompt, "chat_history": []})
                    
                    st.session_state.edited_script_content = generated_script
                    st.session_state.messages.append(AIMessage(content=f"**[생성된 스크립트]**\n{generated_script}"))
            else:
                st.warning("먼저 주제를 선택해주세요.")


    st.divider()
    st.subheader("📝 문서 기반 질문 답변 (기존 RAG)")
    st.session_state.system_prompt = st.text_area(
        "AI의 역할을 설정해주세요.",
        value=st.session_state.system_prompt,
        height=150
    )

    source_type = st.radio("문서 소스 선택:", ("URL", "Files"))
    source_input = None
    if source_type == "URL":
        source_input = st.text_input("URL을 입력하세요 (예: https://www.example.com)")
    else:
        source_input = st.file_uploader("파일을 업로드하세요.", type=["pdf", "docx", "txt"], accept_multiple_files=True)

    if st.button("문서 처리 및 RAG 활성화"):
        if source_input:
            with st.spinner("문서를 처리하고 있습니다..."):
                st.session_state.retriever = get_retriever_from_source(source_type, source_input)
            st.success("문서 처리 및 RAG 활성화 완료!")
        else:
            st.warning("URL을 입력하거나 파일을 업로드해주세요.")

    st.divider()
    st.subheader("📹 비디오 생성 설정")
    st.session_state.edited_script_content = st.text_area(
        "영상 스크립트 (수정 가능):",
        value=st.session_state.edited_script_content,
        height=200
    )

    st.session_state.video_topic = st.text_input("영상 주제 (이미지 생성 키워드):", value=st.session_state.video_topic)

    tts_template_options = list(TTS_TEMPLATES.keys())
    st.session_state.selected_tts_template = st.selectbox(
        "음성 템플릿 선택:",
        tts_template_options,
        index=tts_template_options.index(st.session_state.selected_tts_template)
    )

    subtitle_template_options = list(SUBTITLE_TEMPLATES.keys())
    st.session_state.selected_subtitle_template = st.selectbox(
        "자막 템플릿 선택:",
        subtitle_template_options,
        index=subtitle_template_options.index(st.session_state.selected_subtitle_template)
    )

    st.session_state.bgm_path = st.file_uploader("배경 음악 파일 업로드 (선택 사항)", type=["mp3", "wav"])
    if st.session_state.bgm_path:
        # Save the uploaded BGM file to a temporary location
        with open(os.path.join("assets", st.session_state.bgm_path.name), "wb") as f:
            f.write(st.session_state.bgm_path.getbuffer())
        st.session_state.bgm_path = os.path.join("assets", st.session_state.bgm_path.name)
    
    st.session_state.include_voice = st.checkbox("음성 포함", value=st.session_state.include_voice)


# --- 챗 인터페이스 ---
for message in st.session_state.messages:
    if message["role"] == "user":
        with st.chat_message("user"):
            st.markdown(message["content"])
    else:
        with st.chat_message("assistant"):
            st.markdown(message["content"])

user_input = st.chat_input("질문하세요 (예: 업로드된 문서에서 '생성형 AI'에 대해 설명해줘)")

if user_input:
    st.session_state.messages.append(HumanMessage(content=user_input))
    with st.chat_message("user"):
        st.markdown(user_input)

    chat_history = st.session_state.messages
    
    # 챗봇 답변 생성 로직 (기존 RAG와 통합)
    with st.chat_message("assistant"):
        container = st.empty()
        ai_answer = ""
        
        # RAG가 활성화된 경우
        if st.session_state.retriever:
            retrieval_chain = (
                st.session_state.retriever
                | get_document_chain(st.session_state.system_prompt)
            )
            # Invoke retrieval_chain with proper input for conversation history
            final_llm_question = {"question": user_input, "chat_history": chat_history}
            
            for token in retrieval_chain.stream(final_llm_question):
                ai_answer += token
                container.markdown(ai_answer)
        else:
            # RAG가 활성화되지 않은 경우, 기본 챗봇 체인 사용 (사용자 질문을 그대로 전달)
            chain = get_default_chain(st.session_state.system_prompt)
            for token in chain.stream({"question": user_input, "chat_history": chat_history}):
                ai_answer += token
                container.markdown(ai_answer)

        st.session_state.messages.append({"role": "assistant", "content": ai_answer, "sources": []})
    
    # 챗봇이 답변을 생성한 후, 사이드바의 스크립트와 주제 필드를 자동으로 채웁니다.
    st.session_state.edited_script_content = ai_answer
    with st.spinner("답변에서 영상 주제를 자동으로 추출 중..."):
        topic_extraction_prompt = f"""다음 스크립트에서 이미지를 생성하기 위한 2-3개의 간결한 키워드 또는 아주 짧은 구문(최대 10단어)으로 메인 주제를 추출해주세요. 키워드/구문만 응답하세요.

        스크립트:
        {ai_answer}

        키워드/주제:"""
        topic_llm_chain = get_default_chain(system_prompt="당신은 주어진 텍스트에서 키워드를 추출하는 유용한 조수입니다.")
        extracted_topic_for_ui = topic_llm_chain.invoke({"question": topic_extraction_prompt, "chat_history": []}).strip()
        if extracted_topic_for_ui:
            st.session_state.video_topic = extracted_topic_for_ui


# 비디오 생성 버튼
if st.button("🚀 비디오 생성 시작"):
    if not st.session_state.edited_script_content:
        st.error("스크립트 내용이 비어 있습니다. 스크립트를 입력하거나 생성해주세요.")
    elif not st.session_state.video_topic:
        st.error("영상 주제가 비어 있습니다. 영상 주제를 입력하거나 추출해주세요.")
    else:
        st.subheader("🎥 비디오 생성 결과")

        # 1. 음성 생성
        audio_path = "assets/audio.mp3"
        if st.session_state.include_voice:
            with st.spinner("음성을 생성 중입니다..."):
                generate_tts(
                    text=st.session_state.edited_script_content,
                    save_path=audio_path,
                    template_name=st.session_state.selected_tts_template
                )
            st.success(f"음성 생성 완료: {audio_path}")
            st.audio(audio_path)
        else:
            st.info("음성 생성을 건너뛰고 배경 음악만 사용합니다.")
            audio_path = None # 음성을 포함하지 않으면 audio_path를 None으로 설정

        # 2. 이미지 생성
        image_dir = "assets/images"
        os.makedirs(image_dir, exist_ok=True)
        num_images_to_generate = 5 # 예시: 5장의 이미지 생성
        image_paths = []
        with st.spinner(f"{st.session_state.video_topic}에 대한 이미지를 생성 중입니다..."):
            generate_images_for_topic(
                query=st.session_state.video_topic,
                num_images=num_images_to_generate,
                start_index=0
            )
            # Pexels API는 파일을 직접 반환하지 않고 다운로드 경로에 저장하므로, 저장된 경로를 기반으로 리스트 생성
            image_paths = [f"assets/image_{i}.jpg" for i in range(num_images_to_generate)]
            
            # 생성된 이미지를 미리보기로 표시
            for img_path in image_paths:
                if os.path.exists(img_path):
                    st.image(img_path, caption=os.path.basename(img_path), width=150)
        st.success(f"이미지 생성 완료: {num_images_to_generate}장")

        # 3. 자막 생성 (음성이 있을 경우)
        ass_path = "assets/subtitles.ass"
        segments_for_subtitle = []
        if st.session_state.include_voice and audio_path and os.path.exists(audio_path):
            with st.spinner("오디오를 텍스트로 변환하고 자막 세그먼트를 생성 중입니다..."):
                segments_for_subtitle = transcribe_audio_with_timestamps(audio_path)
            st.success("자막 세그먼트 생성 완료!")

            with st.spinner("자막 파일 (.ass) 생성 중입니다..."):
                # transcribe_audio_with_timestamps의 결과가 dict-like object (Segment) 이므로, 딕셔너리로 변환하여 전달
                segments_as_dicts = [{"start": seg.start, "end": seg.end, "text": seg.text} for seg in segments_for_subtitle]
                generate_ass_subtitle(
                    segments=segments_as_dicts,
                    ass_path=ass_path,
                    template_name=st.session_state.selected_subtitle_template
                )
            st.success(f"자막 파일 생성 완료: {ass_path}")
        elif not st.session_state.include_voice:
            st.info("음성을 포함하지 않아 자막 생성을 건너뜀니다.")
        else:
            st.warning("음성 파일이 없어 자막을 생성할 수 없습니다.")


        # 4. 비디오 생성
        final_video_path = "assets/final_video_with_subs.mp4"
        if image_paths and (st.session_state.include_voice and segments_for_subtitle) or (not st.session_state.include_voice):
            with st.spinner("최종 비디오를 생성 중입니다..."):
                created_video_path = create_video_with_segments(
                    script_content=st.session_state.edited_script_content,
                    image_paths=image_paths,
                    audio_path=audio_path,
                    bgm_path=st.session_state.bgm_path,
                    save_path="assets/video_without_subs.mp4" # 자막 추가 전 중간 파일
                )
            st.success(f"기본 비디오 생성 완료: {created_video_path}")

            # 5. 자막이 있는 경우 비디오에 자막 추가
            if st.session_state.include_voice and os.path.exists(ass_path):
                with st.spinner("비디오에 자막을 추가 중입니다..."):
                    add_subtitles_to_video(
                        video_path="assets/video_without_subs.mp4",
                        subtitle_path=ass_path,
                        output_path=final_video_path
                    )
                st.success(f"최종 비디오 생성 완료: {final_video_path}")
            else:
                final_video_path = created_video_path # 자막이 없으면 중간 파일이 최종 파일
                st.info("자막이 없어 비디오에 자막을 추가하지 않습니다.")

            if os.path.exists(final_video_path):
                st.video(final_video_path)
            else:
                st.error("최종 비디오 파일을 찾을 수 없습니다.")
        else:
            st.error("비디오를 생성하는 데 필요한 이미지 또는 오디오/자막 정보가 부족합니다.")
