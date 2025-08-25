import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from RAG.rag_pipeline import get_retriever_from_source
from RAG.chain_builder import get_conversational_rag_chain, get_default_chain
from persona import generate_response_from_persona
from image_generator import generate_images_for_topic, generate_videos_for_topic
from elevenlabs_tts import generate_tts, TTS_ELEVENLABS_TEMPLATES, TTS_POLLY_VOICES
from generate_timed_segments import generate_subtitle_from_script, generate_ass_subtitle, SUBTITLE_TEMPLATES
from video_maker import (
    create_video_with_segments,
    create_video_from_videos,
    add_subtitles_to_video,
    create_dark_text_video
)
from deep_translator import GoogleTranslator
from file_handler import get_documents_from_files
from upload import upload_to_youtube
from best_subtitle_extractor import load_best_subtitles_documents
from text_scraper import get_links, clean_html_parallel, filter_noise
from langchain_core.documents import Document

import os
import requests
import re
import json
import nest_asyncio
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS

nest_asyncio.apply()
load_dotenv()

VIDEO_TEMPLATE = "영상(영어보이스+한국어자막·가운데)"

# ---------- 유틸 ----------
def get_web_documents_from_query(query: str):
    try:
        urls = get_links(query, num=40)
        crawl_results = clean_html_parallel(urls)
        docs = []
        for result in crawl_results:
            if result['success']:
                clean_text = filter_noise(result['text'])
                if len(clean_text.strip()) >= 100:
                    doc = Document(
                        page_content=clean_text.strip(),
                        metadata={"source": result['url']}
                    )
                    docs.append(doc)
        return docs, None
    except Exception as e:
        return [], str(e)

