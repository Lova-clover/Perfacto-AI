from faster_whisper import WhisperModel
import copy

def transcribe_audio_with_timestamps(audio_path):
    model = WhisperModel("medium", device="cpu")
    segments, info = model.transcribe(audio_path, beam_size=15, language="ko", word_timestamps=True)
    
    # segments는 리스트 형태
    return list(segments)

SUBTITLE_TEMPLATES = {
    "educational": {
        "Fontname": "Noto Sans CJK KR",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "entertainer": {
        "Fontname": "Noto Sans CJK KR",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "slow": {
        "Fontname": "Noto Sans CJK KR",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "default": {
        "Fontname": "Noto Sans CJK KR",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "korean_male": {
        "Fontname": "Noto Sans CJK KR",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "korean_male2": {
        "Fontname": "Noto Sans CJK KR",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "korean_female": {
        "Fontname": "Noto Sans CJK KR",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    },
    "korean_female2": {
        "Fontname": "Noto Sans CJK KR",
        "Fontsize": 12,
        "PrimaryColour": "&H00FFFFFF",       # 흰색 텍스트
        "OutlineColour": "&H00000000",       # 검정 외곽선
        "Outline": 2,
        "Alignment": 2,
        "MarginV": 40
    }
}


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
            start = seg.start
            # 다음 세그먼트가 있으면, 그 시작 시점 바로 이전까지 자막 표시
            if i + 1 < len(segments):
                next_start = segments[i + 1].start
                end = next_start
            else:
                end = seg.end

            text = seg.text.strip().replace("\n", " ")
            start_ts = format_ass_timestamp(start)
            end_ts = format_ass_timestamp(end)

            f.write(f"Dialogue: 0,{start_ts},{end_ts},Bottom,,0,0,0,,{text}\n")




def format_ass_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h:01}:{m:02}:{s:02}.{cs:02}"

