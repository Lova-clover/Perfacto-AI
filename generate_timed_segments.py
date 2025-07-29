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

<<<<<<< HEAD
def split_script_to_lines(script_text):
    return [sent.strip() for sent in kss.split_sentences(script_text) if sent.strip()]
=======
def split_script_to_lines(script_text, min_length=15, max_length=35):
    import kss
    import re

    # 1차: KSS로 문장 분리
    kss_sentences = kss.split_sentences(script_text)
    processed_lines = []

    for sent in kss_sentences:
        sent = sent.strip()

        # 아주 짧은 문장은 그대로 사용
        if len(sent) <= max_length:
            processed_lines.append(sent)
            continue

        # 2차: 쉼표나 접속사 기준으로 나눔
        temp_chunks = re.split(r"(,| 그리고 | 그래서 | 하지만 | 또한 )", sent)
        temp = ""
        for part in temp_chunks:
            temp += part
            if len(temp.strip()) >= max_length or part in [",", " 그리고 ", " 그래서 ", " 하지만 ", " 또한 "]:
                processed_lines.append(temp.strip())
                temp = ""
        if temp.strip():
            processed_lines.append(temp.strip())

    # 3차: 여전히 긴 문장이 있다면 조사 기준으로만 한 번 더 분할
    final_lines = []
    for line in processed_lines:
        if len(line) <= max_length:
            final_lines.append(line)
        else:
            # 조사 기준으로만 한 번 더 자르기
            sub_chunks = re.split(r"(은 |는 |을 |를 |이 |가 |에 |도 |으로 |부터 |까지 |에서 )", line)
            temp = ''
            for part in sub_chunks:
                temp += part
                if len(temp) >= min_length:
                    final_lines.append(temp.strip())
                    temp = ''
            if temp.strip():
                final_lines.append(temp.strip())

    # 빈 줄 제거
    return [l.strip() for l in final_lines if l.strip()]
>>>>>>> 87e8cb4 (대사분할증가)

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
    full_audio_file_path: str, # <-- 새로 추가된 인자
    provider: str = "elevenlabs",
    template: str = "default",
    polly_voice_key: str = "korean_female"
):
    print(f"디버그: 자막 생성을 위한 스크립트 라인 분리 중...")
    script_lines = split_script_to_lines(script_text)
    print(f"디버그: 분리된 스크립트 라인 수: {len(script_lines)}")

    if not script_lines:
        print("경고: 스크립트 라인이 생성되지 않았습니다. 빈 segments 반환.")
        return [], None, ass_path # audio_clips가 None인 경우를 명시적으로 반환

    audio_paths = generate_tts_per_line(script_lines, provider=provider, template=template)

    if not audio_paths:
        print("오류: 라인별 오디오 파일이 생성되지 않았습니다. 빈 segments 반환.")
        return [], None, ass_path # audio_clips가 None인 경우를 명시적으로 반환

    segments_raw = merge_audio_files(audio_paths, full_audio_file_path)
    segments = []
    for i, s in enumerate(segments_raw):
        segments.append({
            "start": s["start"],
            "end": s["end"],
            "text": script_lines[i]  # 기존대로 자막 문장 포함
        })

    print(f"디버그: get_segments_from_audio 후 최종 segments의 길이: {len(segments)}")

    if not segments:
        print("오류: 세그먼트 생성에 실패했습니다. 빈 segments 반환.")
        return [], None, ass_path # audio_clips가 None인 경우를 명시적으로 반환

    # === 새로 추가되거나 수정된 부분: MoviePy AudioFileClip 생성 ===
    audio_clips = None # 일단 None으로 초기화
    if os.path.exists(full_audio_file_path):
        try:
            # main.py에서 생성된 전체 오디오 파일을 MoviePy AudioFileClip으로 로드
            audio_clips = AudioFileClip(full_audio_file_path)
            print(f"디버그: 전체 오디오 파일 '{full_audio_file_path}' MoviePy AudioFileClip으로 로드 성공.")
        except Exception as e:
            print(f"오류: 전체 오디오 파일 '{full_audio_file_path}' 로드 실패: {e}")
            # 로드 실패 시 audio_clips는 None으로 유지됨
    else:
        print(f"경고: 전체 오디오 파일 '{full_audio_file_path}'을 찾을 수 없습니다. audio_clips는 None입니다.")


    # ASS 파일 생성
    generate_ass_subtitle(segments, ass_path, template_name=template)
    
    # 세그먼트, 오디오 클립, ASS 경로를 모두 반환
    return segments, audio_clips, ass_path