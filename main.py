import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from rag_pipeline import get_retriever_from_source, get_document_chain, get_default_chain, get_shorts_script_generation_prompt, generate_topic_insights
from web_ingest import full_web_ingest # web_ingest는 별도로 정의되어 있어야 합니다.
from image_generator import generate_images_for_topic
from elevenlabs_tts import generate_tts, TTS_TEMPLATES
from whisper_asr import transcribe_audio_with_timestamps, generate_ass_subtitle, SUBTITLE_TEMPLATES
from video_maker import create_video_with_segments, add_subtitles_to_video
from deep_translator import GoogleTranslator
import os
import requests # 기본 이미지 다운로드를 위해 추가
import re

# API 키 불러오기
load_dotenv()

# --- 앱 기본 설정 ---
st.set_page_config(page_title="멀티모달 RAG 챗봇", page_icon="🤖")
st.title("🤖 멀티모달 파일/URL 분석 RAG 챗봇")
st.markdown(
    """
안녕하세요! 이 챗봇은 웹사이트 URL이나 업로드된 파일(PDF, DOCX, TXT)의 내용을 분석하여 답변해 드립니다.
또한, 영상 스크립트 생성 및 영상 제작 기능도 제공하고 있어요.
"""
)

# --- 세션 상태 초기화 ---
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "retriever" not in st.session_state:
    st.session_state.retriever = None
if "system_prompt" not in st.session_state:
    st.session_state.system_prompt = "당신은 유능한 AI 어시스턴트입니다."
if "last_user_query" not in st.session_state:
    st.session_state.last_user_query = ""
if "video_topic" not in st.session_state:
    st.session_state.video_topic = ""
if "edited_script_content" not in st.session_state:
    st.session_state.edited_script_content = ""
if "selected_tts_template" not in st.session_state:
    st.session_state.selected_tts_template = "educational"
if "selected_subtitle_template" not in st.session_state:
    st.session_state.selected_subtitle_template = "educational"
if "bgm_path" not in st.session_state:
    st.session_state.bgm_path = None
if "include_voice" not in st.session_state:
    st.session_state.include_voice = True
if "generated_topics" not in st.session_state:
    st.session_state.generated_topics = []
if "selected_generated_topic" not in st.session_state:
    st.session_state.selected_generated_topic = ""

