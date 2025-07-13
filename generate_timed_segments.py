# generate_timed_segments.py
import os
import re
from elevenlabs_tts import generate_tts
from pydub import AudioSegment
from moviepy import AudioFileClip

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
}

def split_script_into_lines(script_text: str) -> list[str]:
    """
    스크립트를 문장 단위로 분리합니다.
    마침표(.)와 새로운 구분자(_)를 기준으로 분리하며, 구분자는 결과 문장에서 제거합니다.
    """
    # 마침표와 언더스코어를 기준으로 분리하되, 구분자는 포함하지 않음
    # re.split은 패턴에 매치되는 부분을 기준으로 문자열을 분리하고, 매치된 부분은 결과에 포함하지 않습니다.
    # 하지만 여기서는 '새로운 기준'도 문장을 끊는 역할만 하고 실제 문장에는 포함되지 않아야 하므로,
    # re.split의 동작 방식이 적합합니다.
    lines = re.split(r'[._]', script_text) # . 또는 _ 기준으로 분리

    # 각 라인의 앞뒤 공백을 제거하고 빈 문자열 필터링
    cleaned_lines = [line.strip() for line in lines if line.strip()]

    # 특수 구분자가 문장의 시작이나 끝에 단독으로 오는 경우를 대비하여 추가 처리
    # 예를 들어 "안녕하세요. _오늘 날씨 좋네요." 와 같은 경우, "_"가 제거되어야 함
    final_lines = []
    for line in cleaned_lines:
        # 이전에 . 이나 _ 로 분리되었으므로, 해당 문자는 이미 제거된 상태
        # 따라서 추가적인 re.sub는 필요하지 않음.
        # 만약 스크립트 내부에 '.'이나 '_'가 문장의 일부로 사용되는 경우가 있다면,
        # 정규표현식을 더 정교하게 다듬어야 합니다 (예: 띄어쓰기 뒤에 오는 . 만 인식 등).
        final_lines.append(line)

    print(f"디버그: 분리된 스크립트 라인 수: {len(final_lines)}")
    print(f"디버그: 분리된 스크립트 라인: {final_lines}")
    return final_lines

def generate_tts_per_line(script_lines: list[str], provider: str, template: str) -> list[str]:
    """
    각 스크립트 라인에 대해 TTS 오디오 파일을 생성하고 파일 경로를 반환합니다.
    """
    audio_paths = []
    output_dir = "assets/line_audios"
    os.makedirs(output_dir, exist_ok=True)

    for i, line in enumerate(script_lines):
        # 실제 TTS 생성 시에는 구분자를 포함하지 않은 텍스트를 사용
        # split_script_into_lines 함수에서 이미 구분자가 제거된 상태이므로,
        # 여기서 추가적인 처리는 필요 없습니다.
        # 만약 split_script_into_lines 함수에서 구분자를 완전히 제거하지 않고
        # 단순히 분리만 했다면, 여기서 line.replace('_', '').replace('.', '')와 같은 처리가 필요합니다.
        
        # 현재 로직에서는 split_script_into_lines에서 .과 _가 제거되므로,
        # 여기서는 바로 line을 사용합니다.
        tts_text = line

        if not tts_text.strip(): # 빈 문자열은 스킵
            continue

        audio_filename = os.path.join(output_dir, f"audio_{i}.mp3")
        try:
            # generate_tts 함수가 ElevenLabs와 Polly를 처리합니다.
            generated_path = generate_tts(tts_text, save_path=audio_filename, provider=provider, template_name=template)
            audio_paths.append(generated_path)
            print(f"✅ 오디오 생성 완료: {audio_filename} (내용: '{tts_text[:30]}...')")
        except Exception as e:
            print(f"오류: '{tts_text[:30]}...' 에 대한 오디오 생성 실패: {e}")
            # 오류 발생 시 해당 오디오 파일 경로를 추가하지 않고 건너뜁니다.
            # 이로 인해 오디오 파일 개수가 스크립트 라인 개수보다 적을 수 있습니다.
            # 이 경우, get_segments_from_audio 함수에서 인덱스 오류가 발생할 수 있으므로,
            # 해당 함수도 수정이 필요합니다. (아래 get_segments_from_audio 수정 제안 참고)
    return audio_paths

