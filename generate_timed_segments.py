# generate_timed_segments.py
import os
import re
from elevenlabs_tts import generate_tts
from pydub import AudioSegment

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

def split_script_to_lines(script_text):
    lines = re.split(r'(?<=[.!?])\\s+', script_text.strip())
    return [line.strip() for line in lines if line.strip()]

def generate_tts_per_line(script_lines, provider, template):
    audio_paths = []
    temp_audio_dir = "temp_line_audios"
    os.makedirs(temp_audio_dir, exist_ok=True)

    print(f"디버그: 총 {len(script_lines)}개의 스크립트 라인에 대해 TTS 생성 시도.") # 추가

    for i, line in enumerate(script_lines):
        line_audio_path = os.path.join(temp_audio_dir, f"line_{i}.mp3")
        try:
            # generate_tts 함수는 elevenlabs_tts.py에 정의되어 있습니다.
            generate_tts(
                text=line,
                save_path=line_audio_path,
                provider=provider,
                template_name=template # ElevenLabs의 경우, Polly는 polly_voice_name_key 사용
            )
            audio_paths.append(line_audio_path)
            print(f"디버그: 라인 {i+1} ('{line[:30]}...') TTS 생성 성공. 파일: {line_audio_path}") # 추가
        except Exception as e:
            # TTS 생성 실패 시 구체적인 오류 메시지 출력
            print(f"오류: 라인 {i+1} ('{line[:30]}...') TTS 생성 실패: {e}") # 수정
            # 실패한 라인에 대해 오디오 경로를 추가하지 않아 segments 길이가 줄어들 수 있습니다.
            # 모든 라인에 대해 TTS 생성이 성공해야 합니다.
            continue # 다음 라인으로 건너뜝니다.
            
    print(f"디버그: 최종 생성된 오디오 파일 경로 수: {len(audio_paths)}") # 추가
    return audio_paths

def get_segments_from_audio(audio_paths, script_lines):
    segments = []
    current_time = 0.0
    for line, path in zip(script_lines, audio_paths):
        audio = AudioSegment.from_file(path)
        duration = audio.duration_seconds
        segments.append({
            "start": current_time,
            "end": current_time + duration,
            "text": line
        })
        current_time += duration
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
            # seg가 딕셔너리 또는 객체일 수 있으므로, 안전하게 접근하도록 수정
            # 딕셔너리 형태일 경우 seg['start'], 객체 형태일 경우 seg.start
            # faster_whisper segments는 객체이고, 수동 생성 segments는 딕셔너리이므로
            # 여기서는 딕셔너리 키로 접근하도록 통일합니다.
            start = seg['start']
            # 다음 세그먼트가 있으면, 그 시작 시점 바로 이전까지 자막 표시
            if i + 1 < len(segments):
                next_start = segments[i + 1]['start']
                end = next_start
            else:
                end = seg['end'] # 마지막 세그먼트의 끝 시간

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
    script_text,
    ass_path,
    provider="elevenlabs",
    template="default", # ElevenLabs 템플릿 이름
    polly_voice_key="korean_female" # Polly 음성 키 (generate_tts_per_line으로 전달)
):
    print(f"디버그: 자막 생성을 위한 스크립트 라인 분리 중...") # 추가
    script_lines = split_script_to_lines(script_text)
    print(f"디버그: 분리된 스크립트 라인 수: {len(script_lines)}") # 추가

    if not script_lines:
        print("경고: 스크립트 라인이 생성되지 않았습니다. 빈 segments 반환.")
        return [], [], ass_path

    # generate_tts_per_line 호출 시 polly_voice_key를 정확히 전달해야 합니다.
    # 현재 코드에서는 template_name에 polly_voice_key가 들어갈 수 있으므로, 해당 부분을 확인하세요.
    # 만약 generate_tts_per_line에서 Polly 음성 키를 제대로 사용하지 않는다면 문제가 될 수 있습니다.
    
    # generate_tts_per_line 함수 호출 시 polly_voice_name_key 매개변수 추가 (elevenlabs_tts.py의 generate_tts 함수 시그니처 확인 필요)
    # 현재 generate_tts_per_line은 template 매개변수를 사용하고 있습니다.
    # generate_tts_per_line 함수가 polly_voice_name_key를 template_name으로 전달하고 있을 것입니다.
    # elevenlabs_tts.py의 generate_tts 함수 정의에 따라 달라집니다.
    
    # 아래 호출 부분이 올바른지 다시 확인 필요
    audio_paths = generate_tts_per_line(script_lines, provider=provider, template=template) # template에 Polly voice key가 들어가는 경우
    # 또는 명시적으로 Polly 키를 넘기는 경우 (만약 generate_tts_per_line 시그니처가 변경된다면)
    # audio_paths = generate_tts_per_line(script_lines, provider=provider, polly_voice_name_key=polly_voice_key)


    if not audio_paths:
        print("오류: 라인별 오디오 파일이 생성되지 않았습니다. 빈 segments 반환.")
        return [], [], ass_path

    segments = get_segments_from_audio(audio_paths, script_lines)
    print(f"디버그: get_segments_from_audio 후 최종 segments의 길이: {len(segments)}") # 추가