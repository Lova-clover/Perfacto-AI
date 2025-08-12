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

def split_script_to_lines(script_text):
    return [sent.strip() for sent in kss.split_sentences(script_text) if sent.strip()]

def generate_tts_per_line(script_lines, provider, template):
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


def generate_ass_subtitle(segments, ass_path, template_name="default"):
    settings = SUBTITLE_TEMPLATES.get(template_name, SUBTITLE_TEMPLATES["default"])

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n\n")

        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Bottom,{settings['Fontname']},{settings['Fontsize']},{settings['PrimaryColour']},{settings['OutlineColour']},1,{settings['Outline']},0,2,10,10,{settings['MarginV']},1\n\n")

        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        for i, seg in enumerate(segments):
            start = seg['start']
            # 변경: 다음 세그먼트 시작 대신 현재 세그먼트의 실제 끝 시간을 사용
            end = seg['end']

            text = seg['text'].strip().replace("\\n", " ")

            # 시간 형식 변환
            start_ts = format_ass_timestamp(start)
            end_ts = format_ass_timestamp(end)

            # Dialogue: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            f.write(f"Dialogue: 0,{start_ts},{end_ts},Bottom,,0,0,0,,{text}\n")

def format_ass_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h:01}:{m:02}:{s:02}.{cs:02}"


def generate_subtitle_from_script(
    script_text: str,
    ass_path: str,
    full_audio_file_path: str,
    provider: str = "elevenlabs",
    template: str = "default",
    polly_voice_key: str = "korean_female",
    # ▼ 새로 추가: 자막 언어 컨트롤
    subtitle_lang: str = "ko",             # "auto" | "ko" | "en"
    translate_only_if_english: bool = False   # True면 "원문이 영어일 때만 ko로 번역"
    # 현재는 한국어자막만 사용할 것이기 때문에 False
):
    print(f"디버그: 자막 생성을 위한 스크립트 라인 분리 중...")
    script_lines = split_script_to_lines(script_text)
    print(f"디버그: 분리된 스크립트 라인 수: {len(script_lines)}")

    if not script_lines:
        print("경고: 스크립트 라인이 생성되지 않았습니다. 빈 segments 반환.")
        return [], None, ass_path

    # 1) TTS는 항상 원문으로 (영어 음성 유지 목적)
    tts_lines = script_lines[:]

    # 2) 자막 텍스트만 선택적으로 번역
    target = None
    if subtitle_lang == "ko":
        target = "ko"
    elif subtitle_lang == "en":
        target = "en"
    # "auto"면 target=None → 번역 안함 (원문 그대로)

    subtitle_lines = (
        _maybe_translate_lines(
            script_lines,
            target=target,
            only_if_src_is_english=translate_only_if_english
        )
        if target is not None else script_lines
    )

    # 3) 라인별 TTS (원문 기준)
    audio_paths = generate_tts_per_line(tts_lines, provider=provider, template=template)
    if not audio_paths:
        print("오류: 라인별 오디오 파일이 생성되지 않았습니다. 빈 segments 반환.")
        return [], None, ass_path

    # 4) 병합 및 타이밍
    segments_raw = merge_audio_files(audio_paths, full_audio_file_path)
    segments = []
    for i, s in enumerate(segments_raw):
        # 자막 문장은 번역된 문장(또는 원문) 사용
        line_text = subtitle_lines[i] if i < len(subtitle_lines) else tts_lines[i]
        segments.append({"start": s["start"], "end": s["end"], "text": line_text})

    if not segments:
        print("오류: 세그먼트 생성에 실패했습니다. 빈 segments 반환.")
        return [], None, ass_path

    # 5) MoviePy 전체 오디오 로드(변경 없음)
    audio_clips = None
    if os.path.exists(full_audio_file_path):
        try:
            audio_clips = AudioFileClip(full_audio_file_path)
            print(f"디버그: 전체 오디오 파일 '{full_audio_file_path}' 로드 성공.")
        except Exception as e:
            print(f"오류: 전체 오디오 파일 로드 실패: {e}")
    else:
        print(f"경고: 전체 오디오 파일 '{full_audio_file_path}' 없음.")

    # 6) ASS 생성 (변경 없음)
    generate_ass_subtitle(segments, ass_path, template_name=template)
    return segments, audio_clips, ass_path