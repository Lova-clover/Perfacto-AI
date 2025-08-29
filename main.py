import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, AIMessage
from RAG.rag_pipeline import get_retriever_from_source
from RAG.chain_builder import get_conversational_rag_chain, get_default_chain
from persona import generate_response_from_persona
from image_generator import generate_images_for_topic, generate_videos_for_topic
from elevenlabs_tts import TTS_ELEVENLABS_TEMPLATES, TTS_POLLY_VOICES
from generate_timed_segments import generate_subtitle_from_script, generate_ass_subtitle, SUBTITLE_TEMPLATES, _auto_split_for_tempo, auto_densify_for_subs, _strip_last_punct_preserve_closers, dedupe_adjacent_texts, harden_ko_sentence_boundaries, _build_dense_from_ssml
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
import math 
from moviepy import AudioFileClip
nest_asyncio.apply()
load_dotenv()

VIDEO_TEMPLATE = "영상(영어보이스+한국어자막·가운데)"


# ---------- 유틸 ----------
def ensure_min_frames(events, fps=30.0, min_frames=2):
    if not events: return events
    tick = 1.0 / float(fps)
    min_dur = tick * max(1, int(min_frames))
    out = []
    for i, e in enumerate(events):
        s = float(e["start"]); ed = float(e["end"])
        if ed - s < min_dur:
            ed = s + min_dur
            if i + 1 < len(events):
                ed = min(ed, float(events[i+1]["start"]) - 0.001)  # 살짝 여유
        out.append({**e, "start": round(s,3), "end": round(ed,3)})
    return out

def drop_or_fix_empty_text(events, merge_if_overlap_or_gap=0.06):
    if not events: return events
    NBSP = "\u00A0"; ASS_NL = r"\N"
    out = []
    for e in events:
        txt = (e.get("text") or "").strip()
        vis = txt.replace(NBSP, "").replace(ASS_NL, "").strip()
        if not vis:
            # 완전 빈 텍스트만 제거
            continue
        if out and out[-1]["text"] == txt:
            prev_end = float(out[-1]["end"]); cur_start = float(e["start"])
            gap = max(0.0, cur_start - prev_end)
            # 겹치거나 gap이 아주 짧을 때만 병합
            if gap <= merge_if_overlap_or_gap:
                out[-1]["end"] = max(out[-1]["end"], e["end"])
            else:
                out.append(e)
        else:
            out.append(e)
    return out

def sanitize_ass_text(s: str) -> str:
    """ASS에서 문제될 수 있는 중괄호를 이스케이프(우리는 override 태그를 텍스트에 넣지 않음)."""
    s = (s or "")
    s = s.replace("\\{", "\\{").replace("\\}", "\\}")  # idempotent
    s = s.replace("{", r"\{").replace("}", r"\}")
    return s

def prepare_text_for_ass(text: str, one_line_threshold=12, biline_target=14) -> str:
    t = bind_compounds(text)                 # 결합 표현 보호
    t = _protect_short_tail_nbsp(t)          # 말꼬리 보호
    t = lock_oneliner_if_short(t, one_line_threshold)
    t = smart_biline_break(t, biline_target) # 필요한 경우만 \N 강제
    t = sanitize_ass_text(t)
    # 완전 공백 방지(정말 빈 경우는 NBSP 하나라도 넣어 표시 강제)
    if not t.strip().replace(NBSP, "").replace(ASS_NL, ""):
        t = NBSP
    return t

ASS_NL = r"\N"

def _visible_len(s: str) -> int:
    # 래핑 판단용 길이(개략). NBSP는 공백 취급.
    return len((s or "").replace(NBSP, " "))

def lock_oneliner_if_short(text: str, threshold: int = 12) -> str:
    if _visible_len(text) <= threshold:
        return (text or "").replace(" ", NBSP)
    return text

def smart_biline_break(text: str, target: int = 14) -> str:
    raw = (text or "").replace(NBSP, " ")
    if len(raw) <= target * 2:
        return text  # 자동 래핑에 맡김

    import re
    candidates = [m.start() for m in re.finditer(r"[ ,·/](?!$)", raw)]
    if not candidates:
        # 조사 경계
        candidates = [m.end() for m in re.finditer(r"[은는이가을를도만의에](?!$)", raw)]

    mid = len(raw) // 2
    pos = None
    if candidates:
        pos = min(candidates, key=lambda i: abs(i - mid))
    else:
        pos = mid

    left = raw[:pos].rstrip()
    right = raw[pos:].lstrip()
    return (left + ASS_NL + right).replace(" ", " ")

NBSP = "\u00A0"

