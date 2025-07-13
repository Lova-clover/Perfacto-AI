# generate_timed_segments.py
import os
import re
from elevenlabs_tts import generate_tts
from pydub import AudioSegment

def split_script_to_lines(script_text):
    lines = re.split(r'(?<=[.!?])\\s+', script_text.strip())
    return [line.strip() for line in lines if line.strip()]

def generate_tts_per_line(script_lines, audio_dir="assets/audio", provider="elevenlabs", template="korean_male"):

    os.makedirs(audio_dir, exist_ok=True)
    audio_paths = []
    for i, line in enumerate(script_lines):
        audio_path = os.path.join(audio_dir, f"line_{i}.mp3")
        generate_tts(
            text=line,
            save_path=audio_path,
            provider=provider,
            template_name=template
        )
        audio_paths.append(audio_path)
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

def generate_subtitle_from_script(script_text, ass_path="assets/generated_subtitle.ass",
                                 provider="elevenlabs", template="korean_male"):

    script_lines = split_script_to_lines(script_text)
    audio_paths = generate_tts_per_line(script_lines, provider=provider, template=template)
    segments = get_segments_from_audio(audio_paths, script_lines)
    generate_ass_subtitle(segments=segments, ass_path=ass_path, template_name=template)
    return segments, audio_paths, ass_path