# --- 사이드바: AI 페르소나 설정 및 RAG 설정 ---
with st.sidebar:
    st.header("⚙️ AI 페르소나 및 RAG 설정")

    with st.expander("전문가 페르소나 설정", expanded=True):
        st.write("주제 생성을 위한 전문가 AI의 설정을 정의해 보세요.")
        expert_persona = st.text_input("페르소나 (예: 역사학자, 과학자)", value=st.session_state.get("expert_persona", "정보 제공자"))
        expert_domain = st.text_input("주제 전문 분야 (예: 조선 시대, 블랙홀, 인공지능)", value=st.session_state.get("expert_domain", "일반 지식"))
        expert_audience = st.text_input("대상 시청자 (예: 고등학생, 일반인, 전문가)", value=st.session_state.get("expert_audience", "모든 사람"))
        expert_tone = st.text_input("톤 (예: 유익함, 재미있음, 진지함)", value=st.session_state.get("expert_tone", "유익함"))
        expert_format = st.text_input("출력 형식 (예: 목록 (10개), 상세 설명)", value=st.session_state.get("expert_format", "목록 (10개)"))
        expert_constraints = st.text_area("추가 조건 (JSON 형식 권장)", value=st.session_state.get("expert_constraints", "{}"))

        if st.button("주제 생성"):
            try:
                constraints_dict = eval(expert_constraints) # 문자열을 딕셔너리로 변환
            except:
                st.error("추가 조건이 올바른 JSON(Python 딕셔너리) 형식이 아닙니다.")
                constraints_dict = {}

            with st.spinner("전문가 페르소나가 주제를 생성하고 있습니다..."):
                st.session_state.messages.append({"role": "user", "content": f"전문가 페르소나({expert_persona})로 '{expert_domain}'에 대한 '{expert_audience}' 대상의 '{expert_tone}' 톤 '{expert_format}' 형식의 주제를 생성해 줘. 추가 조건: {expert_constraints}"})
                st.session_state.generated_topics = generate_topic_insights(
                    persona=expert_persona,
                    domain=expert_domain,
                    audience=expert_audience,
                    tone=expert_tone,
                    format=expert_format,
                    constraints=expert_constraints # 문자열로 전달
                )
                if st.session_state.generated_topics:
                    topic_list_str = "\n".join([f"- {topic}" for topic in st.session_state.generated_topics])
                    st.session_state.messages.append({"role": "assistant", "content": f"다음 주제들이 생성되었습니다:\n{topic_list_str}"})
                    st.session_state.selected_generated_topic = st.session_state.generated_topics[0] if st.session_state.generated_topics else ""
                else:
                    st.session_state.messages.append({"role": "assistant", "content": "주제 생성에 실패했어요. 설정을 다시 확인해 주세요."})
            st.rerun()

    # 주제 선택 드롭다운
    if st.session_state.generated_topics:
        st.session_state.selected_generated_topic = st.selectbox(
            "생성된 주제 중 하나를 선택하세요:",
            options=st.session_state.generated_topics,
            index=st.session_state.generated_topics.index(st.session_state.selected_generated_topic) if st.session_state.selected_generated_topic in st.session_state.generated_topics else 0
        )
    
    st.markdown("---")

    with st.expander("RAG (검색 증강 생성) 설정", expanded=False):
        st.subheader("🔎 분석 대상 설정")
        url_input = st.text_input("검색 키워드 입력", placeholder="ex) 인공지능 윤리")
        uploaded_files = st.file_uploader(
            "파일 업로드 (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True
        )
        st.info("LlamaParse는 테이블, 텍스트가 포함된 문서 분석에 최적화되어 있습니다.", icon="ℹ️")
        
        if st.button("분석 시작"):
            st.session_state.messages = []
            st.session_state.retriever = None
            st.session_state.video_topic = "" # 분석 시작 시 영상 주제 초기화
            st.session_state.edited_script_content = "" # 분석 시작 시 스크립트 내용 초기화

            source_type = None
            source_input = None

            if uploaded_files:
                source_type = "Files"
                source_input = uploaded_files

            elif url_input:
                with st.spinner("웹페이지를 수집하고 벡터화하는 중입니다..."):
                    text_path, index_dir, error = full_web_ingest(url_input)
                    if not error:
                        source_type = "FAISS"
                        source_input = index_dir  # 폴더 경로
                    else:
                        st.error(f"웹페이지 수집 및 벡터화 중 오류 발생: {error}")
            else:
                st.warning("검색 키워드 또는 파일을 입력해 주세요.")

            if source_input and source_type:
                st.session_state.retriever = get_retriever_from_source(source_type, source_input)
                if st.session_state.retriever:
                    st.success("분석이 완료되었습니다! 이제 질문해 보세요.")
                else:
                    st.error("문서 처리 중 오류가 발생했습니다. 다시 시도해 주세요.")


        system_prompt_input = st.text_area(
            "AI 어시스턴트 시스템 프롬프트",
            value=st.session_state.system_prompt,
            height=100,
        )
        if system_prompt_input != st.session_state.system_prompt:
            st.session_state.system_prompt = system_prompt_input

    st.markdown("---")

    with st.expander("영상 제작 설정", expanded=True):
        st.subheader("스크립트 생성")
        if st.button("스크립트 생성", help="선택된 주제로 숏폼 영상 스크립트를 만들어 드립니다."):
            if st.session_state.selected_generated_topic:
                with st.spinner(f"'{st.session_state.selected_generated_topic}' 주제로 스크립트를 만드는 중입니다..."):
                    # 콘텐츠 제작자 페르소나로 스크립트 생성
                    script_prompt = get_shorts_script_generation_prompt(st.session_state.selected_generated_topic)
                    script_chain = get_default_chain(system_prompt="당신은 TikTok, YouTube Shorts, Instagram Reels과 같은 매력적이고 바이럴성 있는 숏폼 비디오 스크립트를 작성하는 전문 크리에이터입니다.")
                    
                    st.session_state.messages.append({"role": "user", "content": f"선택된 주제 '{st.session_state.selected_generated_topic}'에 대한 스크립트를 만들어 줘."})
                    
                    generated_script = ""
                    for token in script_chain.stream({"question": script_prompt, "chat_history": []}): # chat_history는 필요에 따라 추가
                        generated_script += token
                    
                    st.session_state.edited_script_content = generated_script.strip()
                    st.session_state.video_topic = st.session_state.selected_generated_topic # 스크립트 생성 시 주제도 업데이트
                    st.session_state.messages.append({"role": "assistant", "content": f"**다음 스크립트가 생성되었습니다:**\n\n{st.session_state.edited_script_content}"})
                st.success("스크립트 생성이 완료되었습니다!")
                st.rerun() # 스크립트가 업데이트되도록 다시 로드
            else:
                st.warning("먼저 생성된 주제를 선택해 주세요.")

        st.subheader("제작된 스크립트 미리보기 및 수정")
        st.session_state.edited_script_content = st.text_area(
            "영상 스크립트 (원하는 대로 수정 가능)",
            value=st.session_state.edited_script_content,
            height=200,
            key="script_editor"
        )
        st.session_state.video_topic = st.text_input(
            "영상 주제 (이미지 생성에 사용될 키워드)",
            value=st.session_state.video_topic,
            key="video_topic_input"
        )

        col1_tts, col2_tts = st.columns(2)
        with col1_tts:
            st.session_state.selected_tts_template = st.selectbox(
                "TTS 목소리 템플릿",
                options=list(TTS_TEMPLATES.keys()),
                index=list(TTS_TEMPLATES.keys()).index(st.session_state.selected_tts_template)
            )
        with col2_tts:
            st.session_state.include_voice = st.checkbox("AI 목소리 포함", value=st.session_state.include_voice)

        st.session_state.selected_subtitle_template = st.selectbox(
            "자막 템플릿",
            options=list(SUBTITLE_TEMPLATES.keys()),
            index=list(SUBTITLE_TEMPLATES.keys()).index(st.session_state.selected_subtitle_template)
        )
        
        uploaded_bgm = st.file_uploader("배경 음악 (MP3, WAV)", type=["mp3", "wav"])
        if uploaded_bgm:
            temp_bgm_path = os.path.join("assets", uploaded_bgm.name)
            os.makedirs("assets", exist_ok=True)
            with open(temp_bgm_path, "wb") as f:
                f.write(uploaded_bgm.getvalue())
            st.session_state.bgm_path = temp_bgm_path
            st.success(f"배경 음악 '{uploaded_bgm.name}' 업로드를 완료했어요!")

        st.subheader("영상 제작 단계")
        if st.button("스크립트 -> 오디오 변환"):
            if st.session_state.edited_script_content and st.session_state.include_voice:
                with st.spinner("오디오를 생성하고 있습니다..."):
                    audio_path = generate_tts(st.session_state.edited_script_content, template_name=st.session_state.selected_tts_template)
                    st.session_state.audio_path = audio_path
                st.success("오디오 생성이 완료되었습니다!")
                st.audio(audio_path, format="audio/mp3")
            else:
                st.warning("오디오를 생성하려면 스크립트 내용을 입력하고 'AI 목소리 포함'을 선택해야 해요.")

        if st.button("이미지 생성"):
            if st.session_state.video_topic:
                with st.spinner(f"'{st.session_state.video_topic}' 에 대한 이미지를 생성하고 있습니다..."):
                    # 필요한 이미지 수 계산 (예: 10초당 1장 또는 스크립트 길이에 비례)
                    # 여기서는 간단히 5장으로 고정하거나, 스크립트 길이에 따라 동적으로 결정 가능
                    num_images = max(1, len(st.session_state.edited_script_content.split('.')) // 2) # 문장 수의 절반 정도
                    generate_images_for_topic(st.session_state.video_topic, num_images=num_images)
                st.success("이미지 생성이 완료되었습니다! (assets/image_X.jpg)")
            else:
                st.warning("이미지를 생성하려면 영상 주제를 입력해 주세요.")

        if st.button("영상 미리보기"):
            if st.session_state.audio_path and os.path.exists("assets/image_0.jpg"): # 최소 1개 이미지 존재 확인
                with st.spinner("영상 미리보기를 생성하고 있습니다... (오디오와 이미지 동기화)"):
                    video_output_path = "assets/preview_video.mp4"
                    create_video_with_segments(
                        audio_path=st.session_state.audio_path,
                        image_dir="assets",
                        save_path=video_output_path,
                        bgm_path=st.session_state.bgm_path if st.session_state.get("bgm_path") else None
                    )
                st.success("영상 미리보기 생성이 완료되었습니다!")
                st.video(video_output_path)
            else:
                st.warning("영상을 미리 보려면 오디오와 이미지가 먼저 생성되어야 해요.")
        
        if st.button("영상 최종 생성 (자막 포함)"):
            if st.session_state.audio_path and os.path.exists("assets/image_0.jpg"):
                with st.spinner("최종 영상과 자막을 생성하고 있습니다..."):
                    final_video_path_no_subs = "assets/final_video_no_subs.mp4"
                    create_video_with_segments(
                        audio_path=st.session_state.audio_path,
                        image_dir="assets",
                        save_path=final_video_path_no_subs,
                        bgm_path=st.session_state.bgm_path if st.session_state.get("bgm_path") else None
                    )
                    
                    # 자막 생성
                    segments = transcribe_audio_with_timestamps(st.session_state.audio_path)
                    ass_path = "assets/subtitles.ass"
                    generate_ass_subtitle(segments, ass_path, template_name=st.session_state.selected_subtitle_template)

                    # 영상에 자막 추가
                    final_video_path_with_subs = "assets/final_video_with_subs.mp4"
                    add_subtitles_to_video(final_video_path_no_subs, ass_path, final_video_path_with_subs)

                st.success("최종 영상과 자막 생성이 완료되었습니다!")
                st.video(final_video_path_with_subs)
                with open(final_video_path_with_subs, "rb") as file:
                    st.download_button(
                        label="최종 영상 다운로드",
                        data=file,
                        file_name="final_video_with_subs.mp4",
                        mime="video/mp4"
                    )
            else:
                st.warning("최종 영상을 생성하려면 오디오와 이미지가 먼저 생성되어야 해요.")


# --- 메인 채팅 인터페이스 ---
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").markdown(msg["content"])
    elif msg["role"] == "assistant":
        st.chat_message("assistant").markdown(msg["content"])
        if "sources" in msg and msg["sources"]:
            with st.expander("참조 문서 확인하기"):
                for source in msg["sources"]:
                    st.markdown(f"- **출처**: [{source.metadata.get('source', 'N/A')}]({source.metadata.get('source', '#')})")
                    st.text(source.page_content)

# 사용자 입력 처리
if user_input := st.chat_input("메시지를 입력해 주세요 (예: 최근 AI 기술 트렌드 알려줘, 이 파일 요약해 줘, 이 URL 분석해 줘)"):
    st.session_state.messages.append(HumanMessage(content=user_input, role="user"))
    st.chat_message("user").markdown(user_input)
    st.session_state.last_user_query = user_input # 마지막 사용자 쿼리 저장

    with st.chat_message("assistant"):
        container = st.empty()
        ai_answer = ""
        sources_list = []
        
        # RAG 사용 여부 결정 (URL 또는 파일이 처리된 경우)
        if st.session_state.retriever:
            retrieval_chain = get_document_chain(st.session_state.system_prompt, st.session_state.retriever)
            
            # 검색 및 답변 생성
            full_response = retrieval_chain.invoke(
                {"input": user_input, "chat_history": st.session_state.messages}
            )
            ai_answer = full_response
            # TODO: 소스 추출 로직 필요 (LangChain Chain에서 직접 소스 추출 어려움, 별도 처리 필요)
            # 여기서는 임시로 빈 리스트를 사용하거나, 추후 Chain을 수정하여 소스 메타데이터를 반환하도록 해야 함
            sources_list = [] 
            
        else:
            # 일반 챗봇 모드 (RAG 비활성화)
            chain = get_default_chain(st.session_state.system_prompt)
            
            # 챗봇 스트리밍 응답
            for token in chain.stream({"question": user_input, "chat_history": st.session_state.messages}):
                ai_answer += token
                container.markdown(ai_answer)
        
        container.markdown(ai_answer)
        st.session_state.messages.append({"role": "assistant", "content": ai_answer, "sources": sources_list})

    # 챗봇이 답변을 생성한 후, 사이드바의 스크립트와 주제 필드를 자동으로 채웁니다.
    # 일반 챗봇 답변을 스크립트로 활용
    st.session_state.edited_script_content = ai_answer
    with st.spinner("답변에서 영상 주제를 자동으로 추출하고 있습니다..."):
        topic_extraction_prompt = f"""다음 스크립트에서 이미지를 생성하기 위한 2-3개의 간결한 키워드 또는 아주 짧은 구문(최대 10단어)으로 메인 주제를 추출해주세요. 키워드/구문만 응답하세요.

        스크립트:
        {ai_answer}

        키워드/주제:"""
        topic_llm_chain = get_default_chain(system_prompt="당신은 주어진 텍스트에서 키워드를 추출하는 유용한 조수입니다.")
        extracted_topic_for_ui = topic_llm_chain.invoke({"question": topic_extraction_prompt, "chat_history": []}).strip()
        if extracted_topic_for_ui:
            st.session_state.video_topic = extracted_topic_for_ui