from deep_translator import GoogleTranslator
from ssml_converter import convert_line_to_ssml
# generate_timed_segments.py
import os
import re
from elevenlabs_tts import generate_tts
from pydub import AudioSegment
from moviepy import AudioFileClip
import kss

SUBTITLE_TEMPLATES = {
    "educational": {
        "Fontname": "NanumGothic",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "entertainer": {
        "Fontname": "NanumGothic",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "slow": {
        "Fontname": "NanumGothic",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "default": {
        "Fontname": "NanumGothic",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "korean_male": {
        "Fontname": "NanumGothic",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "korean_male2": {
        "Fontname": "NanumGothic",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "korean_female": {
        "Fontname": "NanumGothic",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "korean_female2": {
        "Fontname": "NanumGothic",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    }
}

def _looks_english(text: str) -> bool:
    # 매우 단순한 휴리스틱: 알파벳이 한글보다 확실히 많으면 영어로 간주
    letters = len(re.findall(r'[A-Za-z]', text))
    hangul = len(re.findall(r'[\uac00-\ud7a3]', text))
    return letters >= max(3, hangul * 2)

def _detect_script_language(lines):
    eng = sum(_looks_english(x) for x in lines)
    kor = sum(bool(re.search(r'[\uac00-\ud7a3]', x)) for x in lines)
    return 'en' if eng > kor else 'ko'

def _maybe_translate_lines(lines, target='ko', only_if_src_is_english=True):
    if not lines:
        return lines
    try:
        src = _detect_script_language(lines)
        if only_if_src_is_english and src != 'en':
            # 원문이 영어가 아닐 때는 건드리지 않음
            return lines
        if target is None or target == src:
            return lines
        tr = GoogleTranslator(source='auto', target=target)
        return [tr.translate(l) if l.strip() else l for l in lines]
    except Exception:
        # 번역 실패 시 원문 유지 (크래시 방지)
        return lines

def _validate_ssml(text: str) -> str:
    """
    Polly 호출 전 SSML 안전성 검사 및 보정
    """
    # 1) 빈 prosody 블록 제거
    text = re.sub(r"<prosody[^>]*>\s*</prosody>", "", text)

    # 2) 잘못된 중첩/닫힘 보정 (간단히)
    # 열림과 닫힘 개수 안 맞으면 강제로 닫음
    open_count = text.count("<prosody")
    close_count = text.count("</prosody>")
    while close_count < open_count:
        text += "</prosody>"
        close_count += 1

    return text.strip()

def generate_tts_per_line(script_lines, provider, template, polly_voice_key="korean_female1"):
    audio_paths = []
    temp_audio_dir = "temp_line_audios"
    os.makedirs(temp_audio_dir, exist_ok=True)

    print(f"디버그: 총 {len(script_lines)}개의 스크립트 라인에 대해 TTS 생성 시도.")

    for i, line in enumerate(script_lines):
        line_audio_path = os.path.join(temp_audio_dir, f"line_{i}.mp3")
        try:
            # Polly면 한 번 더 안전 체크(빈 prosody 제거 등)
            line_ssml = _validate_ssml(line)

            # 완전체가 아니면 <speak> 래핑(혹시 상위 단계에서 못 감싼 경우 대비)
            ls = line_ssml.strip()
            if provider == "polly" and not ls.startswith("<speak"):
                ls = f"<speak>{ls}</speak>"

            generate_tts(
                text=ls,
                save_path=line_audio_path,
                provider=provider,
                template_name=template,
                polly_voice_name_key=polly_voice_key
            )
            audio_paths.append(line_audio_path)
            print(f"디버그: 라인 {i+1} ('{line[:30]}...') TTS 생성 성공. 파일: {line_audio_path}")
        except Exception as e:
            print(f"오류: 라인 {i+1} ('{line[:30]}...') TTS 생성 실패: {e}")
            continue
            
    print(f"디버그: 최종 생성된 오디오 파일 경로 수: {len(audio_paths)}")
    if not audio_paths:
        raise RuntimeError("라인별 TTS가 0건 생성됨 (각 라인의 실패 사유는 위 로그 참조)")
    
    return audio_paths

def merge_audio_files(audio_paths, output_path):
    merged = AudioSegment.empty()
    segments = []
    current_time = 0

    for i, path in enumerate(audio_paths):
        audio = AudioSegment.from_file(path)
        duration = audio.duration_seconds

        segments.append({
            "start": current_time,
            "end": current_time + duration
        })

        merged += audio
        current_time += duration

    merged.export(output_path, format="mp3")
    return segments

def get_segments_from_audio(audio_paths, script_lines):
    segments = []
    current_time = 0
    for i, audio_path in enumerate(audio_paths):
        try:
            audio = AudioSegment.from_file(audio_path)
            duration = audio.duration_seconds
            line = script_lines[i]
            segments.append({
                "start": current_time,
                "end": current_time + duration,
                "text": line
            })
            current_time += duration
        except Exception as e:
            print(f"오류: 오디오 파일 {audio_path} 처리 중 오류 발생: {e}")
            continue
    return segments

# --- pitch 할당 함수 ---
def _assign_pitch(text: str) -> int:
    if text.endswith("?"):
        return 20     # 질문/경고
    if text.endswith("습니다") or text.endswith("합니다"):
        return -5     # 일반 설명
    if text.endswith("이다") or text.endswith("없습니다"):
        return -18    # 결론/단정
    return 0

def generate_ass_subtitle(segments, ass_path, template_name="default",
                          strip_trailing_punct_last=True):
    settings = SUBTITLE_TEMPLATES.get(template_name, SUBTITLE_TEMPLATES["default"])

    def _escape_ass_text(s: str) -> str:
        s = s.replace("\\", r"\\")
        s = s.replace("\r", "")
        s = s.replace("\n", r"\N")
        return s

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n\n")

        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Bottom,{settings['Fontname']},{settings['Fontsize']},{settings['PrimaryColour']},{settings['OutlineColour']},1,{settings['Outline']},0,2,10,10,{settings['MarginV']},1\n\n")

        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        for i, seg in enumerate(segments):
            start, end = seg['start'], seg['end']
            text = (seg.get('text') or "").strip()
            if strip_trailing_punct_last and i == len(segments) - 1:
                text = _strip_last_punct_preserve_closers(text)
            text = _escape_ass_text(text)

            start_ts = format_ass_timestamp(start)
            end_ts   = format_ass_timestamp(end)

            # ✅ pitch 조건 → 색상 반영
            colour_tag = ""
            if "pitch" in seg and seg["pitch"] <= -15:
                colour_tag = "{\\c&H0000FF&}"  # 빨강

            f.write(f"Dialogue: 0,{start_ts},{end_ts},Bottom,,0,0,0,,{colour_tag}{text}\n")


def format_ass_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h:01}:{m:02}:{s:02}.{cs:02}"


def split_script_to_lines(script_text, mode="newline"):
    text = script_text or ""
    if mode == "punct":  # 콤마/마침표 기준
        parts = re.split(r'(?<=[,.])\s*', text.strip())
        return [p for p in map(str.strip, parts) if p]
    elif mode == "kss":  # 한국어 문장 분할기
        return [s.strip() for s in kss.split_sentences(text) if s.strip()]
    else:                # ✅ 입력 줄바꿈 그대로(원하시는 동작)
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

# --- 변경 2: generate_subtitle_from_script 시그니처/로직 확장 ---
def generate_subtitle_from_script(
    script_text: str,
    ass_path: str,
    full_audio_file_path: str,
    provider: str = "elevenlabs",
    template: str = "default",
    polly_voice_key: str = "default_male",
    subtitle_lang: str = "ko",
    translate_only_if_english: bool = False,
    tts_lang: str | None = None,
    split_mode: str = "newline",
    strip_trailing_punct_last: bool = True
):
    # 1) 라인 분할
    script_lines = split_script_to_lines(script_text, mode=split_mode)
    if not script_lines:
        return [], None, ass_path

    # 2) 언어-보이스 키 동기화 (Polly 전용)
    if provider == "polly":
        if tts_lang == "en" and polly_voice_key.startswith("korean_"):
            print(f"⚠️ 영어 모드인데 한국어 보이스({polly_voice_key}) 선택됨 → default_male로 교체")
            polly_voice_key = "default_male"
        elif tts_lang == "ko" and polly_voice_key.startswith("default_"):
            print(f"⚠️ 한국어 모드인데 영어 보이스({polly_voice_key}) 선택됨 → korean_female1으로 교체")
            polly_voice_key = "korean_female1"

    # 3) TTS 라인 준비  (★ 라인별로 <speak> 감싸서 Polly에 보냄)
    if provider == "polly":
        tts_lines = []
        for line in script_lines:
            l = (line or "").strip()
            if l.startswith("<speak"):
                safe = l  # 이미 완전 SSML
            elif ("<prosody" in l) or ("<break" in l):
                safe = f"<speak>{l}</speak>"  # SSML 조각 → 래핑
            else:
                # 평문 → 변환(조각; <speak> 제거됨) → 래핑
                try:
                    frag = convert_line_to_ssml(l)
                except Exception:
                    frag = f"<prosody rate='145%' pitch='+2%'>{l}</prosody>"
                safe = f"<speak>{frag}</speak>"
            tts_lines.append(safe)
    else:
        tts_lines = script_lines[:]

    # (선택) TTS 언어 강제 변환
    if tts_lang in ("en", "ko") and provider != "polly":
        tts_lines = _maybe_translate_lines(
            tts_lines,
            target=tts_lang,
            only_if_src_is_english=False
        )

    # 4) 자막 라인 (화면 표시용)
    if subtitle_lang in ("ko", "en"):
        subtitle_lines = _maybe_translate_lines(
            script_lines,
            target=subtitle_lang,
            only_if_src_is_english=translate_only_if_english
        )
    else:
        subtitle_lines = script_lines[:]

    # 5) 라인별 TTS 생성
    audio_paths = generate_tts_per_line(
        tts_lines,
        provider=provider,
        template=template,
        polly_voice_key=polly_voice_key   # ✅ 보정된 보이스 키 반영
    )
    if not audio_paths:
        return [], None, ass_path

    # 6) 병합
    segments_raw = merge_audio_files(audio_paths, full_audio_file_path)
    segments = []
    for i, s in enumerate(segments_raw):
        line_text = subtitle_lines[i] if i < len(subtitle_lines) else script_lines[i]
        segments.append({
            "start": s["start"],
            "end": s["end"],
            "text": line_text,
            "pitch": _assign_pitch(line_text)
        })

    # 7) ASS 생성
    generate_ass_subtitle(
        segments, ass_path, template_name=template,
        strip_trailing_punct_last=strip_trailing_punct_last
    )

    return segments, None, ass_path

# === Auto-paced subtitle densifier (자연스러운 문맥 분할 우선) ===
def _auto_split_for_tempo(text: str, tempo: str = "fast"):
    """
    tempo: fast(짧게) | medium | slow
    분할 우선순위:
    1) 담화 표지(그리고/하지만/그래서/그런데/그러니까/즉/특히/반면에/게다가/또는/혹은 등) '뒤'에서 끊기
    2) 연결 어미(고/지만/는데/면서/라면/면/니까/다가/으며/며 등) '뒤'에서 끊기
    3) 쉼표/세미콜론/중점 등 구두점 뒤에서 끊기
    4) 여전히 길면 공백 근처로 길이 기반 분할
    이후 너무 짧은 조각은 이웃과 병합
    """
    import re

    # 길이 목표(상황 맞게 조절)
    max_len_map = {"fast": 12, "medium": 18, "slow": 24}
    max_len = max_len_map.get(tempo, 18)
    min_piece_chars = 2  # 너무 짧은 조각 병합 기준

    t = (text or "").strip()
    if not t:
        return []

    # 1) 담화 표지 후 분할(토큰은 앞 조각에 둠)
    discourse = r"(그리고|하지만|근데|그런데|그래서|그러니까|즉|특히|게다가|한편|반면에|또는|혹은|다만)"
    t = re.sub(rf"\b{discourse}\b\s*", r"\g<0>§", t)

    # 2) 연결 어미 후 분할(어미는 앞 조각에 둠)
    eomi = r"(고|지만|는데요?|면서|며|라면|면|니까|다가|으며|거나|든지)"
    t = re.sub(rf"({eomi})(?=\s|\Z)", r"\1§", t)

    # 3) 쉼표·세미콜론·중점 뒤 분할 (구두점은 앞 조각에)
    t = re.sub(r"(?<=[,，、;:·])\s*", "§", t)

    # 일차 분할
    parts = [p.strip() for p in t.split("§") if p.strip()]
    chunks = []

    # 4) 길이 보정: 너무 긴 건 공백 근처로 추가 분할
    for p in parts:
        if len(p) <= max_len:
            chunks.append(p)
            continue

        cur = p
        while len(cur) > max_len:
            window = cur[: max_len + 6]  # 여유
            spaces = [m.start() for m in re.finditer(r"\s", window)]
            split_pos = spaces[-1] if spaces else max_len
            chunks.append(cur[:split_pos].strip())
            cur = cur[split_pos:].strip()
        if cur:
            chunks.append(cur)

    # 5) 너무 짧은 조각 병합(양 옆과 자연스러운 공백 처리)
    def _wordish(ch: str) -> bool:
        return ch.isalnum() or ('\uAC00' <= ch <= '\uD7A3')  # 영문/숫자/한글
    i = 1
    while i < len(chunks):
        if len(chunks[i]) < min_piece_chars:
            prev = chunks[i-1].rstrip()
            cur  = chunks[i].lstrip()
            sep = " " if (prev and cur and _wordish(prev[-1]) and _wordish(cur[0])) else ""
            chunks[i-1] = (prev + sep + cur).strip()
            chunks.pop(i)
        else:
            i += 1

    return chunks

def auto_densify_for_subs(
    segments,
    tempo: str = "fast",
    strip_trailing_punct_each: bool = True,
    words_per_piece: int | None = 3,
    min_tail_words: int = 2,
    chunk_strategy: str | None = None,   # ✅ 추가: "period_2or3" 사용
):
    dense = []
    for seg in segments:
        start, end = seg["start"], seg["end"]
        dur = max(0.01, end - start)

        final_pieces = []
        text = (seg.get("text") or "").strip()

        if chunk_strategy == "period_2or3":   # ✅ 새 전략
            # 1) 마침표(.)로 문장 분리
            sentences = _sentence_split_by_dot(text) or [text]

            for sent in sentences:
                tokens = re.findall(r'\S+', sent)
                wc = len(tokens)

                # 2) 문장 길이에 따라 1/2/3 조각 결정(의미 해치지 않게 단어 경계만 사용)
                if wc <= 4:
                    chunks = [" ".join(tokens).strip()]
                elif wc <= 10:
                    chunks = _split_tokens_into_n(tokens, 2)   # 2조각
                else:
                    chunks = _split_tokens_into_n(tokens, 3)   # 3조각

                # 3) 각 조각 꼬리 구두점 제거
                if strip_trailing_punct_each:
                    chunks = [_strip_last_punct_preserve_closers(c) for c in chunks]

                # 4) 맨 끝 조각이 너무 짧으면 앞과 병합(예: '돼' 단독 방지)
                if len(chunks) >= 2 and len(chunks[-1].split()) < 2:
                    chunks[-2] = (chunks[-2] + " " + chunks[-1]).strip()
                    chunks.pop()

                final_pieces.extend(chunks)

        else:
            # 기존 경로(문맥→길이→(옵션)단어개수 기준)
            pieces = _auto_split_for_tempo(text, tempo=tempo)
            if words_per_piece and words_per_piece > 0:
                tmp = []
                for p in pieces:
                    subs = _micro_split_by_words(p, words_per_piece, min_tail_words)
                    tmp.extend(subs if subs else [p.strip()])
                final_pieces = tmp
            else:
                final_pieces = [p.strip() for p in pieces]

            if strip_trailing_punct_each:
                final_pieces = [_strip_last_punct_preserve_closers(x) for x in final_pieces]
        
        final_pieces = _smooth_chunks_by_flow(
            final_pieces,
            target_words=3,
            min_words=2,
            max_words=5
        )
        
        if not final_pieces:
            dense.append(seg)
            continue

        # 시간 배분(문자 길이 비율)
        total_chars = sum(len(x) for x in final_pieces) or 1
        t = start
        for i, txt in enumerate(final_pieces):
            t2 = end if i == len(final_pieces) - 1 else t + dur * (len(txt) / total_chars)
            dense.append({"start": t, "end": t2, "text": txt})
            t = t2

    return dense

def _strip_last_punct_preserve_closers(s: str) -> str:
    # 끝이 [. , ! ? …] 이고 그 뒤에는 공백/닫는 따옴표/괄호만 오는 경우 그 구두점만 제거
    return re.sub(r'([.,!?…])(?=\s*(?:["\'”’)\]\}]|$))', '', s.strip())

# --- helper: 단어 단위 마이크로 분할 ---
def _micro_split_by_words(piece: str, target_words: int = 3, min_tail_words: int = 2):
    # 공백 기준 토큰화(토큰에 붙은 쉼표 등은 그대로 유지 → 중간의 구두점은 살림)
    tokens = re.findall(r'\S+', piece.strip())
    if not tokens:
        return []
    chunks = [" ".join(tokens[i:i+target_words]).strip()
              for i in range(0, len(tokens), target_words)]
    # 마지막 덩어리가 너무 짧으면 앞 덩어리로 합치기
    if len(chunks) >= 2 and len(chunks[-1].split()) < min_tail_words:
        chunks[-2] = (chunks[-2] + " " + chunks[-1]).strip()
        chunks.pop()
    return chunks

def _sentence_split_by_dot(text: str):
    """'.' 뒤에서 문장 분리(공백 무시). 마침표가 없다면 전체를 한 문장으로."""
    if not text or not text.strip():
        return []
    parts = re.split(r'(?<=\.)\s*', text.strip())
    # 빈 조각 제거 + 원문 유지
    return [p.strip() for p in parts if p and p.strip()]

def _split_tokens_into_n(tokens, n, prefer_punct=True):
    """
    토큰 리스트를 n개로 균형 있게 자름.
    prefer_punct=True면 경계 근처에서 쉼표/세미콜론 등 뒤를 우선 경계로 선택.
    """
    if n <= 1 or len(tokens) <= n:
        return [" ".join(tokens).strip()]

    desired = [round(len(tokens) * i / n) for i in range(1, n)]
    boundaries = []
    for idx in desired:
        # 자르기 좋은 근처 후보 인덱스(토큰 사이 경계)
        cand = list(range(max(1, idx - 2), min(len(tokens) - 1, idx + 2) + 1))
        pick = None
        if prefer_punct:
            for j in cand:
                if re.search(r'[,:;·…]$', tokens[j - 1]):
                    pick = j
                    break
        if pick is None:
            pick = min(cand, key=lambda j: abs(j - idx)) if cand else idx
        # 단조 증가 보장
        if boundaries and pick <= boundaries[-1]:
            pick = boundaries[-1] + 1
        pick = min(max(1, pick), len(tokens) - 1)
        boundaries.append(pick)

    # 경계로 분할
    out = []
    start = 0
    for b in boundaries + [len(tokens)]:
        out.append(" ".join(tokens[start:b]).strip())
        start = b
    return [x for x in out if x]


def _smooth_chunks_by_flow(pieces, target_words=3, min_words=2, max_words=5):
    """
    pieces: 문자열 리스트(이미 조각난 자막)
    - 1단어/너무짧은 조각은 앞/뒤와 합침
    - 담화표지(그리고/하지만/근데/그런데/그러니까/또/또한/게다가/한편/반면에/즉)는 뒤 조각에 붙이는 걸 우선
    - 너무 길어진 조각은 단어 경계 + 구두점 뒤를 선호해 다시 나눔
    """
    discourse_heads = {"그리고","하지만","근데","그런데","그러니까","또","또한","게다가","한편","반면에","즉"}

    # 1) 토큰화
    toks = [re.findall(r"\S+", p.strip()) for p in pieces if p.strip()]
    if not toks:
        return []

    # 2) 1단어/짧은 조각 병합
    i = 0
    while i < len(toks):
        wc = len(toks[i])
        if wc >= min_words or len(toks) == 1:
            i += 1
            continue

        first_tok = toks[i][0] if toks[i] else ""
        # 담화표지만 단독이면 다음과 합치기 우선
        if first_tok in discourse_heads and i + 1 < len(toks):
            toks[i + 1] = toks[i] + toks[i + 1]
            toks.pop(i)
            continue

        # 그 외: 앞 조각이 목표보다 짧으면 앞과 합치기, 아니면 뒤와 합치기
        prev_ok = (i > 0 and len(toks[i - 1]) < target_words)
        if prev_ok:
            toks[i - 1] = toks[i - 1] + toks[i]
            toks.pop(i)
        elif i + 1 < len(toks):
            toks[i] = toks[i] + toks[i + 1]
            toks.pop(i + 1)
        else:
            i += 1  # 마지막 하나 남은 예외
    # 3) 너무 긴 조각은 자연스럽게 재분할(구두점 선호)
    refined = []
    for tt in toks:
        wc = len(tt)
        if wc > max_words:
            n = max(2, round(wc / target_words))
            refined.extend(_split_tokens_into_n(tt, n, prefer_punct=True))
        else:
            refined.append(" ".join(tt).strip())

    # 4) 각 조각 끝의 꼬리 구두점 정리(따옴표/괄호 보존)
    refined = [_strip_last_punct_preserve_closers(x) for x in refined if x.strip()]
    return refined