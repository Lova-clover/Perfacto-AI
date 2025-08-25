from deep_translator import GoogleTranslator
import re

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

def generate_tts_per_line(script_lines, provider, template, polly_voice_key="korean_female1"):
    audio_paths = []
    temp_audio_dir = "temp_line_audios"
    os.makedirs(temp_audio_dir, exist_ok=True)

    print(f"디버그: 총 {len(script_lines)}개의 스크립트 라인에 대해 TTS 생성 시도.")

    for i, line in enumerate(script_lines):
        line_audio_path = os.path.join(temp_audio_dir, f"line_{i}.mp3")
        try:
            generate_tts(
                text=line,
                save_path=line_audio_path,
                provider=provider,
                template_name=template
            )
            audio_paths.append(line_audio_path)
            print(f"디버그: 라인 {i+1} ('{line[:30]}...') TTS 생성 성공. 파일: {line_audio_path}")
        except Exception as e:
            print(f"오류: 라인 {i+1} ('{line[:30]}...') TTS 생성 실패: {e}")
            continue
            
    print(f"디버그: 최종 생성된 오디오 파일 경로 수: {len(audio_paths)}")
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


def generate_ass_subtitle(segments, ass_path, template_name="default",
                          strip_trailing_punct_last=True):
    settings = SUBTITLE_TEMPLATES.get(template_name, SUBTITLE_TEMPLATES["default"])

    def _escape_ass_text(s: str) -> str:
        # ASS에서 개행은 \N, 역슬래시는 이스케이프, 중괄호는 태그로 오인될 수 있음
        s = s.replace("\\", r"\\")
        s = s.replace("\r", "")
        s = s.replace("\n", r"\N")
        # 필요시 특수문자 추가 이스케이프 가능
        return s

    with open(ass_path, "w", encoding="utf-8") as f:
        # 헤더
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n\n")

        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Bottom,{settings['Fontname']},{settings['Fontsize']},{settings['PrimaryColour']},{settings['OutlineColour']},1,{settings['Outline']},0,2,10,10,{settings['MarginV']},1\n\n")

        # 이벤트(여기서 포맷과 Dialogue 필드 개수를 반드시 일치시켜야 함)
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        for i, seg in enumerate(segments):
            start, end = seg['start'], seg['end']
            text = (seg.get('text') or "").strip()

            if strip_trailing_punct_last and i == len(segments) - 1:
                # 마지막 자막 꼬리 구두점 제거 (옵션)
                text = re.sub(r'[\s　]*[,.!?…~·]+$', '', text)

            # ASS 안전 이스케이프 + 줄바꿈 변환
            text = _escape_ass_text(text)

            start_ts = format_ass_timestamp(start)
            end_ts   = format_ass_timestamp(end)

            # 🔴 핵심: Name, Effect 컬럼을 비워두더라도 "자리"는 채워야 함
            # Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            # 예:     0,     0:00:00.00,0:00:02.10,Bottom, ,0,0,0, ,여기가텍스트
            f.write(f"Dialogue: 0,{start_ts},{end_ts},Bottom,,0,0,0,,{text}\n")


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
    polly_voice_key: str = "korean_female",
    subtitle_lang: str = "ko",
    translate_only_if_english: bool = False,
    tts_lang: str | None = None,
    split_mode: str = "newline",          # ✅ 새 파라미터
    strip_trailing_punct_last: bool = True
):
    # 1) 라인 분할
    script_lines = split_script_to_lines(script_text, mode=split_mode) 

    if not script_lines:
        return [], None, ass_path

    # 2) TTS 라인: 원문을 유지하되, tts_lang 지정 시 라인 단위 번역(개수 보존)
    tts_lines = script_lines[:]
    if tts_lang in ("en", "ko"):
        tts_lines = _maybe_translate_lines(
            script_lines,
            target=tts_lang,
            only_if_src_is_english=False
        )

    # 3) 자막 라인: 요청 언어에 따라 선택(ko면 그대로 두면 원문과 100% 동일)
    target = None
    if subtitle_lang == "ko":
        target = "ko"
    elif subtitle_lang == "en":
        target = "en"

    subtitle_lines = (
        _maybe_translate_lines(
            script_lines, target=target,
            only_if_src_is_english=translate_only_if_english
        ) if target is not None else script_lines
    )

    # 4) 라인별 TTS 생성 및 병합
    audio_paths = generate_tts_per_line(tts_lines, provider=provider, template=template)
    if not audio_paths:
        return [], None, ass_path

    segments_raw = merge_audio_files(audio_paths, full_audio_file_path)
    segments = []
    for i, s in enumerate(segments_raw):
        line_text = subtitle_lines[i] if i < len(subtitle_lines) else tts_lines[i]
        segments.append({"start": s["start"], "end": s["end"], "text": line_text})

    # 5) ASS 생성 (마지막 자막 구두점 제거 옵션 전달)
    generate_ass_subtitle(segments, ass_path, template_name=template,
                          strip_trailing_punct_last=strip_trailing_punct_last)
    return segments, None, ass_path

# === Auto-paced subtitle densifier (쉼표·세미콜론 우선, 길이면 보정) ===
def _auto_split_for_tempo(text: str, tempo: str = "fast"):
    """
    tempo: fast(짧게) | medium | slow
    - 1차: 쉼표/세미콜론/중점 등에서 우선 분할 (구두점은 앞 조각에 남김)
    - 2차: 너무 길면 공백 근처로 잘라내기 (한국어 공백 기준, 없으면 길이로 강제 절단)
    """
    import re
    max_len_map = {"fast": 12, "medium": 18, "slow": 24}
    max_len = max_len_map.get(tempo, 16)

    # 1차: 부드러운 분할(쉼표류, ; : · 등)
    parts = re.split(r'(?<=[,，、;:·])\s*', (text or "").strip())
    parts = [p for p in parts if p]

    chunks = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(p) <= max_len:
            chunks.append(p)
            continue

        # 2차: 길면 공백 근처로 분절(가까운 공백 찾기, 없으면 강제)
        cur = p
        while len(cur) > max_len:
            window = cur[: max_len + 4]  # 살짝 여유
            # 가장 오른쪽 공백 위치(가능하면 단어 경계에서 끊기)
            spaces = [m.start() for m in re.finditer(r'\s', window)]
            split_pos = spaces[-1] if spaces else max_len
            chunks.append(cur[:split_pos].strip())
            cur = cur[split_pos:].strip()
        if cur:
            chunks.append(cur)
    return chunks


def auto_densify_for_subs(segments, tempo: str = "fast"):
    """
    각 원 세그먼트(한 줄)를 tempo에 맞춰 여러 하위 자막 이벤트로 쪼개되,
    오디오/영상 타이밍은 유지(문자 길이 비율로 시간 배분).
    """
    dense = []
    for seg in segments:
        start, end = seg["start"], seg["end"]
        dur = max(0.01, end - start)
        pieces = _auto_split_for_tempo(seg.get("text", ""), tempo=tempo)
        if not pieces:
            dense.append(seg)
            continue
        total_chars = sum(len(x) for x in pieces) or 1
        t = start
        for i, txt in enumerate(pieces):
            if i == len(pieces) - 1:
                t2 = end  # 마지막은 끝까지
            else:
                t2 = t + dur * (len(txt) / total_chars)
            dense.append({"start": t, "end": t2, "text": txt})
            t = t2
    return dense