def bind_compounds(
    text: str,
    unit_words=None,        # 숫자 뒤에 붙는 단위/접미
    counter_words=None,     # 번/수/명/개/칸/차례 등 카운터
    bignum_prefixes=None,   # 수십/수백/수천/수만/수백만/수억/수조...
    user_terms=None         # 사용자가 보호하고 싶은 구(낱말 묶음)
) -> str:
    """
    문장 내부에서 '끊기면 어색한 결합 표현'을 자동 감지해 공백을 NBSP로 바꿉니다.
    (줄바꿈 알고리즘이 NBSP를 분할 지점으로 보지 않아 자연스러운 끊김을 유도)

    - 숫자+단위: 3수, 9점, 1분, 30초, 1cm, 1만 2천 km, 10의 120제곱
    - 큰수+단위: 수백만 수, 수천만 명 ...
    - 이름+값: 퀸 9점, 룩 5점, 폰 1점
    - 양화: (단 )?한/두/세/... + 번/수/명/개/칸/(에)
    - 사용자 정의 용어: user_terms=["한 번에","수백만 수"] 등
    """
    if not text or text.isspace():
        return text

    unit_words = unit_words or [
        "수","점","분","초","칸","번","가지","명","개","년","배","%",
        "km","m","cm","mm","kg","g","mg","℃","℉","°"
    ]
    counter_words = counter_words or ["번","수","가지","명","개","칸","차례"]
    bignum_prefixes = bignum_prefixes or [
        "수십","수백","수천","수만","수십만","수백만","수천만","수억","수조"
    ]
    user_terms = user_terms or []

    t = text

    # 0) 사용자 지정 어구 보호 (그대로 넣으면 가장 유연)
    #    예: ["한 번에", "수백만 수", "단 한 수"]
    if user_terms:
        # 긴 어구부터 치환(부분 중복 방지)
        for term in sorted(user_terms, key=len, reverse=True):
            safe = term.replace(" ", NBSP)
            # 단어 경계 무시하고 그대로 찾아 치환
            t = t.replace(term, safe)

    # 1) '이름 + 숫자 + (점|수|칸|분|초|%)' 패턴 (퀸 9점, 룩 5점, 폰 1점)
    #    이름은 한글/영문 단어 한 개로 가정
    name_val = re.compile(
        r"([가-힣A-Za-z]+)\s+(\d+(?:\.\d+)?)\s*(점|수|칸|분|초|%)"
    )
    def _name_val(m):
        return f"{m.group(1)}{NBSP}{m.group(2)}{NBSP}{m.group(3)}"
    t = name_val.sub(_name_val, t)

    # 2) '숫자(복합) + 단위' 패턴 (1만 2천 km, 3 수, 30 초, 1 cm ...)
    #    - '1만 2천' 같이 내부 공백도 NBSP로
    unit_alt = "|".join(map(re.escape, unit_words))
    num_unit = re.compile(
        rf"((?:\d+(?:\s*[만천백십])?)(?:\s*\d+)*)(?:\s*)({unit_alt})"
    )
    def _num_unit(m):
        left = m.group(1).replace(" ", NBSP)
        return f"{left}{NBSP}{m.group(2)}"
    t = num_unit.sub(_num_unit, t)

    # 3) '큰수 접두(수백/수천만/수억/수조...) + 단위' (수백만 수, 수천만 명)
    big_alt = "|".join(map(re.escape, bignum_prefixes))
    big_unit = re.compile(rf"({big_alt})\s*({unit_alt})")
    t = big_unit.sub(lambda m: f"{m.group(1)}{NBSP}{m.group(2)}", t)

    # 4) 지수 표기 '10의 120제곱'
    expo = re.compile(r"(\d+)\s*의\s*(\d+)\s*제곱")
    t = expo.sub(lambda m: f"{m.group(1)}{NBSP}의{NBSP}{m.group(2)}{NBSP}제곱", t)

    # 5) 양화 표현 '(단 )?한/두/세/... + 번/수/가지/명/개/칸 (+에)'
    quant_num = "(한|두|세|네|다섯|여섯|일곱|여덟|아홉|열)"
    counter_alt = "|".join(map(re.escape, counter_words))
    quant = re.compile(rf"(단\s+)?{quant_num}\s+({counter_alt})(에)?")
    def _quant(m):
        pre = (m.group(1) or "").replace(" ", NBSP)  # "단 " -> "단&nbsp;"
        core = f"{m.group(2)}{NBSP}{m.group(3)}"     # "한 번"
        tail = f"{NBSP}{m.group(4)}" if m.group(4) else ""
        return f"{pre}{core}{tail}"
    t = quant.sub(_quant, t)

    # 6) 공백 정리(이중 이상 -> 단일), 문두/문미 공백 제거 (NBSP는 유지)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()
    return t

