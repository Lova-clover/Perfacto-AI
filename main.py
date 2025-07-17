import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from rag_pipeline import get_retriever_from_source, get_document_chain, get_default_chain, generate_topic_insights, GROQLLM
from web_ingest import full_web_ingest # web_ingest는 별도로 정의되어 있어야 합니다.
from image_generator import generate_images_for_topic
from elevenlabs_tts import generate_tts, TTS_ELEVENLABS_TEMPLATES, TTS_POLLY_VOICES
from generate_timed_segments import generate_subtitle_from_script, generate_ass_subtitle, SUBTITLE_TEMPLATES
from video_maker import create_video_with_segments, add_subtitles_to_video
from deep_translator import GoogleTranslator
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
import os
import requests # 기본 이미지 다운로드를 위해 추가
import re
import json # JSON 파싱을 위해 추가
import nest_asyncio

nest_asyncio.apply()

# API 키 불러오기
load_dotenv()

# --- 앱 기본 설정 ---
st.set_page_config(page_title="Perfacto AI", page_icon="🤖")
st.title("PerfactoAI")
st.markdown(
    """
Make your own vids automatically
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
if "video_title" not in st.session_state: # 새롭게 추가된 부분: 영상 제목 세션 상태
    st.session_state.video_title = ""
if "edited_script_content" not in st.session_state:
    st.session_state.edited_script_content = ""
if "selected_tts_provider" not in st.session_state: # 새로운 TTS 공급자 세션 상태
    st.session_state.selected_tts_provider = "ElevenLabs" # 기본값 설정
if "selected_tts_template" not in st.session_state:
    st.session_state.selected_tts_template = "educational" # ElevenLabs 템플릿
if "selected_polly_voice_key" not in st.session_state: # Amazon Polly 음성 세션 상태
    st.session_state.selected_polly_voice_key = "korean_female" # 기본값 설정
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
if "audio_path" not in st.session_state: 
    st.session_state.audio_path = None
if "expert_persona" not in st.session_state:
    st.session_state.expert_persona = "" 
if "expert_domain" not in st.session_state:
    st.session_state.expert_domain = ""
if "expert_audience" not in st.session_state:
    st.session_state.expert_audience = ""
if "expert_tone" not in st.session_state:
    st.session_state.expert_tone = ""
if "expert_output_count" not in st.session_state: # 'format' 대신 'output_count'
    st.session_state.expert_output_count = 3 # 기본값 설정
if "expert_constraints" not in st.session_state:
    st.session_state.expert_constraints = "{}"


# --- 사이드바: AI 페르소나 설정 및 RAG 설정 ---
with st.sidebar:
    st.header("⚙️ AI 페르소나 및 RAG 설정")

    with st.expander("전문가 페르소나 설정", expanded=True):
        st.write("주제 생성을 위한 전문가 AI의 설정을 정의해 보세요.")
        expert_persona = st.text_input("페르소나", 
                                       value=st.session_state.expert_persona, 
                                       placeholder="예: 역사학자, 과학자", 
                                       key="expert_persona_input")
        expert_domain = st.text_input("주제 전문 분야", 
                                       value=st.session_state.expert_domain, 
                                       placeholder="예: 조선 시대, 블랙홀, 인공지능", 
                                       key="expert_domain_input")
        expert_audience = st.text_input("대상 시청자", 
                                         value=st.session_state.expert_audience, 
                                         placeholder="예: 고등학생, 일반인, 전문가", 
                                         key="expert_audience_input")
        expert_tone = st.text_input("톤", 
                                     value=st.session_state.expert_tone, 
                                     placeholder="예: 유익함, 재미있음, 진지함", 
                                     key="expert_tone_input")
        expert_output_count = st.number_input("출력 개수", # '출력 형식' 대신 '출력 개수'
                                              min_value=1, max_value=10, 
                                              value=st.session_state.expert_output_count, 
                                              key="expert_output_count_input")
        expert_constraints = st.text_area("추가 조건 (JSON 형식 권장)", 
                                           value=st.session_state.expert_constraints, 
                                           placeholder="예: {\"length\": \"short\", \"keywords\": [\"파이썬\", \"데이터\"]}", 
                                           key="expert_constraints_input")

        if st.button("주제 생성"):
            if not expert_persona.strip():
                st.warning("페르소나를 입력해 주세요.")
                st.stop()
            if not expert_domain.strip():
                st.warning("주제 전문 분야를 입력해 주세요.")
                st.stop()
            if not expert_audience.strip():
                st.warning("대상 시청자를 입력해 주세요.")
                st.stop()
            if not expert_tone.strip():
                st.warning("톤을 입력해 주세요.")
                st.stop()
            constraints_dict = {}
            if expert_constraints.strip(): # 추가 조건이 비어있지 않을 때만 파싱 시도
                try:
                    constraints_dict = json.loads(expert_constraints) # json.loads 사용 권장
                except json.JSONDecodeError:
                    st.error("추가 조건이 올바른 JSON 형식이 아닙니다.")
                    st.stop() # 오류 시 스크립트 중단

            with st.spinner("전문가 페르소나가 주제를 생성하고 있습니다..."):
                st.session_state.messages.append({"role": "user", "content": f"전문가 페르소나({expert_persona})로 '{expert_domain}'에 대한 '{expert_audience}' 대상의 '{expert_tone}' 톤으로 {expert_output_count}개의 주제를 생성해 줘. 추가 조건: {expert_constraints}"})
                st.session_state.generated_topics = generate_topic_insights(
                    persona=expert_persona,
                    domain=expert_domain,
                    audience=expert_audience,
                    tone=expert_tone,
                    num_topics=expert_output_count, # 출력 개수 전달
                    constraints=expert_constraints # 문자열로 전달 (generate_topic_insights 내부에서 처리)
                )
                if st.session_state.generated_topics:
                    topic_list_str = "\n".join([f"- {topic}" for topic in st.session_state.generated_topics])
                    st.session_state.messages.append({"role": "assistant", "content": f"다음 주제들이 생성되었습니다:\n{topic_list_str}"})
                    st.session_state.selected_generated_topic = st.session_state.generated_topics[0] if st.session_state.generated_topics else ""
                else:
                    st.session_state.messages.append({"role": "assistant", "content": "주제 생성에 실패했어요. 설정을 다시 확인해 주세요."})
            st.rerun()
    
    st.markdown("---")

    with st.expander("RAG (검색 증강 생성) 설정", expanded=True):
        st.subheader("🔎 분석 대상 설정")
        url_input = st.text_input("검색 키워드 입력", placeholder="ex) 인공지능 윤리")
        uploaded_files = st.file_uploader(
            "파일 업로드 (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True
        )
        
        if st.button("분석 시작"):
            st.session_state.retriever = None

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
                        source_input = index_dir   # 폴더 경로
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

    st.markdown("---")

    with st.expander("스크립트 생성", expanded=True): # 새로운 "스크립트 생성" expander
        st.subheader("스크립트 생성 및 설정")

        # 주제 선택 드롭다운 (새 expander로 이동)
        if st.session_state.generated_topics:
            st.session_state.selected_generated_topic = st.selectbox(
                "생성된 주제 중 하나를 선택하세요:",
                options=st.session_state.generated_topics,
                index=st.session_state.generated_topics.index(st.session_state.selected_generated_topic) if st.session_state.selected_generated_topic in st.session_state.generated_topics else 0,
                key="script_topic_select"
            )
        
        # 페르소나, 대상 시청자, 추가 조건 복사 (원래 위치에도 유지)
        script_expert_persona = st.text_input("페르소나", 
                                               value=st.session_state.expert_persona, 
                                               placeholder="예: 역사학자, 과학자", 
                                               key="script_expert_persona_input")
        script_expert_audience = st.text_input("대상 시청자", 
                                                value=st.session_state.expert_audience, 
                                                placeholder="예: 고등학생, 일반인, 전문가", 
                                                key="script_expert_audience_input")
        script_expert_tone = st.text_input("톤", 
                                     value=st.session_state.expert_tone, 
                                     placeholder="예: 유익함, 재미있음, 진지함", 
                                     key="script_tone_input") 
        script_expert_constraints = st.text_area("추가 조건 (JSON 형식 권장)", 
                                                 value=st.session_state.expert_constraints, 
                                                 placeholder="예: {\"length\": \"short\", \"keywords\": [\"파이썬\", \"데이터\"]}", 
                                                 key="script_expert_constraints_input")


        if st.button("스크립트 생성", help="선택된 주제로 숏폼 영상 스크립트를 만들어 드립니다.", key="generate_script_button"):
            if st.session_state.selected_generated_topic:
                with st.spinner(f"'{st.session_state.selected_generated_topic}' 주제로 스크립트를 만드는 중입니다..."):
                    # 콘텐츠 제작자 페르소나로 스크립트 생성
                    # 스크립트 생성 프롬프트에 페르소나, 대상 시청자, 추가 조건 반영
                    script_prompt_content = f"주어진 주제: '{st.session_state.selected_generated_topic}'. 이 주제에 대해 다음 조건을 사용하여 숏폼 비디오 스크립트를 작성해 주세요. 페르소나: {script_expert_persona}, 대상 시청자: {script_expert_audience}, 톤 : {script_expert_tone}, 추가 조건: {script_expert_constraints}"
                    script_chain = get_default_chain(
                    system_prompt="""당신은 TikTok, YouTube Shorts, Instagram Reels 등에서 **즉시 시선을 사로잡고 끝까지 시청하게 만드는 바이럴성 숏폼 비디오 스크립트**를 작성하는 전문 크리에이터입니다.

                    **핵심 원칙:**
                    1.  **강력한 오프닝 훅:** 첫 문장부터 시청자의 스크롤을 멈추게 할 질문, 충격적인 사실, 또는 궁금증 유발하는 문구로 시작하세요.
                    2.  **초고속 전개:** 각 문장은 독립적인 하나의 아이디어 또는 짧은 구문으로 구성하고, 불필요한 서론이나 수식어는 제거하여 빠른 템포를 유지합니다. **한 줄에 한 문장/구만 배치하여 다음 장면으로의 빠른 전환을 유도하세요.**
                    3.  **명확한 메시지:** 각 세그먼트(문장)는 마침표(.), 물음표(?), 느낌표(!)로 깔끔하게 끝나야 합니다.
                    4.  **정보 밀도 & 재미:** 유익한 정보, 놀라운 사실, 혹은 재미있는 관점을 간결하게 전달하여 시청자에게 '아하!'하는 순간을 선사합니다.
                    5.  **이모지 사용 금지.**
                    6.  **마지막에 강력한 마무리:** 시청자가 공유, 좋아요, 팔로우하고 싶게 만드는 여운을 남기거나, 간단한 다음 행동을 유도할 수 있습니다.

                    **출력 형식 (매우 중요!):**
                    - 다른 어떠한 설명, 머리말, 꼬리말, 예시, 또는 추가 문구 없이, **오직 스크립트 대사 내용만 줄바꿈하여 나열해주세요.**
                    - 스크립트 대사 시작 전에 "스크립트", "대사"와 같은 머리말도 붙이지 마세요.
                    - 예시 스타일에서 제시된 것과 같이, 오직 대사 내용만 각 줄에 배치합니다.

                    위 원칙에 따라 매력적이고 바이럴성 있는 숏폼 비디오 스크립트를 작성해주세요.
                    """
                    )           
                    st.session_state.messages.append({"role": "user", "content": f"선택된 주제 '{st.session_state.selected_generated_topic}'에 대한 스크립트를 만들어 줘."})
                    
                    generated_script = ""
                    for token in script_chain.stream({"question": script_prompt_content, "chat_history": []}): # chat_history는 필요에 따라 추가
                        generated_script += token
                    
                    st.session_state.edited_script_content = generated_script.strip()
                    with st.spinner("생성된 스크립트에서 영상 주제를 자동으로 추출하고 있습니다..."):
                        topic_extraction_prompt = f"""다음 스크립트에서 이미지를 생성하기 위한 2-3개의 간결한 키워드 또는 아주 짧은 구문(최대 10단어)으로 메인 주제를 추출해주세요. 키워드/구문만 응답하세요.

                        스크립트:
                        {generated_script.strip()} 

                        키워드/주제:"""
                        topic_llm_chain = get_default_chain(system_prompt="당신은 주어진 텍스트에서 키워드를 추출하는 유용한 조수입니다.")
                        extracted_topic_for_ui = topic_llm_chain.invoke({"question": topic_extraction_prompt, "chat_history": []}).strip()
                        if extracted_topic_for_ui:
                            st.session_state.video_topic = extracted_topic_for_ui
                        else: # 추출에 실패한 경우 기존 선택 주제 유지 또는 기본값 설정
                            st.session_state.video_topic = st.session_state.selected_generated_topic
                    
                    # 새롭게 추가된 부분: 스크립트에서 영상 제목 자동 추출
                    with st.spinner("생성된 스크립트에서 영상 제목을 자동으로 추출하고 있습니다..."):
                        title_extraction_prompt = f"""다음 스크립트에서 영상의 제목으로 사용할 수 있는 5~10단어 이내의 간결하고 매력적인 한국어 제목을 추출해주세요. 제목만 응답하세요.

                        스크립트:
                        {generated_script.strip()}

                        영상 제목:"""
                        title_llm_chain = get_default_chain(
                        system_prompt="""당신은 TikTok, YouTube Shorts, Instagram Reels과 같은 **매력적이고 바이럴성 있는 숏폼 비디오 제목**을 작성하는 전문 크리에이터입니다.
                        다음 스크립트에서 시청자의 스크롤을 멈추게 할 수 있는, **최대 5단어 이내의 간결하고 임팩트 있는 한국어 제목**을 생성해주세요.
                        이 제목은 호기심을 유발하고, 핵심 내용을 빠르게 전달하며, 클릭을 유도하는 강력한 후크 역할을 해야 합니다.
                        **예시: '체스 초고수 꿀팁!', '이거 알면 체스 끝!', '체스 천재되는 법?'**
                        **제목만 응답하세요.**
                        """
                        )
                        extracted_title_for_ui = title_llm_chain.invoke({"question": title_extraction_prompt, "chat_history": []}).strip()
                        if extracted_title_for_ui:
                            st.session_state.video_title = extracted_title_for_ui
                        else:
                            st.session_state.video_title = "제목 없음" # 추출 실패 시 기본값

                    st.session_state.messages.append({"role": "assistant", "content": f"**다음 스크립트가 생성되었습니다:**\n\n{st.session_state.edited_script_content}"})
                st.success("스크립트 생성이 완료되었습니다!")
                st.rerun() # 스크립트가 업데이트되도록 다시 로드
            else:
                st.warning("먼저 생성된 주제를 선택해 주세요.")

        st.subheader("제작된 스크립트 미리보기 및 수정")
        # 스크립트 내용 (수정 가능) 텍스트 영역
        st.session_state.edited_script_content = st.text_area(
            "영상 스크립트 (원하는 대로 수정 가능):",
            value=st.session_state.edited_script_content, # 세션 상태에서 가져옴
            height=200,
            key="script_editor_final" # Changed key to avoid conflict if any
        )
    
    st.markdown("---") # 스크립트 생성 expander와 영상 제작 설정 expander 사이에 구분선 추가

    with st.expander("영상 제작 설정", expanded=True): # 원래 있던 "영상 제작 설정" expander
        # 영상 주제 입력 필드 이름 변경 (Moved here)
        st.session_state.video_topic = st.text_input(
            "이미지 생성에 사용될 키워드", # 필드 이름 변경
            value=st.session_state.video_topic, # 세션 상태에서 가져옴
            key="video_topic_input_final" # Changed key to avoid conflict if any
        )

        # 새롭게 추가된 부분: 영상 제목 입력 필드
        st.session_state.video_title = st.text_input(
            "영상 제목 (영상 위에 표시될 제목)", # 필드 이름
            value=st.session_state.video_title, # 세션 상태에서 가져옴
            key="video_title_input_final" # 새로운 키
        )

        # 음성 포함 여부 선택
        st.session_state.include_voice = st.checkbox("영상에 AI 목소리 포함", value=st.session_state.include_voice)

        if st.session_state.include_voice:
            # TTS 서비스 공급자 선택 라디오 버튼 추가
            st.session_state.selected_tts_provider = st.radio(
                "음성 서비스 공급자 선택:",
                ("ElevenLabs", "Amazon Polly"),
                index=0 if st.session_state.selected_tts_provider == "ElevenLabs" else 1,
                key="tts_provider_select"
            )

            if st.session_state.selected_tts_provider == "ElevenLabs":
                # ElevenLabs 템플릿 선택
                elevenlabs_template_names = list(TTS_ELEVENLABS_TEMPLATES.keys())
                st.session_state.selected_tts_template = st.selectbox(
                    "ElevenLabs 음성 템플릿 선택:",
                    options=elevenlabs_template_names,
                    index=elevenlabs_template_names.index(st.session_state.selected_tts_template) if st.session_state.selected_tts_template in elevenlabs_template_names else 0,
                    key="elevenlabs_template_select"
                )
                # ElevenLabs는 voice_id를 따로 받을 수도 있지만, 여기서는 템플릿으로만 통일하여 간결하게 합니다.
                # 만약 특정 Voice ID를 직접 입력받고 싶다면 추가적인 text_input을 구성할 수 있습니다.

            elif st.session_state.selected_tts_provider == "Amazon Polly":
                # Amazon Polly 음성 선택
                polly_voice_keys = list(TTS_POLLY_VOICES.keys())
                st.session_state.selected_polly_voice_key = st.selectbox(
                    "Amazon Polly 음성 선택:",
                    options=polly_voice_keys,
                    index=polly_voice_keys.index(st.session_state.selected_polly_voice_key) if st.session_state.selected_polly_voice_key in polly_voice_keys else 0,
                    key="polly_voice_select"
                )

        # 자막 템플릿 선택
        st.session_state.selected_subtitle_template = st.selectbox(
            "자막 템플릿 선택",
            options=list(SUBTITLE_TEMPLATES.keys()),
            index=list(SUBTITLE_TEMPLATES.keys()).index(st.session_state.selected_subtitle_template)
        )

        # BGM 파일 업로드 (선택 사항)
        uploaded_bgm_file = st.file_uploader("BGM 파일 업로드 (선택 사항, .mp3, .wav)", type=["mp3", "wav"])
        if uploaded_bgm_file:
            temp_bgm_path = os.path.join("assets", uploaded_bgm_file.name) # Use original filename
            os.makedirs("assets", exist_ok=True)
            with open(temp_bgm_path, "wb") as f:
                f.write(uploaded_bgm_file.read())
            st.session_state.bgm_path = temp_bgm_path
            st.success(f"배경 음악 '{uploaded_bgm_file.name}' 업로드를 완료했어요!")
        else:
            # If no file is uploaded, and there was a previous BGM, keep it unless explicitly cleared.
            pass # Keep existing bgm_path if no new file is uploaded

        st.subheader("영상 제작")
        if st.button("영상 만들기"):
            # 사용자가 수정한 스크립트 내용과 주제를 사용
            final_script_for_video = st.session_state.edited_script_content
            final_topic_for_video = st.session_state.video_topic
            final_title_for_video = st.session_state.video_title # 새롭게 추가된 부분: 최종 영상 제목

            if not final_script_for_video.strip():
                st.error("스크립트 내용이 비어있습니다. 스크립트를 입력하거나 생성해주세요.")
                st.stop()
            if not final_topic_for_video.strip():
                st.error("영상 주제가 비어있습니다. 주제를 입력해주세요.")
                st.stop()
            if not final_title_for_video.strip(): # 새롭게 추가된 부분: 영상 제목 유효성 검사
                st.error("영상 제목이 비어있습니다. 제목을 입력하거나 생성해주세요.")
                st.stop()

            with st.spinner("✨ 영상 제작 중입니다..."):
                try:
                    # --- 0-1. 추출된 토픽을 영어로 번역 (GoogleTranslator 사용) ---
                    st.write("🌐 이미지 검색어를 영어로 번역 중...")
                    image_query_english = ""
                    try:
                        translator = GoogleTranslator(source='ko', target='en')
                        image_query_english = translator.translate(final_topic_for_video)
                        st.success(f"이미지 검색어 번역 완료 (영어): '{image_query_english}'")
                    except Exception as e:
                        st.warning(f"이미지 검색어 번역에 실패했습니다. 한국어 검색어를 그대로 사용합니다. 오류: {e}")
                        image_query_english = final_topic_for_video
                    image_query_final = image_query_english 

                    audio_path = None
                    segments = []

                    if st.session_state.include_voice:
                        # --- 1. Text-to-Speech (TTS) 생성 ---
                        audio_output_dir = "assets"
                        os.makedirs(audio_output_dir, exist_ok=True)
                        audio_path = os.path.join(audio_output_dir, "generated_audio.mp3")
                        
                        st.write("🗣️ 음성 파일 생성 중...")
                        
                        if st.session_state.selected_tts_provider == "ElevenLabs":
                            generated_audio_path = generate_tts(
                                text=final_script_for_video,
                                save_path=audio_path,
                                provider="elevenlabs", # 공급자 명시
                                template_name=st.session_state.selected_tts_template # ElevenLabs 템플릿
                            )
                        elif st.session_state.selected_tts_provider == "Amazon Polly":
                            generated_audio_path = generate_tts(
                                text=final_script_for_video,
                                save_path=audio_path,
                                provider="polly", # 공급자 명시
                                polly_voice_name_key=st.session_state.selected_polly_voice_key # Polly 음성 키
                            )

                        st.success(f"음성 파일 생성 완료: {generated_audio_path}")
                        st.session_state.audio_path = generated_audio_path # Store audio path in session state

                        # --- 2. Audio Transcription (ASR) 및 Subtitle (ASS) 파일 생성 ---
                        subtitle_output_dir = "assets"
                        os.makedirs(subtitle_output_dir, exist_ok=True)
                        ass_path = os.path.join(subtitle_output_dir, "generated_subtitle.ass")
                        
                        audio_save_path = "assets/generated_audio.mp3"
                        full_audio_path = generate_tts(
                        text=final_script_for_video,
                        save_path=audio_save_path,
                        provider="elevenlabs" if st.session_state.selected_tts_provider == "ElevenLabs" else "polly",
                        template_name=st.session_state.selected_tts_template if st.session_state.selected_tts_provider == "ElevenLabs"
                                else st.session_state.selected_polly_voice_key
                    )

                        st.write("📝 자막 생성을 위한 음성 분석 중...")
                        segments, audio_clips, ass_path = generate_subtitle_from_script(
                        script_text=final_script_for_video,
                        ass_path=ass_path,
                        full_audio_file_path=full_audio_path, 
                        provider="elevenlabs" if st.session_state.selected_tts_provider == "ElevenLabs" else "polly",
                        template=st.session_state.selected_tts_template if st.session_state.selected_tts_provider == "ElevenLabs"
                                else st.session_state.selected_polly_voice_key
                    )
                        st.success(f"자막 파일 생성 완료: {ass_path}")
                    else: # 음성이 없는 경우
                        st.write("음성 없이 자막과 이미지만으로 영상을 생성합니다.")

                        # 스크립트를 문장 단위로 분할
                        sentences = re.split(r'(?<=[.?!])\s*', final_script_for_video.strip())
                        sentences = [s.strip() for s in sentences if s.strip()]

                        if not sentences:
                            sentences = [final_script_for_video.strip()] # 전체 스크립트를 하나의 문장으로

                        words_per_minute = 150 # 분당 단어 수 (평균적인 읽기 속도)
                        total_script_words = len(final_script_for_video.split())
                        total_estimated_duration_seconds = (total_script_words / words_per_minute) * 60

                        if total_estimated_duration_seconds < 5: # 너무 짧은 영상 방지 (최소 5초)
                            total_estimated_duration_seconds = 5

                        current_time = 0.0 # 현재 시간 (누적)
                        segments = [] # 최종 segments 리스트

                        # total_chars 계산 (이전 코드에서 누락되어 있던 부분)
                        total_chars = sum(len(s) for s in sentences)

                        for sentence_text in sentences:
                            min_segment_duration = 1.5 # 초

                            if total_chars > 0: # 0으로 나누는 오류 방지
                                proportion = len(sentence_text) / total_chars
                                segment_duration = total_estimated_duration_seconds * proportion
                            else: # 스크립트가 비어있거나 특수한 경우 (이 경우는 거의 없겠지만 안전장치)
                                segment_duration = total_estimated_duration_seconds / len(sentences)

                            segment_duration = max(min_segment_duration, segment_duration)

                            segments.append({
                                "start": current_time,
                                "end": current_time + segment_duration,
                                "text": sentence_text
                            })
                            current_time += segment_duration

                        if segments:
                            segments[-1]["end"] = current_time 

                        subtitle_output_dir = "assets"
                        os.makedirs(subtitle_output_dir, exist_ok=True)
                        ass_path = os.path.join(subtitle_output_dir, "generated_subtitle.ass")

                        st.write("📝 자막 파일 생성 중...")
                        generate_ass_subtitle(
                            segments=segments,
                            ass_path=ass_path,
                            template_name=st.session_state.selected_subtitle_template
                        )
                        st.success(f"자막 파일 생성 완료: {ass_path}")

                    # --- 3. 이미지 생성 ---
                    num_images = max(3, len(segments)) if segments else 3 # 최소 3장 또는 세그먼트 수만큼
                    image_output_dir = "assets"
                    os.makedirs(image_output_dir, exist_ok=True)
                    
                    st.write(f"🖼️ '{image_query_final}' 관련 이미지 {num_images}장 생성 중...")
                    image_paths = generate_images_for_topic(image_query_final, num_images)
                    
                    if not image_paths:
                        st.warning("이미지 생성에 실패했습니다. 기본 이미지를 사용합니다.")
                        default_image_path = "assets/default_image.jpg"
                        if not os.path.exists(default_image_path):
                            try:
                                print("Downloading a placeholder image as default_image.jpg is not found.")
                                generic_image_url = "https://images.pexels.com/photos/936043/pexels-photo-936043.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2" # Example URL
                                image_data = requests.get(generic_image_url).content
                                with open(default_image_path, "wb") as f:
                                    f.write(image_data)
                                print(f"✅ Placeholder image saved to: {default_image_path}")
                            except Exception as img_dl_e:
                                st.error(f"기본 이미지 다운로드에도 실패했습니다. 오류: {img_dl_e}")
                                st.stop()
                        image_paths = [default_image_path] * num_images # Ensure enough default images
                        
                    st.success(f"이미지 {len(image_paths)}장 생성 완료.")

                    # --- 4. 비디오 생성 (자막 제외) ---
                    video_output_dir = "assets"
                    os.makedirs(video_output_dir, exist_ok=True)
                    temp_video_path = os.path.join(video_output_dir, "temp_video.mp4")
                    final_video_path = os.path.join(video_output_dir, "final_video_with_subs.mp4")

                    st.write("🎬 비디오 클립 조합 및 오디오 통합 중...")
                    created_video_path = create_video_with_segments(
                        image_paths=image_paths,
                        segments=segments, # segments를 사용하여 이미지 지속 시간 결정
                        audio_path=audio_path if st.session_state.include_voice else None, # 음성 미포함 시 None 전달
                        topic_title=final_title_for_video, # 새롭게 수정된 부분: 영상 제목을 전달
                        include_topic_title=True,
                        bgm_path=st.session_state.bgm_path,
                        save_path=temp_video_path,
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

                except Exception as e:
                    st.error(f"❌ 영상 생성 중 오류가 발생했습니다: {e}")
                    st.exception(e)

    st.divider()
    if st.button("대화 초기화"):
        st.session_state.clear()
        st.rerun()


# --- 메인 채팅 인터페이스 ---
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.chat_message("user").markdown(msg["content"])
    elif msg["role"] == "assistant":
        st.chat_message("assistant").markdown(msg["content"])
        if "sources" in msg and msg["sources"]:
            with st.expander("참조 문서 확인하기"):
                for source in msg["sources"]:
                    st.markdown(f"- **출처**: [{source['metadata'].get('source', 'N/A')}]({source['metadata'].get('source', '#')})")
                    st.text(source['page_content'])
# 사용자 입력 처리
if user_input := st.chat_input("메시지를 입력해 주세요 (예: 최근 AI 기술 트렌드 알려줘)"):
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.chat_message("user").markdown(user_input)
    st.session_state.last_user_query = user_input

    if st.session_state.retriever:
        with st.spinner("정보를 검색하고 답변을 생성 중입니다..."):
            # rag_system_prompt에서 {context}를 제거하고, 순수한 시스템 지침으로 만듭니다.
            rag_system_prompt = """당신은 주어진 문서를 참고하여 질문에 답변하는 유능한 AI 어시스턴트입니다.
            주어진 정보로 답변할 수 없다면, '주어진 정보로는 답변할 수 없습니다.'라고 말하세요.
            답변은 항상 한국어로 하세요.
            """

            llm = GROQLLM(api_key=st.secrets["GROQ_API_KEY"])

            rag_prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", rag_system_prompt),
                    MessagesPlaceholder(variable_name="chat_history"),
                    # 사용자 메시지 템플릿에 {context} 변수를 명시적으로 포함시킵니다.
                    # {context}에 검색된 문서 내용이, {input}에 사용자의 질문이 들어갑니다.
                    ("user", "다음 문서를 참고하여 질문에 답변하세요:\n\n{context}\n\n질문: {input}"),
                ]
            )

            document_chain = get_document_chain(llm, rag_prompt)

            retrieval_chain = get_retrieval_chain(st.session_state.retriever, document_chain)

            rag_chat_history = [
                HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"])
                for msg in st.session_state.messages[:-1]
            ]

            response = retrieval_chain.invoke({"input": user_input, "chat_history": rag_chat_history})

            ai_answer = response["answer"]
            retrieved_sources = response["context"]

            formatted_sources = []
            for doc in retrieved_sources:
                formatted_sources.append({
                    "metadata": {"source": doc.metadata.get('source', '알 수 없음')},
                    "page_content": doc.page_content
                })

            st.session_state.messages.append({"role": "assistant", "content": ai_answer, "sources": formatted_sources})
            st.chat_message("assistant").markdown(ai_answer)
            if formatted_sources:
                with st.expander("참조 문서 확인하기"):
                    for source in formatted_sources:
                        st.markdown(f"- **출처**: [{source['metadata'].get('source', 'N/A')}]({source['metadata'].get('source', '#')})")
                        st.text(source['page_content'])

    else:
        with st.spinner("답변 생성 중..."):
            general_chat_chain = get_default_chain(st.session_state.system_prompt)

            general_chat_history = [
                HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"])
                for msg in st.session_state.messages[:-1]
            ]

            ai_answer = ""
            for token in general_chat_chain.stream({"question": user_input, "chat_history": general_chat_history}):
                ai_answer += token

            st.session_state.messages.append({"role": "assistant", "content": ai_answer})
            st.chat_message("assistant").markdown(ai_answer)
    st.rerun()

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

    # 새롭게 추가된 부분: 챗봇 답변에서 영상 제목 자동 추출
    with st.spinner("답변에서 영상 제목을 자동으로 추출하고 있습니다..."):
        title_extraction_prompt = f"""당신은 TikTok, YouTube Shorts, Instagram Reels과 같은 **매력적이고 바이럴성 있는 숏폼 비디오 제목**을 작성하는 전문 크리에이터입니다.
다음 스크립트에서 시청자의 스크롤을 멈추게 할 수 있는, **최대 5단어 이내의 간결하고 임팩트 있는 한국어 제목**을 생성해주세요.
이 제목은 호기심을 유발하고, 핵심 내용을 빠르게 전달하며, 클릭을 유도하는 강력한 후크 역할을 해야 합니다.
**예시: '체스 초고수 꿀팁!', '이거 알면 체스 끝!', '체스 천재되는 법?'**
**제목만 응답하세요.**

        스크립트:
        {ai_answer}

        영상 제목:"""
        title_llm_chain = get_default_chain(
    system_prompt="당신은 숏폼(Shorts) 비디오를 위한 매우 짧고 강렬한 한국어 제목을 생성하는 전문 AI입니다. 항상 5단어 이내로, 시청자의 호기심을 극대화하는 제목을 만드세요."
)
        extracted_title_for_ui = title_llm_chain.invoke({"question": title_extraction_prompt, "chat_history": []}).strip()
        if extracted_title_for_ui:
            st.session_state.video_title = extracted_title_for_ui
        else:
            st.session_state.video_title = "제목 없음" # 추출 실패 시 기본값