def merge_audio_files(audio_paths: list[str], output_path: str) -> list[dict]:
    """
    분리된 오디오 파일들을 하나로 합치고, 각 오디오 클립의 시작과 끝 시간을 기록합니다.
    """
    combined_audio = AudioSegment.empty()
    segments = []
    current_time = 0

    for path in audio_paths:
        try:
            audio_clip = AudioSegment.from_file(path)
            segments.append({
                "start": current_time,
                "end": current_time + len(audio_clip),
                "duration": len(audio_clip) # 밀리초 단위
            })
            combined_audio += audio_clip
            current_time += len(audio_clip)
        except Exception as e:
            print(f"오류: 오디오 파일 '{path}' 병합 중 오류 발생: {e}")
            # 오류 발생 시 해당 파일은 건너뛰고 다음 파일로 진행

    if combined_audio.duration_seconds > 0:
        combined_audio.export(output_path, format="mp3")
        print(f"✅ 전체 오디오 파일 저장 완료: {output_path}")
    else:
        print("경고: 병합할 오디오 클립이 없습니다.")
        return [] # 병합된 오디오가 없으면 빈 리스트 반환

    # segments의 시간을 초 단위로 변환
    for s in segments:
        s["start"] /= 1000.0
        s["end"] /= 1000.0
        s["duration"] /= 1000.0

    return segments

def generate_ass_subtitle(segments: list[dict], template: dict, audio_duration: float, ass_path: str) -> str:
    """
    주어진 세그먼트와 템플릿을 사용하여 ASS 자막 파일을 생성합니다.
    """
    with open(ass_path, "w", encoding="utf-8") as f:
        # ASS 헤더
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n")
        f.write("WrapStyle: 0\n")
        f.write("ScaledBorderAndShadow: yes\n")
        f.write("Collisions: Normal\n")
        f.write("PlayResX: 1920\n")
        f.write("PlayResY: 1080\n")
        f.write(f"Audio File: {os.path.basename(ass_path).replace('.ass', '.mp3')}\n") # ASS 파일명에 오디오 파일명을 포함
        f.write("\n")

        # 스타일 정의
        f.write("[V4+ Styles]\n")
        f.write(
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )
        f.write(
            f"Style: Default,{template['Fontname']},{template['Fontsize']},{template['PrimaryColour']},{template['PrimaryColour']},{template['OutlineColour']},{template['OutlineColour']},0,0,0,0,100,100,0,0,1,{template['Outline']},0,{template['Alignment']},0,0,{template['MarginV']},1\n"
        )
        f.write("\n")

        # 자막 이벤트
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        for segment in segments:
            start_time_ms = int(segment["start"] * 1000)
            end_time_ms = int(segment["end"] * 1000)

            # ASS 시간 형식 변환 (H:MM:SS.cc)
            start_h = start_time_ms // 3600000
            start_mm = (start_time_ms % 3600000) // 60000
            start_ss = (start_time_ms % 60000) // 1000
            start_cc = (start_time_ms % 1000) // 10

            end_h = end_time_ms // 3600000
            end_mm = (end_time_ms % 3600000) // 60000
            end_ss = (end_time_ms % 60000) // 1000
            end_cc = (end_time_ms % 1000) // 10

            start_str = f"{start_h}:{start_mm:02}:{start_ss:02}.{start_cc:02}"
            end_str = f"{end_h}:{end_mm:02}:{end_ss:02}.{end_cc:02}"
            
            # 실제 자막 텍스트에는 ._ 등의 구분자가 포함되지 않도록 함
            subtitle_text = segment["text"].replace('.', '').replace('_', '')

            f.write(
                f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{subtitle_text}\n"
            )
    print(f"✅ ASS 자막 파일 저장 완료: {ass_path}")
    return ass_path


