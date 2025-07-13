import os
import json
from aeneas.executetask import ExecuteTask
from aeneas.language import Language
from aeneas.logger import Logger
from aeneas.mtae import AudioFile, TextFile
from aeneas.syncmap import SyncMapFormat

def transcribe_audio_with_timestamps(audio_file_path: str, script_text: str) -> list:
    """
    Aeneas를 사용하여 오디오 파일과 주어진 스크립트 텍스트를 동기화하고,
    각 텍스트 세그먼트의 시작 및 종료 타임스탬프를 반환합니다.

    Args:
        audio_file_path (str): 오디오 파일의 경로.
        script_text (str): 오디오와 동기화할 전체 스크립트 텍스트.
                           각 줄이 하나의 세그먼트로 간주됩니다.

    Returns:
        list: 각 세그먼트의 시작 시간, 종료 시간, 텍스트를 포함하는 딕셔너리 리스트.
              예: [{'start': 0.0, 'end': 2.5, 'text': '안녕하세요'}, ...]
    """
    logger = Logger(Logger.INFO) # Aeneas 로거 설정 (디버깅용)

    # Aeneas는 텍스트 파일을 입력으로 받으므로 임시 파일을 생성합니다.
    temp_text_file_path = "temp_aeneas_script.txt"
    # 스크립트 텍스트를 줄바꿈 기준으로 분리하여 Aeneas에 전달하면,
    # 각 줄을 하나의 동기화 단위로 간주할 가능성이 높습니다.
    # LLM이 "한 줄에 한 세그먼트"로 출력하도록 지시했으므로 이 방식이 적합합니다.
    with open(temp_text_file_path, "w", encoding="utf-8") as f:
        f.write(script_text)

    # Aeneas 태스크 설정
    # task_language: 언어 코드 (한국어는 'kor')
    # os_task_file_format: 출력 형식 (json)
    # is_text_type: 텍스트 타입 (plain)
    config_string = u"task_language=kor|os_task_file_format=json|is_text_type=plain"

    try:
        # Aeneas 태스크 실행
        task = ExecuteTask(
            logger=logger,
            config_string=config_string,
            audio_file_path=audio_file_path,
            text_file_path=temp_text_file_path
        )
        
        task.execute()

        segments = []
        if task.sync_map:
            # Aeneas의 결과는 task.sync_map.fragments에 저장됩니다.
            for fragment in task.sync_map.fragments:
                segments.append({
                    "start": float(fragment.begin),
                    "end": float(fragment.end),
                    "text": fragment.text.strip()
                })
        
        return segments

    except Exception as e:
        logger.error(f"Aeneas 동기화 중 오류 발생: {e}")
        # 오류 발생 시 빈 리스트 또는 오류 메시지 반환
        return []
    finally:
        # 임시 파일 삭제
        if os.path.exists(temp_text_file_path):
            os.remove(temp_text_file_path)

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


def generate_ass_subtitle(segments: list, template_name: str = "default") -> str:
    """
    주어진 세그먼트와 템플릿을 사용하여 ASS 자막 파일을 생성합니다.
    """
    templates = {
        "default": """
[Script Info]
PlayResX: 1280
PlayResY: 720
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,20,1
Style: Highlight,Arial,48,&H0000FFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""",
        "karaoke_style": """
[Script Info]
PlayResX: 1280
PlayResY: 720
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,52,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,2,2,10,10,20,1
Style: Highlight,Arial,52,&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,2,2,10,10,20,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    }

    ass_content = templates.get(template_name, templates["default"])

    for segment in segments:
        start_time = segment['start']
        end_time = segment['end']
        text = segment['text']

        # ASS 시간 형식 변환 (HH:MM:SS.cs)
        def format_time(seconds):
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            cs = int((seconds * 100) % 100)
            return f"{hours:01d}:{minutes:02d}:{secs:02d}.{cs:02d}"

        formatted_start = format_time(start_time)
        formatted_end = format_time(end_time)

        # 텍스트에 줄바꿈이 있다면 ASS 형식에 맞게 처리
        processed_text = text.replace('\n', '\\N')

        ass_content += f"Dialogue: 0,{formatted_start},{formatted_end},Default,,0,0,0,,{processed_text}\n"

    return ass_content