def build_image_paths_for_dense_segments(segments_for_video, persona_text: str):
    if "seen_photo_ids" not in st.session_state:
        st.session_state.seen_photo_ids = set()
    if "query_page_cursor_img" not in st.session_state:
        st.session_state.query_page_cursor_img = {}

    sentence_units = [s.get('text', '') for s in segments_for_video]
    per_sentence_queries = get_scene_keywords_batch(sentence_units, persona_text)
    for i, q in enumerate(per_sentence_queries, start=1):
        st.write(f"🧩 촘촘조각 {i} 키워드: {q}")

    def _img_search_once(q: str, idx: int, page: int):
        try:
            paths, ids = generate_images_for_topic(
                q, 1,
                start_index=idx,
                page=page,
                exclude_ids=st.session_state.seen_photo_ids,
                return_ids=True
            )
        except TypeError:
            paths = generate_images_for_topic(q, 1, start_index=idx)
            ids = []
        if paths:
            if ids:
                st.session_state.seen_photo_ids.update(ids)
            return _save_unique_image(paths[0], idx)
        return None

    def _normalize_scene_query(raw: str) -> str:
        import re
        if not raw: return ""
        s = raw.strip()
        s = re.sub(r'(?i)^(here are .*?:)\s*', '', s)
        s = re.sub(r'(?i)^(keywords?|키워드)\s*:\s*', '', s)
        s = s.replace("\n", " ").replace("\r", " ")
        s = re.sub(r'["“”‘’\'`]+', '', s)
        s = re.sub(r'[^A-Za-z\uAC00-\uD7A30-9 ,\-./°%]+', ' ', s)
        s = re.sub(r'\s*,\s*', ',', s)
        s = re.sub(r'\s*\.\s*', '.', s)
        s = re.sub(r'\s{2,}', ' ', s).strip(' ,').strip()
        parts = [p.strip() for p in s.split(',') if p.strip()]
        if parts: s = ', '.join(parts[:3])
        return s[:90].rstrip(' ,')

    def _fetch_one_image(q: str, idx: int, page_tries: int = 4):
        base_pg = st.session_state.query_page_cursor_img.get(q, 1)
        for step in range(page_tries):
            pg = base_pg + step
            got = _img_search_once(q, idx, pg)
            if got:
                st.session_state.query_page_cursor_img[q] = pg + 1
                return got
        if "," in q:
            for piece in [p.strip() for p in q.split(",") if p.strip()]:
                base_pg2 = st.session_state.query_page_cursor_img.get(piece, 1)
                for step in range(page_tries):
                    pg = base_pg2 + step
                    got = _img_search_once(piece, idx, pg)
                    if got:
                        st.session_state.query_page_cursor_img[piece] = pg + 1
                        return got
        fb = _normalize_scene_query(q)
        if fb and fb != q:
            base_pg3 = st.session_state.query_page_cursor_img.get(fb, 1)
            for step in range(page_tries):
                pg = base_pg3 + step
                got = _img_search_once(fb, idx, pg)
                if got:
                    st.session_state.query_page_cursor_img[fb] = pg + 1
                    return got
        return None

    image_paths = []
    target_len = len(segments_for_video)
    for idx, q in enumerate(per_sentence_queries, start=1):
        st.write(f"🖼️ 촘촘조각 {idx} 검색: {q}")
        path = _fetch_one_image(q, idx, page_tries=4)
        image_paths.append(path)

    if len(image_paths) < target_len:
        last = image_paths[-1] if image_paths else None
        image_paths += [last] * (target_len - len(image_paths))
    elif len(image_paths) > target_len:
        image_paths = image_paths[:target_len]

    st.success(f"이미지 {sum(1 for p in image_paths if p)}장 확보 / 총 {target_len}조각")
    return image_paths

def enforce_reading_speed_non_merging(events, min_cps=11.0, floor=0.60, ceiling=None, margin=0.02):
    """
    자막을 '합치지' 않고, 가능한 범위에서만 end를 늘려
    - 글자수/읽기속도 기반 최소 노출시간 보장
    - 다음 cue의 시작은 침범하지 않음
    """
    if not events:
        return events
    out = []
    for i, e in enumerate(events):
        s  = float(e["start"])
        ed = float(e["end"])
        text = (e.get("text") or "").strip()
        need = max(floor, (len(text) / max(min_cps, 1e-6)) if text else floor)
        target_end = s + need
        # 다음 cue 시작 직전까지만 확장
        if i + 1 < len(events):
            next_s = float(events[i+1]["start"])
            ed = min(max(ed, target_end), next_s - margin)
        else:
            ed = max(ed, target_end)
        if ceiling is not None:
            ed = min(ed, s + float(ceiling))
        if ed < s + 0.02:
            ed = s + 0.02
        out.append({**e, "start": round(s, 3), "end": round(ed, 3)})
    return out

def _protect_short_tail_nbsp(text: str) -> str:
    """
    '보병 같죠?' 같은 꼬리가 다음 줄로 떨어지지 않도록,
    꼬리 앞 공백을 NBSP로 치환.
    """
    NBSP = "\u00A0"
    # 한/두 단어 꼬리 패턴들
    TAILS = [
        r"같죠\?", r"그렇죠\?", r"그죠\?", r"그죠",
        r"이죠\?", r"이죠", r"죠\?", r"죠",
        r"입니다", r"예요", r"이에요", r"이다", r"다$"
    ]
    pat = re.compile(r"\s+(?=(" + "|".join(TAILS) + r"))")
    return pat.sub(NBSP, (text or "").strip())

def apply_nbsp_tails(events):
    return [{**e, "text": _protect_short_tail_nbsp(e.get("text") or "")} for e in events]

def quantize_events(events, fps=24.0):
    """자막 시간을 비디오 프레임 격자에 맞춰 스냅."""
    if not events: return events
    tick = 1.0 / float(fps)
    out, prev_end = [], None
    for e in events:
        s  = round(float(e["start"]) / tick) * tick
        ed = round(float(e["end"])   / tick) * tick
        if prev_end is not None and s < prev_end:
            s = prev_end
        if ed <= s:
            ed = s + tick
        out.append({**e, "start": round(s, 3), "end": round(ed, 3)})
        prev_end = ed
    return out

