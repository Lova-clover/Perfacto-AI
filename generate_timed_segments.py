# generate_timed_segments.py
import os
import re
from elevenlabs_tts import generate_tts
from pydub import AudioSegment
from whisper_asr import generate_ass_subtitle

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

def generate_subtitle_from_script(script_text, ass_path="assets/generated_subtitle.ass",
                                 provider="elevenlabs", template="korean_male"):

    script_lines = split_script_to_lines(script_text)
    audio_paths = generate_tts_per_line(script_lines, provider=provider, template=template)
    segments = get_segments_from_audio(audio_paths, script_lines)
    generate_ass_subtitle(segments=segments, ass_path=ass_path, template_name=template)
    return segments, audio_paths, ass_path