def patch_ass_center(ass_path: str):
    """ASS 자막의 모든 Dialogue에 {\an5}를 붙여 화면 정중앙 정렬."""
    try:
        with open(ass_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        out = []
        for ln in lines:
            if ln.startswith("Dialogue:"):
                parts = ln.split(",", 9)
                if len(parts) >= 10 and r"{\an" not in parts[9]:
                    parts[9] = r"{\an5}" + parts[9]
                    ln = ",".join(parts)
            out.append(ln)
        with open(ass_path, "w", encoding="utf-8") as f:
            f.writelines(out)
    except Exception as e:
        print(f"ASS 중앙 정렬 패치 실패: {e}")

# ---------- 앱 기본 ----------
st.set_page_config(page_title="Perfacto AI", page_icon="🤖")
st.title("PerfactoAI")
st.markdown("Make your own vids automatically")

# ---------- 세션 ----------
def _lock_title():
    st.session_state.title_locked = True

def _use_auto_title():
    st.session_state.title_locked = False
    auto = st.session_state.get("auto_video_title", "")
    if auto:
        st.session_state.video_title = auto

def _init_session():
    defaults = dict(
        messages=[],
        retriever=None,
        system_prompt="당신은 유능한 AI 어시스턴트입니다.",
        last_user_query="",
        video_topic="",
        video_title="",
        auto_video_title="",
        title_locked=False,
        edited_script_content="",
        selected_tts_provider="ElevenLabs",
        selected_tts_template="educational",
        selected_polly_voice_key="korean_female1",
        selected_subtitle_template="educational",
        bgm_path=None,
        include_voice=True,
        generated_topics=[],
        selected_generated_topic="",
        audio_path=None,
        last_rag_sources=[],
        persona_rag_flags={},
        persona_rag_retrievers={},
        upload_clicked=False,
        youtube_link="",
        video_binary_data=None,
        final_video_path=""
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
_init_session()

# ---------- 사이드바 ----------
with st.sidebar:
    st.header("⚙️ AI 페르소나 및 RAG 설정")
    if "persona_blocks" not in st.session_state:
        st.session_state.persona_blocks = []

    delete_idx = None

    if st.button("➕ 페르소나 추가"):
        st.session_state.persona_blocks.append({
            "name": "새 페르소나",
            "text": "",
            "use_prev_idx": [],
            "result": ""
        })

    for i, block in enumerate(st.session_state.persona_blocks):
        st.markdown(f"---\n### 페르소나 #{i+1} - `{block['name']}`")

        st.session_state.persona_blocks[i]["name"] = st.text_input(
            "페르소나 역할 이름", value=block["name"], key=f"name_{i}"
        )

        persona_options = [("persona", idx) for idx in range(len(st.session_state.persona_blocks)) if idx != i]
        prev_idxs = st.multiselect(
            "이전 페르소나 응답 이어받기",
            options=persona_options,
            default=block.get("use_prev_idx", []),
            key=f"use_prev_idx_{i}",
            format_func=lambda x: f"{x[1]+1} - {st.session_state.persona_blocks[x[1]]['name']}"
        )
        st.session_state.persona_blocks[i]["use_prev_idx"] = prev_idxs

        st.session_state.persona_blocks[i]["text"] = st.text_area(
            "지시 문장", value=block["text"], key=f"text_{i}"
        )

        rag_source = st.radio(
            "📡 사용할 RAG 유형:",
            options=["웹 기반 RAG", "유튜브 자막 기반 RAG"],
            index=None,
            key=f"rag_source_{i}"
        )

        youtube_channel_input = None
        if rag_source == "유튜브 자막 기반 RAG":
            youtube_channel_input = st.text_input(
                "유튜브 채널 핸들 또는 URL 입력:",
                value="@역사이야기",
                key=f"youtube_channel_input_{i}"
            )

        if st.button(f"🧠 페르소나 실행", key=f"run_{i}"):
            prev_blocks = []
            for ptype, pidx in st.session_state.persona_blocks[i].get("use_prev_idx", []):
                if ptype == "persona" and pidx != i:
                    prev_blocks.append(f"[페르소나 #{pidx+1}]\n{st.session_state.persona_blocks[pidx]['result']}")
            final_prompt = ("\n\n".join(prev_blocks) + "\n\n지시:\n" + block["text"]) if prev_blocks else block["text"]

            retriever = None
            if rag_source == "웹 기반 RAG":
                docs, error = get_web_documents_from_query(block["text"])
                if not error and docs:
                    retriever = get_retriever_from_source("docs", docs)
                    st.success(f"📄 웹 문서 {len(docs)}건 적용 완료")
                    with st.expander("🔗 적용된 웹 문서 출처 보기"):
                        for idx, doc in enumerate(docs, start=1):
                            url = doc.metadata.get("source", "출처 없음")
                            if url.startswith("http"):
                                st.markdown(f"- [문서 {idx}]({url})")
                            else:
                                st.markdown(f"- 문서 {idx}: {url}")
                else:
                    st.warning(f"웹 문서 수집 실패: {error or '문서 없음'}")
            elif rag_source == "유튜브 자막 기반 RAG":
                if youtube_channel_input and youtube_channel_input.strip():
                    subtitle_docs = load_best_subtitles_documents(youtube_channel_input.strip())
                    if subtitle_docs:
                        retriever = get_retriever_from_source("docs", subtitle_docs)
                        st.success(f"🎬 유튜브 자막 {len(subtitle_docs)}건 적용 완료")
                    else:
                        st.warning("유튜브 자막이 없습니다.")
                else:
                    st.warning("유튜브 채널을 입력해 주세요.")

            if retriever:
                st.session_state.persona_rag_flags[i] = True
                st.session_state.persona_rag_retrievers[i] = retriever
                rag_chain = get_conversational_rag_chain(retriever, st.session_state.system_prompt)
                rag_response = rag_chain.invoke({"input": final_prompt})
                content = rag_response.get("answer", rag_response.get("result", rag_response.get("content", "")))
                source_docs = rag_response.get("source_documents", [])
                sources = []
                for doc in source_docs:
                    snippet = doc.page_content.strip()
                    if len(snippet) > 300: snippet = snippet[:300] + "..."
                    sources.append({"content": snippet, "source": doc.metadata.get("source", "출처 없음")})
                st.session_state.messages.append(AIMessage(content=content, additional_kwargs={"sources": sources}))
                st.session_state.persona_blocks[i]["result"] = content
            else:
                st.session_state.persona_rag_flags[i] = False
                result_text = generate_response_from_persona(final_prompt)
                st.session_state.messages.append(AIMessage(content=result_text))
                st.session_state.persona_blocks[i]["result"] = result_text

        if st.button(f"🗑️ 페르소나 삭제", key=f"delete_{i}"):
            delete_idx = i

    if delete_idx is not None:
        del st.session_state.persona_blocks[delete_idx]
        st.rerun()

    st.markdown("---")
    with st.expander("영상 제작 설정", expanded=True):
        # 영상 스타일
        st.session_state.video_style = st.selectbox(
            "영상 스타일 선택",
            ["기본 이미지+타이틀", "감성 텍스트 영상", VIDEO_TEMPLATE],
            index=0
        )
        is_emotional = (st.session_state.video_style == "감성 텍스트 영상")
        is_video_template = (st.session_state.video_style == VIDEO_TEMPLATE)

        st.subheader("📜 사용할 스크립트 선택")
        available_personas_with_results = [
            (i, block["name"]) for i, block in enumerate(st.session_state.persona_blocks) if block.get("result", "").strip()
        ]

        if available_personas_with_results:
            selected_script_persona_idx = st.selectbox(
                "스크립트로 사용할 페르소나 선택:",
                options=available_personas_with_results,
                format_func=lambda x: f"{x[0]+1} - {x[1]}",
                key="selected_script_persona_for_video",
                index=0
            )
            selected_idx = selected_script_persona_idx[0]
            selected_script = st.session_state.persona_blocks[selected_idx]["result"]

            st.session_state.edited_script_content = st.text_area(
                "🎬 스크립트 내용 수정",
                value=selected_script,
                key="script_editor_editable"
            )

            # 제목 자동 생성은 VIDEO_TEMPLATE일 때 건너뜁니다(제목 미사용).
            if not is_video_template:
                with st.spinner("스크립트에서 영상 제목을 추출 중..."):
                    title_prompt = f"""다음 스크립트에 기반해 매력적이고 임팩트 있는 짧은 한국어 영상 제목을 생성하세요. 제목만 응답하세요.

스크립트:
{selected_script}

제목:"""
                    title_llm_chain = get_default_chain(system_prompt="당신은 숏폼 영상 제목을 짓는 전문가입니다.")
                    title = title_llm_chain.invoke({"question": title_prompt, "chat_history": []}).strip()
                    st.session_state.auto_video_title = title
                    if not st.session_state.get("title_locked", False):
                        st.session_state.video_title = title
        else:
            st.warning("사용 가능한 페르소나 결과가 없습니다. 먼저 페르소나 실행을 통해 결과를 생성해 주세요.")

        # 미디어 검색 키워드
        if not is_emotional:
            st.session_state.video_topic = st.text_input(
                "이미지/영상 검색에 사용될 키워드",
                value=st.session_state.video_topic,
                key="video_topic_input_final"
            )

        # 제목 입력칸: VIDEO_TEMPLATE에서는 숨김
        if not is_video_template:
            st.session_state.video_title = st.text_input(
                "영상 제목 (영상 위에 표시될 제목)",
                value=st.session_state.video_title,
                key="video_title_input_final",
                on_change=_lock_title
            )
        else:
            st.session_state.video_title = ""  # 사용하지 않음

        if is_emotional:
            st.info("감성 텍스트 영상은 **이미지/영상/보이스 없이** 텍스트 + (선택) BGM으로만 제작됩니다.")
            st.session_state.include_voice = False
        else:
            st.session_state.include_voice = st.checkbox("영상에 AI 목소리 포함", value=st.session_state.include_voice)
            if st.session_state.include_voice:
                st.session_state.selected_tts_provider = st.radio(
                    "음성 서비스 공급자 선택:",
                    ("ElevenLabs", "Amazon Polly"),
                    index=0 if st.session_state.selected_tts_provider == "ElevenLabs" else 1,
                    key="tts_provider_select"
                )
                if st.session_state.selected_tts_provider == "ElevenLabs":
                    elevenlabs_template_names = list(TTS_ELEVENLABS_TEMPLATES.keys())
                    st.session_state.selected_tts_template = st.selectbox(
                        "ElevenLabs 음성 템플릿 선택:",
                        options=elevenlabs_template_names,
                        index=elevenlabs_template_names.index(st.session_state.selected_tts_template)
                            if st.session_state.selected_tts_template in elevenlabs_template_names else 0,
                        key="elevenlabs_template_select"
                    )
                else:
                    polly_voice_keys = list(TTS_POLLY_VOICES.keys())
                    st.session_state.selected_polly_voice_key = st.selectbox(
                        "Amazon Polly 음성 선택:",
                        options=polly_voice_keys,
                        index=polly_voice_keys.index(st.session_state.selected_polly_voice_key)
                            if st.session_state.selected_polly_voice_key in polly_voice_keys else 0,
                        key="polly_voice_select"
                    )

        if not is_emotional:
            st.session_state.selected_subtitle_template = st.selectbox(
                "자막 템플릿 선택",
                options=list(SUBTITLE_TEMPLATES.keys()),
                index=list(SUBTITLE_TEMPLATES.keys()).index(st.session_state.selected_subtitle_template)
            )

        uploaded_bgm_file = st.file_uploader("BGM 파일 업로드 (선택 사항, .mp3, .wav)", type=["mp3", "wav"])
        if uploaded_bgm_file:
            temp_bgm_path = os.path.join("assets", uploaded_bgm_file.name)
            os.makedirs("assets", exist_ok=True)
            with open(temp_bgm_path, "wb") as f:
                f.write(uploaded_bgm_file.read())
            st.session_state.bgm_path = temp_bgm_path
            st.success(f"배경 음악 '{uploaded_bgm_file.name}' 업로드 완료!")

        st.subheader("영상 제작")
        if st.button("영상 만들기"):
            # 초기화
            st.session_state.video_binary_data = None
            st.session_state.final_video_path = ""
            st.session_state.youtube_link = ""
            st.session_state.upload_clicked = False

            final_script_for_video = st.session_state.edited_script_content
            final_topic_for_video = st.session_state.video_topic
            final_title_for_video = st.session_state.video_title  # VIDEO_TEMPLATE이면 빈 문자열이어도 됨

            if not final_script_for_video.strip():
                st.error("스크립트 내용이 비어있습니다.")
                st.stop()
            if (not is_emotional) and (not final_topic_for_video.strip()):
                st.error("영상 주제가 비어있습니다.")
                st.stop()
            # 🔎 제목 필수 체크는 VIDEO_TEMPLATE에서는 건너뜀
            if (not is_video_template) and (not final_title_for_video.strip()):
                st.error("영상 제목이 비어있습니다.")
                st.stop()

            with st.spinner("✨ 영상 제작 중입니다..."):
                try:
                    # --- 키워드 영어화 (이미지/영상 검색용) ---
                    if not is_emotional:
                        st.write("🌐 미디어 검색어를 영어로 변환 중...")
                        try:
                            image_query_english = GoogleTranslator(source='auto', target='en').translate(final_topic_for_video)
                            st.success(f"변환 완료: '{image_query_english}'")
                        except Exception as e:
                            st.warning(f"검색어 번역 실패(원문 사용): {e}")
                            image_query_english = final_topic_for_video
                        media_query_final = image_query_english
                    else:
                        media_query_final = ""

                    audio_path = None
                    segments = []
                    ass_path = None

                    # --- 음성 포함 / 미포함 분기 ---
                    if not is_emotional and st.session_state.include_voice:
                        # (중요) 이중 음성 방지:
                        #   👉 전체 TTS(단발) 생성은 하지 않고,
                        #   👉 generate_subtitle_from_script() 한 번으로 "라인별 TTS → 병합"까지 처리
                        audio_output_dir = "assets"
                        os.makedirs(audio_output_dir, exist_ok=True)
                        audio_path = os.path.join(audio_output_dir, "generated_audio.mp3")

                        # VIDEO_TEMPLATE에서는 영어 보이스를 원하므로, 스크립트를 영어로 변환해서 전달
                        tts_source_text = final_script_for_video
                        if is_video_template:
                            try:
                                tts_source_text = GoogleTranslator(source='auto', target='en').translate(final_script_for_video)
                            except Exception as e:
                                st.warning(f"영어 번역 실패(원문 보이스로 진행): {e}")
                                tts_source_text = final_script_for_video

                        st.write("🗣️ 라인별 TTS 생성/병합 및 세그먼트 산출 중...")
                        provider = "elevenlabs" if st.session_state.selected_tts_provider == "ElevenLabs" else "polly"
                        tmpl = st.session_state.selected_tts_template if provider == "elevenlabs" else st.session_state.selected_polly_voice_key

                        segments, audio_clips, ass_path = generate_subtitle_from_script(
                            script_text=tts_source_text,
                            ass_path=os.path.join("assets", "generated_subtitle.ass"),
                            full_audio_file_path=audio_path,
                            provider=provider,
                            template=tmpl,
                            subtitle_lang="ko",                 # 자막은 한국어
                            translate_only_if_english=False     # 영어든 무엇이든 ko로
                        )
                        # (리소스 정리)
                        try:
                            if audio_clips is not None:
                                audio_clips.close()
                        except:
                            pass

                        if is_video_template:
                            patch_ass_center(ass_path)
                        st.success(f"음성/자막 생성 완료: {audio_path}, {ass_path}")
                        st.session_state.audio_path = audio_path

                    else:
                        # 음성 없이 세그먼트 생성(텍스트 길이 기반)
                        st.write("🔤 음성 없이 텍스트 기반 세그먼트 생성")
                        sentences = re.split(r'(?<=[.?!])\s*', final_script_for_video.strip())
                        sentences = [s.strip() for s in sentences if s.strip()]
                        if not sentences:
                            sentences = [final_script_for_video.strip()]

                        words_per_minute = 150
                        total_script_words = len(final_script_for_video.split())
                        total_estimated_duration_seconds = max(5, (total_script_words / words_per_minute) * 60)

                        current_time = 0.0
                        total_chars = sum(len(s) for s in sentences)
                        for sentence_text in sentences:
                            min_segment_duration = 1.5
                            if total_chars > 0:
                                proportion = len(sentence_text) / total_chars
                                segment_duration = total_estimated_duration_seconds * proportion
                            else:
                                segment_duration = total_estimated_duration_seconds / len(sentences)
                            segment_duration = max(min_segment_duration, segment_duration)
                            segments.append({"start": current_time, "end": current_time + segment_duration, "text": sentence_text})
                            current_time += segment_duration
                        if segments: segments[-1]["end"] = current_time

                        if not is_emotional:
                            ass_path = os.path.join("assets", "generated_subtitle.ass")
                            st.write("📝 자막 파일 생성 중...")
                            generate_ass_subtitle(
                                segments=segments,
                                ass_path=ass_path,
                                template_name=st.session_state.selected_subtitle_template
                            )
                            if is_video_template:
                                patch_ass_center(ass_path)
                            st.success(f"자막 파일 생성 완료: {ass_path}")

                    # --- 미디어(이미지 or 영상) 수집 ---
                    image_paths, video_paths = [], []
                    if st.session_state.video_style != "감성 텍스트 영상":
                        if is_video_template:
                            st.write(f"🎞️ '{media_query_final}' 관련 영상 수집 중...")
                            video_paths = generate_videos_for_topic(media_query_final, max(3, len(segments)), orientation="portrait")
                            if not video_paths:
                                st.error("적합한 영상 클립을 찾지 못했습니다. 키워드를 바꿔보세요.")
                                st.stop()
                            st.success(f"영상 {len(video_paths)}개 확보")
                        else:
                            st.write(f"🖼️ '{media_query_final}' 관련 이미지 수집 중...")
                            image_paths = generate_images_for_topic(media_query_final, max(3, len(segments)))
                            if not image_paths:
                                st.warning("이미지 생성 실패. 기본 이미지를 사용합니다.")
                                default_image_path = "assets/default_image.jpg"
                                if not os.path.exists(default_image_path):
                                    try:
                                        generic_image_url = "https://images.pexels.com/photos/936043/pexels-photo-936043.jpeg?auto=compress&cs=tinysrgb&w=1260&h=750&dpr=2"
                                        image_data = requests.get(generic_image_url).content
                                        os.makedirs("assets", exist_ok=True)
                                        with open(default_image_path, "wb") as f:
                                            f.write(image_data)
                                    except Exception as img_dl_e:
                                        st.error(f"기본 이미지 다운로드 실패: {img_dl_e}")
                                        st.stop()
                                image_paths = [default_image_path] * max(3, len(segments))
                            st.success(f"이미지 {len(image_paths)}장 확보")

                    # --- 합성 ---
                    video_output_dir = "assets"
                    os.makedirs(video_output_dir, exist_ok=True)
                    temp_video_path = os.path.join(video_output_dir, "temp_video.mp4")
                    final_video_path = os.path.join(video_output_dir, "final_video_with_subs.mp4")

                    st.write("🎬 비디오 합성 중...")
                    if is_emotional:
                        created_video_path = create_dark_text_video(
                            script_text=final_script_for_video,
                            title_text="",                 # 감성 텍스트: 화면 제목 비사용
                            audio_path=None,
                            bgm_path=st.session_state.bgm_path,
                            save_path=temp_video_path
                        )
                        final_video_with_subs_path = created_video_path
                    else:
                        if is_video_template:
                            created_video_path = create_video_from_videos(
                                video_paths=video_paths,
                                segments=segments,
                                audio_path=st.session_state.audio_path if st.session_state.include_voice else None,
                                topic_title="",
                                include_topic_title=False,  # ✅ 상단 제목 오버레이 제거
                                bgm_path=st.session_state.bgm_path,
                                save_path=temp_video_path
                            )
                        else:
                            created_video_path = create_video_with_segments(
                                image_paths=image_paths,
                                segments=segments,
                                audio_path=st.session_state.audio_path if st.session_state.include_voice else None,
                                topic_title=st.session_state.video_title,
                                include_topic_title=True,
                                bgm_path=st.session_state.bgm_path,
                                save_path=temp_video_path
                            )

                        # 자막 오버레이
                        st.write("📝 자막 입히는 중...")
                        final_video_with_subs_path = add_subtitles_to_video(
                            input_video_path=created_video_path,
                            ass_path=ass_path,
                            output_path=final_video_path
                        )

                    st.success(f"✅ 최종 영상 생성 완료: {final_video_with_subs_path}")
                    st.session_state["final_video_path"] = final_video_with_subs_path

                except Exception as e:
                    st.error(f"❌ 영상 생성 중 오류: {e}")
                    st.exception(e)

    st.divider()
    # ---------- 다운로드 & 업로드 ----------
    with st.expander("📤 다운로드 및 업로드", expanded=True):
        final_path = st.session_state.get("final_video_path", "")
        if final_path and os.path.exists(final_path):
            st.video(final_path)
            data_for_download = st.session_state.get("video_binary_data", None)
            if data_for_download is None:
                try:
                    with open(final_path, "rb") as f:
                        data_for_download = f.read()
                    st.session_state.video_binary_data = data_for_download
                except Exception as e:
                    st.error(f"영상 파일 읽기 오류: {e}")
                    data_for_download = b""
            st.download_button(
                label="🎬 영상 다운로드",
                data=data_for_download,
                file_name="generated_multimodal_video.mp4",
                mime="video/mp4"
            )
            if not st.session_state.upload_clicked:
                if st.button("YouTube에 자동 업로드"):
                    try:
                        youtube_link = upload_to_youtube(
                            final_path,
                            title=st.session_state.get("video_title") or "AI 자동 생성 영상"  # 기본값
                        )
                        st.session_state.upload_clicked = True
                        st.session_state.youtube_link = youtube_link
                        st.success("✅ YouTube 업로드 완료!")
                        st.markdown(f"[📺 영상 보러가기]({youtube_link})")
                    except Exception as e:
                        st.error(f"❌ 업로드 실패: {e}")
            else:
                st.success("✅ YouTube 업로드 완료됨")
                st.markdown(f"[📺 영상 보러가기]({st.session_state.youtube_link})")
        else:
            st.info("📌 먼저 '영상 만들기'를 실행해 주세요.")

    if st.button("대화 초기화"):
        st.session_state.clear()
        st.rerun()

# ---------- 메인 채팅 ----------
for message in st.session_state.messages:
    with st.chat_message(message.type):
        st.markdown(message.content)
        if message.type == "ai" and hasattr(message, "additional_kwargs") and "sources" in message.additional_kwargs and message.additional_kwargs["sources"]:
            st.subheader("📚 참고 문단 (RAG 기반)")
            for idx, source_item in enumerate(message.additional_kwargs["sources"], start=1):
                content_display = source_item["content"]
                source_url_display = source_item.get("source", "N/A")
                if len(content_display) > 200:
                    content_display = content_display[:200] + "..."
                if source_url_display != 'N/A':
                    st.markdown(f"**출처 {idx}:** [{source_url_display}]({source_url_display})\n> {content_display}")
                else:
                    st.markdown(f"**출처 {idx}:**\n> {content_display}")

if user_input := st.chat_input("메시지를 입력해 주세요 (예: 최근 AI 기술 트렌드 알려줘)"):
    st.session_state.messages.append(HumanMessage(content=user_input))
    with st.chat_message("human"):
        st.markdown(user_input)
    st.session_state.last_user_query = user_input

    with st.chat_message("ai"):
        container = st.empty()
        ai_answer = ""
        sources_list = []

        if st.session_state.retriever:
            rag_chain = get_conversational_rag_chain(st.session_state.retriever, st.session_state.system_prompt)
            rag_response = rag_chain.invoke({"input": user_input})
            ai_answer = rag_response.get("answer", rag_response.get("result", rag_response.get("content", "")))
            source_docs = rag_response.get("source_documents", [])
            sources_list = []
            for doc in source_docs:
                sources_list.append({"content": doc.page_content[:200], "source": doc.metadata.get("source", "출처 없음")})
            container.markdown(ai_answer)
            st.session_state.messages.append(AIMessage(content=ai_answer, additional_kwargs={"sources": sources_list}))
        else:
            chain = get_default_chain(st.session_state.system_prompt)
            for token in chain.stream({"question": user_input, "chat_history": st.session_state.messages}):
                ai_answer += token
                container.markdown(ai_answer)

        if sources_list:
            st.write("### 📚 참고 문단 (RAG 기반)")
            for idx, source_item in enumerate(sources_list, start=1):
                content_display = source_item["content"]
                source_url_display = source_item.get("source", "N/A")
                if len(content_display) > 200:
                    content_display = content_display[:200] + "..."
                if source_url_display != 'N/A':
                    st.markdown(f"**출처 {idx}:** [{source_url_display}]({source_url_display})\n> {content_display}")
                else:
                    st.markdown(f"**출처 {idx}:**\n> {content_display}")

    # 채팅 답변을 곧바로 스크립트/주제로 반영
    st.session_state.edited_script_content = ai_answer
    with st.spinner("답변에서 영상 주제를 자동 추출 중..."):
        topic_extraction_prompt = f"""다음 스크립트에서 이미지를 생성하기 위한 2-3개의 간결한 키워드 또는 아주 짧은 구문(최대 10단어)으로 메인 주제를 추출해주세요. 키워드/구문만 응답하세요.

스크립트:
{ai_answer}

키워드/주제:"""
        topic_llm_chain = get_default_chain(system_prompt="당신은 주어진 텍스트에서 키워드를 추출하는 유용한 조수입니다.")
        extracted_topic_for_ui = topic_llm_chain.invoke({"question": topic_extraction_prompt, "chat_history": []}).strip()
        if extracted_topic_for_ui:
            st.session_state.video_topic = extracted_topic_for_ui

    # 제목 자동 추출은 VIDEO_TEMPLATE에서는 사용하지 않지만,
    # 다른 스타일에서는 편의상 유지
    if st.session_state.video_style != VIDEO_TEMPLATE:
        with st.spinner("답변에서 영상 제목을 자동 추출 중..."):
            title_extraction_prompt = f"""당신은 TikTok, YouTube Shorts, Instagram Reels용 **매력적이고 바이럴성 있는 숏폼 비디오 제목**을 작성하는 전문가입니다.
다음 스크립트에서 **최대 5단어 이내**의 강렬한 한국어 제목만 생성하세요.

스크립트:
{ai_answer}

영상 제목:"""
            title_llm_chain = get_default_chain(
                system_prompt="당신은 숏폼 비디오용 매우 짧고 강렬한 한국어 제목을 생성하는 전문 AI입니다. 항상 5단어 이내."
            )
            extracted_title_for_ui = title_llm_chain.invoke({"question": title_extraction_prompt, "chat_history": []}).strip()
            if extracted_title_for_ui:
                extracted_title_for_ui = re.sub(r'[\U00010000-\U0010ffff]', '', extracted_title_for_ui).strip()
                st.session_state.auto_video_title = extracted_title_for_ui
                if not st.session_state.get("title_locked", False):
                    st.session_state.video_title = extracted_title_for_ui
            else:
                if not st.session_state.get("video_title"):
                    st.session_state.video_title = "제목 없음"