def clamp_no_overlap(events, margin=0.05):
    """
    각 cue의 end가 반드시 다음 cue start - margin 이하가 되도록 클램프.
    병합/텍스트 변경 없음. 시간만 조정.
    """
    if not events: 
        return events
    out = []
    n = len(events)
    for i, e in enumerate(events):
        s = float(e["start"])
        ed = float(e["end"])
        if i + 1 < n:
            next_s = float(events[i+1]["start"])
            ed = min(ed, next_s - margin)  # 다음 cue 시작보다 조금(=margin) 일찍 끝내기
        # 너무 짧아져도 20ms는 보장
        if ed < s + 0.02:
            ed = s + 0.02
        out.append({**e, "start": round(s, 3), "end": round(ed, 3)})
    # 단조성 최종 보정
    for i in range(n - 1):
        if out[i]["end"] > out[i+1]["start"] - margin:
            out[i]["end"] = max(out[i]["start"] + 0.02, out[i+1]["start"] - margin)
    return out

def enforce_min_duration_non_merging(events, min_dur=0.35, margin=0.05):
    """
    cue를 병합하지 않고 '가능한 범위에서만' 길이를 늘립니다.
    다음 cue의 start를 침범하지 않도록 margin을 남기고 확장.
    """
    if not events:
        return events
    out = []
    for i, e in enumerate(events):
        s, ed = float(e["start"]), float(e["end"])
        dur = ed - s
        if dur < min_dur:
            target = s + min_dur
            if i + 1 < len(events):
                max_end = float(events[i+1]["start"]) - margin
                ed = min(target, max_end)
            else:
                ed = target
        out.append({**e, "start": round(s, 3), "end": round(ed, 3)})
    # 마지막으로 겹침 방지
    return clamp_no_overlap(out, margin=margin)

def enforce_min_duration(segs, min_dur=0.35):
    out = []
    cur = None
    for s in segs:
        if cur is None:
            cur = dict(s); continue
        if (cur["end"] - cur["start"]) < min_dur:
            cur["end"]  = s["end"]
            cur["text"] = (cur["text"] + " " + s["text"]).strip()
        else:
            out.append(cur); cur = dict(s)
    if cur: out.append(cur)
    if len(out) >= 2 and (out[-1]["end"] - out[-1]["start"]) < min_dur:
        out[-2]["end"]  = out[-1]["end"]
        out[-2]["text"] = (out[-2]["text"] + " " + out[-1]["text"]).strip()
        out.pop()
    return out

def _tokenize_words_for_kr_en(text: str):
    """한/영 혼합 문장을 단어(또는 덩어리)+문장부호 수준으로 토큰화."""
    import re
    tokens = re.findall(r'[\uAC00-\uD7A3A-Za-z0-9]+|[^\s]', text or "")
    merged = []
    for t in tokens:
        if re.match(r'^[^\uAC00-\uD7A3A-Za-z0-9]+$', t) and merged:
            merged[-1] += t
        else:
            merged.append(t)
    return merged

def densify_subtitles_by_words(segments, target_min_events: int):
    """
    자막 세그먼트를 단어 단위로 더 잘게 쪼개어 '한 화면에 문단이 왕창' 뜨는 현상 방지.
    오디오 타이밍은 유지하고, 각 세그먼트 내부에서 글자 길이 비율로 시간 배분.
    """
    import re
    total_tokens = 0
    per_seg_tokens = []
    for s in segments:
        toks = _tokenize_words_for_kr_en(s['text'])
        per_seg_tokens.append(toks)
        total_tokens += len(toks)

    if total_tokens == 0:
        return segments

    desired_events = max(target_min_events, len(segments))
    chunk_size = max(1, min(6, math.ceil(total_tokens / desired_events)))

    dense = []
    for s, toks in zip(segments, per_seg_tokens):
        if not toks:
            dense.append(s)
            continue
        seg_start, seg_end = s['start'], s['end']
        seg_dur = max(0.01, seg_end - seg_start)
        n_chunks = math.ceil(len(toks) / chunk_size)
        t0 = seg_start
        base_len = max(1, len("".join(toks)))
        for i in range(n_chunks):
            part = toks[i*chunk_size:(i+1)*chunk_size]
            if not part: 
                continue
            is_kor = bool(re.search(r'[\uAC00-\uD7A3]', "".join(part)))
            text = ('' if is_kor else ' ').join(part).strip()
            part_ratio = len("".join(part)) / base_len
            dur = seg_dur * part_ratio
            t1 = t0 + dur
            if i == n_chunks - 1:
                t1 = seg_end
            dense.append({'start': t0, 'end': t1, 'text': text})
            t0 = t1
    return dense