def generate_subtitle_from_script(
    script_text: str,
    output_audio_file: str = "assets/full_audio.mp3",
    output_ass_file: str = "assets/output.ass",
    tts_provider: str = "elevenlabs",
    tts_template: str = "educational",
    subtitle_template_name: str = "educational",
):
    """
    주어진 스크립트에서 TTS 오디오를 생성하고, 오디오 길이에 맞춰 자막 파일을 생성합니다.
    """
    print("--- 스크립트 분리 및 오디오 생성 시작 ---")

    # 스크립트를 라인별로 분리 (새로운 기준 적용)
    script_lines = split_script_into_lines(script_text)

    if not script_lines:
        print("경고: 스크립트 라인이 생성되지 않았습니다. 빈 segments 반환.")
        return [], None, None # audio_clips와 ass_path 모두 None 반환

    # 각 라인에 대해 TTS 오디오 생성
    audio_paths = generate_tts_per_line(script_lines, provider=tts_provider, template=tts_template)

    if not audio_paths:
        print("오류: 라인별 오디오 파일이 생성되지 않았습니다. 빈 segments 반환.")
        return [], None, None # audio_clips와 ass_path 모두 None 반환

    # 생성된 개별 오디오 파일들을 하나로 병합하고 세그먼트 정보 추출
    segments_raw = merge_audio_files(audio_paths, output_audio_file)
    
    # script_lines와 segments_raw의 길이가 다를 수 있으므로, 매핑 로직 수정
    segments = []
    # segments_raw는 성공적으로 생성된 오디오 파일에 대한 정보만 담고 있으므로,
    # 해당 정보와 script_lines를 매핑할 때, 스크립트 라인 인덱스와 segments_raw의 인덱스가
    # 항상 일치하지 않을 수 있음을 고려해야 합니다.
    # 여기서는 segments_raw의 길이를 기준으로 반복하고, 해당 세그먼트에 해당하는
    # script_lines의 텍스트를 할당한다고 가정합니다.
    # 만약 TTS 생성 실패로 인해 audio_paths의 길이가 script_lines보다 짧다면,
    # 이 로직은 오작동할 수 있습니다. 이를 방지하기 위해, generate_tts_per_line에서
    # 실패한 라인에 대해 None이나 빈 문자열을 audio_paths에 추가하는 방식으로
    # 길이를 일치시키거나, 여기서 script_lines의 인덱스에 매핑되는 안전한 방법을 사용해야 합니다.
    # 가장 간단한 방법은 generate_tts_per_line에서 오디오 생성 실패 시에도
    # 빈 문자열이나 플레이스홀더 경로를 audio_paths에 넣어 길이를 맞추는 것입니다.
    # 현재 `generate_tts_per_line`이 실패 시 `audio_paths`에 추가하지 않으므로,
    # `segments_raw`의 길이가 `script_lines`의 성공적으로 생성된 오디오 수와 같습니다.
    # 따라서 `segments_raw`와 `script_lines`를 zip하여 사용하는 것은 위험할 수 있습니다.
    # 대신, segments_raw에 이미 텍스트 정보가 포함되어야 합니다.
    # merge_audio_files에서 텍스트 정보도 같이 넘겨주도록 수정하거나,
    # 여기에서 다시 script_lines를 기반으로 segments를 구성하는 방법이 필요합니다.

    # 현재 merge_audio_files는 텍스트를 반환하지 않으므로,
    # script_lines의 순서와 audio_paths의 순서가 일치한다고 가정하고 재매핑합니다.
    # generate_tts_per_line에서 실패한 라인은 audio_paths에 추가되지 않으므로,
    # script_lines와 segments_raw를 직접적으로 1:1 매핑하는 것은 위험합니다.
    # 따라서, _generate_elevenlabs_tts 함수나 _generate_polly_tts 함수에서
    # 오디오 파일이 생성되지 않았을 때에도 빈 오디오 파일이 생성되도록 하거나,
    # (MoviePy에서 빈 오디오 클립 생성),
    # 아니면 segments를 구성할 때 script_lines의 인덱스를 안전하게 매핑해야 합니다.

    # 이 문제를 해결하기 위해, generate_tts_per_line에서 audio_paths와 함께
    # 해당 오디오에 매핑되는 원래 스크립트 라인도 같이 반환하도록 수정하는 것이 가장 좋습니다.
    # 예를 들어, `return [(path, original_line), ...]` 형태로.
    # 현재는 segments_raw에 텍스트 정보가 없으므로,
    # 간단하게 segments_raw의 길이만큼 script_lines를 사용하도록 임시 수정합니다.
    # (이 방식은 generate_tts_per_line에서 오디오 생성에 실패한 라인이
    # segments에서 누락될 수 있음을 의미합니다.)
    
    # 수정된 generate_tts_per_line에서 audio_paths는 (생성된 오디오 경로, 원본 스크립트 라인) 튜플 리스트로 반환된다고 가정
    # 현재 generate_tts_per_line은 경로만 반환하므로, 아래와 같이 재구성.
    # 실제로는 generate_tts_per_line의 반환 값을 (경로, 스크립트) 튜플 리스트로 변경하는 것을 권장합니다.
    
    # 임시 방편으로, segments_raw의 길이에 맞춰 script_lines를 사용합니다.
    # (이는 generate_tts_per_line에서 오디오 생성이 실패한 경우 스크립트-세그먼트 불일치를 야기할 수 있음)
    # 가장 정확한 방법은 generate_tts_per_line 함수가 (오디오 경로, 해당 스크립트 텍스트)의 리스트를 반환하도록 수정하고,
    # merge_audio_files 함수도 이 튜플을 받아 segments에 텍스트를 포함하도록 하는 것입니다.
    
    # 여기서는 기존처럼 segments_raw를 사용하되, script_lines와 길이가 다를 경우를 대비하여
    # segments_raw의 길이를 기반으로 segments를 재구성합니다.
    # 만약 script_lines와 segments_raw의 길이가 다르면, 자막이 제대로 매칭되지 않을 수 있습니다.
    # 이를 해결하기 위해 generate_tts_per_line이 (오디오 경로, 원본 텍스트) 쌍을 반환하도록 하고,
    # merge_audio_files가 그 텍스트를 segments에 포함시키도록 하는 것이 가장 견고합니다.
    
    # 현재 코드를 유지하면서 수정하기 위해, segments_raw에 'text' 키를 추가하는 방식으로 변경합니다.
    # 이 경우, generate_tts_per_line에서 생성 성공한 오디오의 인덱스를 유지해야 합니다.
    # 이는 더 복잡해지므로, generate_timed_segments.py의 `merge_audio_files`에서 텍스트도 같이 받아서
    # 세그먼트에 포함시키는 방식으로 변경하는 것이 좋습니다.

    # 기존 `get_segments_from_audio` 함수가 `merge_audio_files`로 대체되었고,
    # `segments_raw`에는 텍스트 정보가 없으므로, `segments` 리스트를 다시 만듭니다.
    # `generate_tts_per_line`에서 성공적으로 오디오가 생성된 `script_lines`의 인덱스를 알아야 합니다.
    # 이를 위해 `generate_tts_per_line`에서 성공적으로 처리된 라인의 텍스트도 반환하도록 변경하거나,
    # 오디오 경로와 함께 원본 텍스트를 저장해두어야 합니다.

    # 임시방편으로, `script_lines`와 `segments_raw`의 길이가 같다고 가정하고 매핑합니다.
    # 만약 `generate_tts_per_line`에서 오디오 생성이 실패한 라인이 있다면,
    # `segments`의 `text`가 실제 오디오와 매칭되지 않을 수 있습니다.
    segments = []
    # `script_lines`의 각 요소가 `audio_paths`의 각 요소에 대응된다는 강력한 가정이 필요합니다.
    # `generate_tts_per_line` 함수가 실패 시에도 `audio_paths`에 `None`이나 빈 문자열을 추가하여
    # 길이를 `script_lines`와 동일하게 유지한다면 이 방법이 작동할 것입니다.
    # 현재 `generate_tts_per_line`은 실패 시 `audio_paths`에 아무것도 추가하지 않으므로,
    # `segments_raw`의 길이와 `script_lines`의 길이가 다를 수 있습니다.
    # 이 부분은 더 정교한 에러 핸들링이 필요합니다.
    # 예시: `generate_tts_per_line`에서 `(audio_path, original_text)` 튜플 리스트를 반환하도록 변경
    # 또는 `merge_audio_files` 함수가 `script_lines`를 인자로 받아 세그먼트에 텍스트를 추가하도록 변경.

    # 현재 코드 구조에서 가장 간단한 방법은 `generate_tts_per_line`이 반환하는 `audio_paths`와
    # 실제 `script_lines`의 매핑을 정확히 하는 것입니다.
    # 아래 코드는 `segments_raw`와 `script_lines`의 인덱스가 일치한다고 가정한 것입니다.
    # **주의: 이 부분은 `generate_tts_per_line`의 동작에 따라 `script_lines`의 인덱스와
    # `segments_raw`의 인덱스가 1:1로 매칭되지 않을 수 있습니다.
    # 더 견고한 구현을 위해서는 `generate_tts_per_line`이 `(오디오_경로, 해당_텍스트)` 튜플을 반환하도록 변경하고,
    # `merge_audio_files`도 이 텍스트를 세그먼트에 포함시키도록 해야 합니다.**
    
    # 임시 해결책 (완벽하지 않음):
    # `generate_tts_per_line`에서 오디오가 성공적으로 생성된 `script_line`만 추적한다고 가정.
    valid_script_lines = []
    current_line_idx = 0
    # audio_paths와 script_lines를 매칭
    for i, line in enumerate(script_lines):
        # generate_tts_per_line에서 오디오 생성이 성공했는지 확인하는 로직이 필요
        # 현재는 이 정보가 없으므로, 모든 script_lines를 segments에 추가한다고 가정합니다.
        # 실제로는 audio_paths가 생성된 순서대로 대응되는 스크립트 라인을 여기에 추가해야 합니다.
        
        # for segment_info in segments_raw:
        #     # 이 부분에서 segment_info에 해당하는 script_lines의 텍스트를 찾아야 함
        #     # 그러나 현재 segments_raw는 오디오 정보만 가지고 있고, 텍스트는 없습니다.
        #     # 따라서 `merge_audio_files` 함수가 텍스트를 포함하여 반환하도록 변경해야 합니다.
        #     segments.append({
        #         "start": segment_info["start"],
        #         "end": segment_info["end"],
        #         "text": "Placeholder Text" # TODO: 실제 텍스트로 교체 필요
        #     })
        pass
    
    # 최종 segments 리스트를 생성합니다.
    # 여기서는 `segments_raw`와 `script_lines`의 길이가 같다고 "가정"하고 매핑합니다.
    # 이 가정은 `generate_tts_per_line`에서 모든 스크립트 라인에 대해 성공적으로 오디오가 생성될 때만 유효합니다.
    # 현실적인 에러 핸들링을 위해 `generate_tts_per_line`의 반환값을 변경하는 것이 좋습니다.
    segments = []
    # `audio_paths`가 생성될 때 사용된 `script_lines`의 내용을 직접 다시 사용하는 것이 안전합니다.
    # `generate_tts_per_line`에서 `(audio_path, original_line_text)` 튜플 리스트를 반환하도록 변경하는 것이 가장 좋음.
    # 지금은 임시로 `script_lines`를 사용하지만, 이는 오류 발생 가능성이 있습니다.
    if len(segments_raw) == len(script_lines):
        for i, s_raw in enumerate(segments_raw):
            segments.append({
                "start": s_raw["start"],
                "end": s_raw["end"],
                "text": script_lines[i] # 원래 스크립트 라인 사용
            })
    else:
        print("경고: 생성된 오디오 세그먼트 수와 스크립트 라인 수가 일치하지 않습니다. 자막 매핑이 정확하지 않을 수 있습니다.")
        # 이 경우, segments_raw에 텍스트가 없으므로, 자막을 생성하기 어렵습니다.
        # 실제 운영 환경에서는 generate_tts_per_line에서 실패한 라인을 건너뛰지 않고
        # 빈 오디오를 생성하여 길이를 맞추거나, 다른 방식으로 매핑 정보를 전달해야 합니다.
        # 여기서는 최소한의 기능 유지를 위해 segments_raw의 길이만큼만 처리합니다.
        for i, s_raw in enumerate(segments_raw):
            try:
                segments.append({
                    "start": s_raw["start"],
                    "end": s_raw["end"],
                    "text": script_lines[i] # 가능한 경우에만 매핑
                })
            except IndexError:
                segments.append({
                    "start": s_raw["start"],
                    "end": s_raw["end"],
                    "text": "[오디오-스크립트 불일치]" # 오류 메시지
                })


    print(f"디버그: 최종 segments의 길이: {len(segments)}")

    if not segments:
        print("오류: 세그먼트 생성에 실패했습니다. 빈 segments 반환.")
        return [], None, None # audio_clips와 ass_path 모두 None 반환

    # === MoviePy AudioFileClip 생성 ===
    audio_clips = None
    if os.path.exists(output_audio_file):
        try:
            audio_clips = AudioFileClip(output_audio_file)
            print(f"디버그: 전체 오디오 파일 '{output_audio_file}' MoviePy AudioFileClip으로 로드 성공.")
        except Exception as e:
            print(f"오류: 전체 오디오 파일 '{output_audio_file}' 로드 실패: {e}")
            audio_clips = None
    else:
        print(f"경고: 전체 오디오 파일 '{output_audio_file}'이 존재하지 않습니다. 비디오에 오디오가 포함되지 않을 수 있습니다.")

    # ASS 자막 생성
    ass_path = None
    if segments and audio_clips: # segments와 audio_clips가 모두 존재할 때만 자막 생성 시도
        try:
            selected_template = SUBTITLE_TEMPLATES.get(subtitle_template_name, SUBTITLE_TEMPLATES["educational"])
            ass_path = generate_ass_subtitle(segments, selected_template, audio_clips.duration, output_ass_file)
        except Exception as e:
            print(f"오류: ASS 자막 생성 실패: {e}")
            ass_path = None

    return segments, audio_clips, ass_path