def coalesce_segments_for_videos(segments, clip_count: int):
    """
    영상이 적을 때, 연속 세그먼트를 clip_count개 구간으로 병합해
    각 영상 클립이 맡을 구간을 만들어줌(자막은 촘촘한 dense 버전으로 별도 표시).
    """
    if clip_count <= 0 or not segments:
        return segments
    total_duration = segments[-1]['end']
    target = total_duration / clip_count
    coalesced, cur_start, acc = [], segments[0]['start'], 0.0
    for s in segments:
        acc += (s['end'] - s['start'])
        if acc >= target and len(coalesced) < clip_count - 1:
            coalesced.append({'start': cur_start, 'end': s['end'], 'text': ''})
            cur_start, acc = s['end'], 0.0
    if len(coalesced) < clip_count:
        coalesced.append({'start': cur_start, 'end': segments[-1]['end'], 'text': ''})
    return coalesced

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

def _normalize_scene_query(raw: str) -> str:
    import re
    if not raw:
        return ""
    s = raw.strip()

    # 프리앰블 제거
    s = re.sub(r'(?i)^(here are .*?:)\s*', '', s)
    s = re.sub(r'(?i)^(keywords?|키워드)\s*:\s*', '', s)

    # 줄바꿈/따옴표 제거
    s = s.replace("\n", " ").replace("\r", " ")
    s = re.sub(r'["“”‘’\'`]+', '', s)

    # ✅ 허용 문자 범위 완화: 영문 + 한글 + 숫자 + 공백 + , - . / ° %
    s = re.sub(r'[^A-Za-z\uAC00-\uD7A30-9 ,\-./°%]+', ' ', s)

    # ✅ 천단위·소수점 주변 공백 정리
    s = re.sub(r'\s*,\s*', ',', s)
    s = re.sub(r'\s*\.\s*', '.', s)

    # 공백 정리
    s = re.sub(r'\s{2,}', ' ', s).strip(' ,').strip()

    # 쉼표로 쪼개 최대 3조각
    parts = [p.strip() for p in s.split(',') if p.strip()]
    if parts:
        s = ', '.join(parts[:3])

    # 너무 길면 컷
    if len(s) > 90:
        s = s[:90].rstrip(' ,')

    return s

def _save_unique_image(src_path_or_url: str, idx: int) -> str:
    """
    이미지가 같은 파일명으로 덮어쓰기 되는 문제를 막기 위해
    문장 인덱스별로 고유 파일명으로 저장/복사합니다.
    - 로컬 경로면 copy
    - URL이면 다운로드
    """
    import os, shutil, mimetypes
    import requests

    os.makedirs("assets/scene_images", exist_ok=True)

    def _guess_ext(p: str) -> str:
        # 확장자 추정 (없으면 .jpg)
        base, ext = os.path.splitext(p)
        if ext and len(ext) <= 5:
            return ext
        # URL/헤더에서 MIME으로 추정
        if p.startswith("http"):
            try:
                head = requests.head(p, timeout=10)
                ctype = head.headers.get("Content-Type", "")
                ext = mimetypes.guess_extension(ctype.split(";")[0].strip()) or ".jpg"
                return ext
            except Exception:
                return ".jpg"
        return ".jpg"

    ext = _guess_ext(src_path_or_url)
    dst = os.path.join("assets/scene_images", f"img_sent_{idx:02d}{ext}")

    try:
        if src_path_or_url.startswith("http"):
            r = requests.get(src_path_or_url, timeout=30)
            r.raise_for_status()
            with open(dst, "wb") as f:
                f.write(r.content)
        else:
            shutil.copyfile(src_path_or_url, dst)
    except Exception:
        # 실패 시라도 최소한 원본 경로를 반환
        return src_path_or_url

    return dst

def get_scene_keywords_batch(sentence_units, persona_text: str):
    """
    여러 문장을 한 번에 LLM에 보내서, 문장 수만큼 키워드 라인으로 받아옵니다.
    출력 형식(중요): i번째 문장은 'i. keyword' 한 줄
    """
    scene_chain = get_default_chain(system_prompt="당신은 숏폼 비주얼 장면 키워드 생성 전문가입니다.")

    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sentence_units))
    prompt = f"""너는 숏폼 비디오/이미지의 '장면 검색 키워드'를 만드는 도우미다.

[페르소나]
{persona_text}

[문장들]
{numbered}

[요구]
- 각 문장에 대해 1줄의 키워드만 생성
- i번째 줄은 'i. one short phrase' 형식
- 각 키워드는 3~6단어의 영어 구문, 반드시 1개만
- 반드시 키워드만, 라벨/설명/따옴표/줄바꿈 추가 금지
- 같은(혹은 거의 같은) 키워드/구를 여러 줄에 반복 사용하지 말 것. 유사 개념이면 스타일·시간대·로케이션을 바꿔 변주할 것.

응답:
"""

    raw = scene_chain.invoke({"question": prompt, "chat_history": []}).strip()
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]

    # 문장 수만큼 빈 리스트 준비
    out = [""] * len(sentence_units)
    for ln in lines:
        m = re.match(r"^\s*(\d+)\.\s*(.+)$", ln)
        if not m:
            continue
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(out):
            out[idx] = _normalize_scene_query(m.group(2))

    # 비어 있는 건 문장 원문을 영어로 번역해서 폴백
    for i, val in enumerate(out):
        if not val:
            try:
                t = GoogleTranslator(source='auto', target='en').translate(sentence_units[i])
            except Exception:
                t = sentence_units[i]
            out[i] = _normalize_scene_query(t)

    return out

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
                    if len(snippet) > 300:
                        snippet = snippet[:300] + "..."
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
            st.session_state.selected_script_persona_index = selected_idx
            
            st.session_state.edited_script_content = st.text_area(
                "🎬 스크립트 내용 수정",
                value=selected_script,
                key="script_editor_editable"
            )

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

        # 제목 입력칸: VIDEO_TEMPLATE에서는 숨김
        if not is_video_template:
            st.session_state.video_title = st.text_input(
                "영상 제목 (영상 위에 표시될 제목)",
                value=st.session_state.video_title,
                key="video_title_input_final",
                on_change=_lock_title
            )
        else:
            st.session_state.video_title = ""  # 제목 사용 안 함

        if is_emotional:
            st.info("감성 텍스트 영상은 **이미지/음성 없이** 텍스트 + (선택) BGM으로만 제작됩니다.")
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

        st.session_state.selected_tts_lang = st.radio(
            "🎙️ 음성 언어 선택:",
            options=["ko", "en"],
            index=0,  # 기본 한국어
            key="tts_lang_select"
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
            # main.py — "영상 만들기" 버튼 안, 문장별 영상 검색 직전에 추가
            if "seen_video_ids" not in st.session_state:
                st.session_state.seen_video_ids = set()
            if "query_page_cursor" not in st.session_state:
                st.session_state.query_page_cursor = {}  # {query: next_page_int}
            if "seen_photo_ids" not in st.session_state:
                st.session_state.seen_photo_ids = set()
            if "query_page_cursor_img" not in st.session_state:
                st.session_state.query_page_cursor_img = {}  # {query: next_page_int}
                
            final_script_for_video = st.session_state.edited_script_content
            final_title_for_video = st.session_state.video_title  # VIDEO_TEMPLATE이면 빈 문자열이어도 됨

            if not final_script_for_video.strip():
                st.error("스크립트 내용이 비어있습니다.")
                st.stop()

            # 제목은 VIDEO_TEMPLATE일 때 필수 아님
            if (not is_video_template) and (not final_title_for_video.strip()):
                st.error("영상 제목이 비어있습니다.")
                st.stop()

            with st.spinner("✨ 영상 제작 중입니다..."):
                try:
                    media_query_final = ""
                    audio_path = None
                    segments = []
                    ass_path = None

                    # --- 음성 포함/미포함 분기 ---
                    if not is_emotional and st.session_state.include_voice:
                        # (중요) 이중 음성 방지: 별도의 단발 TTS 생성 없이
                        # generate_subtitle_from_script 한 번으로 라인별 TTS→병합까지 수행.
                        audio_output_dir = "assets"
                        os.makedirs(audio_output_dir, exist_ok=True)
                        audio_path = os.path.join(audio_output_dir, "generated_audio.mp3")

                        st.write("🗣️ 라인별 TTS 생성/병합 및 세그먼트 산출 중...")
                        provider = "elevenlabs" if st.session_state.selected_tts_provider == "ElevenLabs" else "polly"
                        tmpl = st.session_state.selected_tts_template if provider == "elevenlabs" else st.session_state.selected_polly_voice_key
                        
                        segments, audio_clips, ass_path = generate_subtitle_from_script(
                            script_text=final_script_for_video,
                            ass_path=os.path.join("assets", "generated_subtitle.ass"),
                            full_audio_file_path=audio_path,
                            provider=provider,
                            template=tmpl,
                            polly_voice_key=st.session_state.selected_polly_voice_key,  # ✅ 실제 선택 보이스 반영
                            subtitle_lang="ko",
                            translate_only_if_english=False,
                            tts_lang=st.session_state.selected_tts_lang,
                            split_mode="new_line",
                            strip_trailing_punct_last=False
                        )
                        
                        try:
                            with AudioFileClip(audio_path) as aud:
                                aud_dur = float(aud.duration or 0.0)
                            if segments and aud_dur > 0:
                                # 약간의 여유(20ms) 줘서 -shortest 트림 방지
                                if aud_dur + 0.02 > segments[-1]["end"]:
                                    segments[-1]["end"] = aud_dur + 0.02
                        except Exception as e:
                            print("Audio length check failed:", e)
                        
                        # ✅ 생성 직후 '진짜로' 만들어졌는지 강제 검증
                        if not segments:
                            st.error("TTS 생성 실패: 세그먼트가 비어 있습니다. (라인별 실패 로그를 확인하세요)")
                            st.stop()

                        try:
                            sz = os.path.getsize(audio_path)
                        except Exception:
                            sz = 0
                        if sz < 5_000:  # 5KB 미만이면 사실상 실패로 간주
                            st.error(f"TTS 생성 실패: 오디오 파일 용량이 비정상적입니다 ({sz} bytes).")
                            st.stop()

                        # === 기존 dense 생성 부분 교체(생성 그대로) ===
                        dense_events = []

                        def _densify_for_fast_tempo(events, words_per_piece=2):
                            # 단어 수 기준으로 목표 이벤트 개수 산정 → 더 촘촘하게 분할
                            import math
                            total_tokens = sum(len(_tokenize_words_for_kr_en(e.get("text",""))) for e in events)
                            if total_tokens == 0: 
                                return events
                            target = max(len(events), math.ceil(total_tokens / max(1, int(words_per_piece))))
                            return densify_subtitles_by_words(events, target)

                        for seg in segments:  # seg = {"start","end","text","ssml"(optional)}
                            if seg.get("ssml"):
                                ev = _build_dense_from_ssml(seg["ssml"], seg["start"], seg["end"], fps=30.0)
                                # 🔥 SSML도 빠른 템포로 더 촘촘히 분할
                                ev = _densify_for_fast_tempo(ev, words_per_piece=2)
                                dense_events += ev
                            else:
                                dense_events += auto_densify_for_subs(
                                    [seg], tempo="fast", words_per_piece=2,
                                    min_tail_words=2, chunk_strategy=None,
                                    marks_voice_key=st.session_state.selected_polly_voice_key,
                                    max_chars_per_piece=14, min_piece_dur=0.50
                                )

                        # === ① 경계 보강 ===
                        dense_events = harden_ko_sentence_boundaries(dense_events)

                        # === ② 텍스트 보호/정리(줄 강제 없이 "보호" 위주) ===
                        def drop_or_fix_empty_text(events):
                            out = []
                            for e in events:
                                t = (e.get("text") or "").strip()
                                if not t.replace(NBSP, ""):
                                    t = NBSP
                                out.append({**e, "text": t})
                            return out

                        def ensure_min_frames(events, fps=30.0, min_frames=2):
                            tick = 1.0 / float(fps)
                            min_d = min_frames * tick
                            out = []
                            for i, e in enumerate(events):
                                s, ed = float(e["start"]), float(e["end"])
                                if ed - s < min_d:
                                    ed = s + min_d
                                # 다음 cue와 겹치지 않도록 마지막에 한번 더 clamp
                                out.append({**e, "start": round(s, 3), "end": round(ed, 3)})
                            # 인접 겹침 방지
                            for i in range(len(out) - 1):
                                if out[i]["end"] > out[i+1]["start"]:
                                    out[i]["end"] = max(out[i]["start"], out[i+1]["start"] - 0.001)
                            return out

                        def prepare_text_for_ass(text: str, one_line_threshold=12, biline_target=14):
                            """
                            - '1줄이면 무조건 1줄' 원칙을 반영하되, 상위 generate_ass_subtitle가 최종 판단.
                            - 여기서는 가벼운 보호만: 숫자+단위, 수량 어구 NBSP, 말꼬리 보호.
                            """
                            t = (text or "").strip()
                            if not t:
                                return NBSP
                            # 보호(숫자+단위/수량 등) — 기존 bind_compounds가 있다면 활용
                            try:
                                t = bind_compounds(t)
                            except Exception:
                                pass
                            # 말꼬리 보호(옵션 함수가 있다면)
                            try:
                                from re import compile
                                def _protect_short_tail_nbsp_local(s: str) -> str:
                                    NB = "\u00A0"
                                    TAILS = [r"같죠\?", r"그렇죠\?", r"그죠\?", r"그죠",
                                            r"이죠\?", r"이죠", r"죠\?", r"죠",
                                            r"입니다", r"예요", r"이에요", r"이다", r"다$"]
                                    pat = compile(r"\s+(?=(" + "|".join(TAILS) + r"))")
                                    return pat.sub(NB, s)
                                t = _protect_short_tail_nbsp_local(t)
                            except Exception:
                                pass
                            # 1줄 선호 → 길이가 아주 짧으면 아예 1줄 고정
                            if len(t) <= one_line_threshold:
                                return t
                            # 2줄 필요 판단은 generate_ass_subtitle에서 최종 처리(\N 삽입)
                            return t

                        dense_events = [{**e, "text": prepare_text_for_ass(e["text"], one_line_threshold=12, biline_target=14)} for e in dense_events]
                        dense_events = dedupe_adjacent_texts(dense_events)
                        dense_events = drop_or_fix_empty_text(dense_events)

                        # === ③ 타이밍 안정화 ===
                        dense_events = clamp_no_overlap(dense_events, margin=0.02)
                        dense_events = enforce_min_duration_non_merging(dense_events, min_dur=0.50, margin=0.02)
                        dense_events = quantize_events(dense_events, fps=30.0)
                        dense_events = ensure_min_frames(dense_events, fps=30.0, min_frames=2)

                        # ⑤ ASS 생성
                        generate_ass_subtitle(
                            segments=dense_events,
                            ass_path=ass_path,
                            template_name=st.session_state.selected_subtitle_template,
                            strip_trailing_punct_last=True,
                            max_chars_per_line=14,
                            max_lines=2
                        )
                        segments_for_video = dense_events

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
                        if segments:
                            segments[-1]["end"] = current_time

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
                            # 🔧 영상 합성에서 참조할 최종 세그먼트 셋업
                            segments_for_video = [{**e, "text": prepare_text_for_ass(e["text"], one_line_threshold=12, biline_target=14)} for e in segments]
                            segments_for_video = dedupe_adjacent_texts(segments_for_video)
                            segments_for_video = drop_or_fix_empty_text(segments_for_video)
                            segments_for_video = clamp_no_overlap(segments_for_video, margin=0.02)
                            segments_for_video = enforce_min_duration_non_merging(segments_for_video, min_dur=0.50, margin=0.02)
                            segments_for_video = quantize_events(segments_for_video, fps=30.0)
                            segments_for_video = ensure_min_frames(segments_for_video, fps=30.0, min_frames=2)

                    # --- 미디어(이미지 or 영상) 수집 ---
                    image_paths, video_paths = [], []
                    if st.session_state.video_style != "감성 텍스트 영상":
                        if is_video_template:
                            # ✅ 문장 단위(segments)로 문장별 키워드 생성 → 영상 1개씩 매칭
                            st.write("🎯 문장별로 페르소나 기반 키워드를 만들어 개별 영상 검색을 수행합니다.")

                            # 1) 문장 리스트
                            sentence_units = [s['text'] for s in segments]

                            # 2) 페르소나 지시문
                            persona_text = ""
                            try:
                                pidx = st.session_state.get("selected_script_persona_index", None)
                                if pidx is not None:
                                    persona_text = st.session_state.persona_blocks[pidx]["text"]
                            except Exception:
                                persona_text = ""

                            # 3) ✅ 문장별 키워드를 한 번에 받기 (배치)
                            per_sentence_queries = get_scene_keywords_batch(sentence_units, persona_text)
                            for i, q in enumerate(per_sentence_queries, start=1):
                                st.write(f"🧩 문장 {i} 키워드(정규화): {q}")

                            # 4) 문장별로 영상 1개씩 검색
                            video_paths = []

                            def _try_search_once(q: str, clip_idx: int):
                                # 키워드별 다음 페이지 커서 (기본 1)
                                pg = st.session_state.query_page_cursor.get(q, 1)
                                paths, ids = generate_videos_for_topic(
                                    query=q,
                                    num_videos=1,
                                    start_index=clip_idx,           # 파일명 일관성 유지
                                    orientation="portrait",
                                    page=pg,                        # ✅ 이 키워드는 여기서부터
                                    exclude_ids=st.session_state.seen_video_ids,  # ✅ 이미 쓴 건 건너뛰기
                                    return_ids=True
                                )
                                if paths:
                                    # 성공 → 다음에 같은 키워드 쓰면 다음 페이지부터
                                    st.session_state.query_page_cursor[q] = pg + 1
                                    st.session_state.seen_video_ids.update(ids)
                                return paths

                            for clip_idx, q in enumerate(per_sentence_queries, start=1):
                                st.write(f"🎞️ 문장 {clip_idx} 검색: {q}")

                                got = _try_search_once(q, clip_idx)

                                # 콤마로 나뉜 구문이면 조각별로도 재시도
                                if not got and ("," in q):
                                    for piece in [p.strip() for p in q.split(",") if p.strip()]:
                                        got = _try_search_once(piece, clip_idx)
                                        if got: break

                                # 그래도 없으면 키워드 정규화 후 한 번 더
                                if not got:
                                    fb = _normalize_scene_query(q)
                                    got = _try_search_once(fb, clip_idx)

                                if got:
                                    video_paths.extend(got)

                            # 5) 길이 보정
                            if len(video_paths) < len(segments):
                                st.warning(f"영상이 {len(video_paths)}개뿐입니다. 일부 문장은 마지막 클립을 재사용합니다.")
                                if video_paths:
                                    video_paths += [video_paths[-1]] * (len(segments) - len(video_paths))

                        else:
                            # --- 이미지 수집(문장당 1장, 부족 시 추가 탐색) ---
                            st.write("🖼️ 문장별로 페르소나 기반 키워드를 만들어 이미지 1장씩 생성/검색합니다.") 

                            persona_text = ""
                            try:
                                pidx = st.session_state.get("selected_script_persona_index", None)
                                if pidx is not None:
                                    persona_text = st.session_state.persona_blocks[pidx]["text"]
                            except Exception:
                                pass

                            image_paths = build_image_paths_for_dense_segments(segments_for_video, persona_text)


                    # --- 합성 ---
                    video_output_dir = "assets"
                    os.makedirs(video_output_dir, exist_ok=True)
                    temp_video_path = os.path.join(video_output_dir, "temp_video.mp4")
                    final_video_path = os.path.join(video_output_dir, "final_video_with_subs.mp4")

                    st.write("🎬 비디오 합성 중...")
                    if is_emotional:
                        created_video_path = create_dark_text_video(
                            script_text=final_script_for_video,
                            title_text="",  # 감성 텍스트: 화면 제목 비사용
                            audio_path=None,
                            bgm_path=st.session_state.bgm_path,
                            save_path=temp_video_path
                        )
                        final_video_with_subs_path = created_video_path
                    else:
                        if is_video_template:
                            created_video_path = create_video_from_videos(
                                video_paths=video_paths,
                                segments=segments_for_video,  # ✅ 병합/조정된 구간 사용
                                audio_path=st.session_state.audio_path if st.session_state.include_voice else None,
                                topic_title="",
                                include_topic_title=False,
                                bgm_path=st.session_state.bgm_path,
                                save_path=temp_video_path
                            )
                        else:
                            created_video_path = create_video_with_segments(
                                image_paths=image_paths,
                                segments=segments_for_video,
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
