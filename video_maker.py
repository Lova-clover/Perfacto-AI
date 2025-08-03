from moviepy import (
    ImageClip, AudioFileClip, concatenate_videoclips,
    CompositeVideoClip, TextClip, ColorClip, CompositeAudioClip
)
import os
import random
import subprocess
import numpy as np
from moviepy.audio.AudioClip import AudioArrayClip
import imageio_ffmpeg

def create_motion_clip(img_path, duration, width, height):
    base_clip_original_size = ImageClip(img_path)

    # 이미지 초기 리사이징 전략 변경: '커버' 방식으로 항상 화면을 가득 채움
    scale_w = width / base_clip_original_size.w
    scale_h = height / base_clip_original_size.h
    
    # 두 스케일 중 더 큰 값을 선택하여, 이미지가 비디오 프레임을 완전히 덮도록 함
    scale_factor_cover = max(scale_w, scale_h)
    
    # Round를 사용하여 소수점 처리 오류 방지, 최소 크기 1 보장
    resized_w_cover = max(1, round(base_clip_original_size.w * scale_factor_cover))
    resized_h_cover = max(1, round(base_clip_original_size.h * scale_factor_cover))

    # 새로운 '커버' 방식으로 리사이즈된 base_clip 생성
    base_clip = base_clip_original_size.resized((resized_w_cover, resized_h_cover)).with_duration(duration)

    clip_width = base_clip.w
    clip_height = base_clip.h

    motion_type = random.choice(["zoom_in_out", "left_to_right", "right_to_left", "static"])

    # 중앙 정렬을 위한 기본 위치
    center_x = round((width - clip_width) / 2)
    center_y = round((height - clip_height) / 2)

    if motion_type == "zoom_in_out":
        start_scale = 1.0
        end_scale = 1.05
        scale_diff = end_scale - start_scale

        # 화면에 꽉 채우도록 커버 리사이즈 먼저 진행
        scale_w = width / base_clip_original_size.w
        scale_h = height / base_clip_original_size.h
        base_scale = max(scale_w, scale_h)

        base_clip = base_clip_original_size.resized(base_scale).with_duration(duration)

        def zoom_factor(t):
            return start_scale + scale_diff * (t / duration)

        def position(t):
            scale = zoom_factor(t)
            w_scaled = base_clip.w * scale
            h_scaled = base_clip.h * scale
            x = round((width - w_scaled) / 2)
            y = round((height - h_scaled) / 2)
            # y가 음수면 0으로 보정해서 아래 검은 여백 방지
            if y < 0:
                y = 0
            return (x, y)

        zoomed_clip = base_clip.resized(zoom_factor).with_position(position)

        return zoomed_clip


    elif motion_type == "left_to_right":
        if clip_width > width:
            max_move = clip_width - width

            # 💡 차이가 아주 작으면 거의 고정 (예: 30픽셀 이하)
            if max_move < 30:
                return base_clip.with_position((center_x, center_y))

            start_ratio = 0.3
            end_ratio = 0.6
            move_ratio = end_ratio - start_ratio

            start_offset = -max_move * start_ratio
            move_distance = max_move * move_ratio

            def ease_in_out(t):
                progress = t / duration
                return 3 * (progress ** 2) - 2 * (progress ** 3)

            def position(t):
                eased = ease_in_out(t)
                x = round(start_offset + move_distance * eased)
                y = center_y
                return (x, y)

            return base_clip.with_position(position)
        else:
            return base_clip.with_position((center_x, center_y))


    elif motion_type == "right_to_left":
        if clip_width > width:
            max_move = clip_width - width

            # 💡 차이가 아주 작으면 거의 고정
            if max_move < 30:
                return base_clip.with_position((center_x, center_y))

            start_ratio = 0.3
            end_ratio = 0.6
            move_ratio = end_ratio - start_ratio

            start_offset = -max_move * end_ratio
            move_distance = max_move * move_ratio

            def ease_in_out(t):
                progress = t / duration
                return 3 * (progress ** 2) - 2 * (progress ** 3)

            def position(t):
                eased = ease_in_out(t)
                x = round(start_offset - move_distance * eased)
                y = center_y
                return (x, y)

            return base_clip.with_position(position)
        else:
            return base_clip.with_position((center_x, center_y))


    else: # "static" (고정)
        # 이미지가 프레임 중앙에 고정되어 잘리지 않고 보여집니다.
        # round()를 사용하여 소수점 처리 오류 방지
        return base_clip.with_position((center_x, center_y))
    
def auto_split_title(text: str, max_first_line_chars=18):
    words = text.split()
    total_chars = sum(len(w) for w in words)
    target = total_chars // 2

    char_count = 0
    for i, word in enumerate(words):
        char_count += len(word)
        if char_count >= target or char_count >= max_first_line_chars:
            return " ".join(words[:i+1]) + "\n" + " ".join(words[i+1:])
    return text

# ✅ 영상 생성 메인 함수
def create_video_with_segments(image_paths, segments, audio_path, topic_title,
                               include_topic_title=True, bgm_path="", save_path="assets/video.mp4"):
    video_width = 720
    video_height = 1080
    clips = []

    # 비디오의 전체 예상 지속 시간 계산
    # segments가 비어있지 않다면 마지막 세그먼트의 끝 시간을 총 지속 시간으로 사용
    if segments:
        total_video_duration = segments[-1]['end']
    else:
        # segments가 비어있는 극단적인 경우를 위한 폴백 (최소 10초)
        total_video_duration = 10 

    # 오디오 클립 초기화 (audio_path가 없으면 무음 클립 생성)
    if audio_path and os.path.exists(audio_path):
        audio = AudioFileClip(audio_path)
    else:
        # 무음 오디오 클립 생성 (moviepy가 None을 처리하지 못하므로)
        # np.array([[0.0, 0.0]])는 무음 오디오 데이터를 나타냅니다.
        audio = AudioArrayClip(np.array([[0.0, 0.0]]), fps=44100).with_duration(total_video_duration)
        print("🔊 음성 파일이 없어 무음 오디오 트랙을 생성했습니다.")

    # segments 개수에 맞춰 이미지도 1:1로 매칭
    num_images_needed = len(segments)
    if len(image_paths) < num_images_needed:
        # 부족하면 마지막 이미지 반복 사용
        image_paths += [image_paths[-1]] * (num_images_needed - len(image_paths))

    for i, seg in enumerate(segments):
        start = seg['start']
        # 각 세그먼트의 duration은 해당 세그먼트의 시작 시간과 끝 시간의 차이로 계산합니다.
        duration = seg['end'] - start

        img_path = image_paths[i]

        # 이미지 하나당 motion clip 생성
        image_clip = create_motion_clip(img_path, duration, video_width, video_height)

        current_segment_clips = [image_clip]

        if include_topic_title:
            title_bar_height = 180
            black_bar = ColorClip(size=(video_width, title_bar_height), color=(0, 0, 0)).with_duration(duration)
            black_bar = black_bar.with_position(("center", "top"))

            formatted_title = auto_split_title(topic_title)

            title_text_clip = TextClip(
                text=formatted_title,
                font_size=48,
                color="white",
                font=os.path.join("assets", "fonts", "NanumGothic.ttf"),
                stroke_color="skyblue",
                stroke_width=1,
                size=(video_width - 40, None),
                method="caption",
            ).with_duration(duration).with_position(("center", 70))

            current_segment_clips.append(black_bar)
            current_segment_clips.append(title_text_clip)

        segment_clip = CompositeVideoClip(current_segment_clips, size=(video_width, video_height)).with_duration(duration)

        clips.append(segment_clip)

    final_audio = audio

    if bgm_path and os.path.exists(bgm_path):
        bgm_raw = AudioFileClip(bgm_path)
        bgm_array = bgm_raw.to_soundarray(fps=44100) * 0.2
        repeat_count = int(np.ceil(audio.duration / bgm_raw.duration))
        bgm_array = np.tile(bgm_array, (repeat_count, 1))
        bgm_array = bgm_array[:int(audio.duration * 44100)]

        bgm = AudioArrayClip(bgm_array, fps=44100).with_duration(audio.duration)
        final_audio = CompositeAudioClip([audio, bgm])

    final = concatenate_videoclips(clips, method="chain")\
        .with_audio(final_audio)\
        .with_fps(24)
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    final.write_videofile(save_path, codec="libx264", audio_codec="aac")
    print(f"✅ 타이밍 동기화 영상 저장 완료: {save_path}")
    return save_path

ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

# ✅ 자막 추가 함수
def add_subtitles_to_video(input_video_path, ass_path, output_path="assets/video_with_subs.mp4"):
    fonts_dir = os.path.abspath(os.path.join("assets", "fonts"))

    command = [
        ffmpeg_path , "-y", "-i", input_video_path,
        "-vf", f"ass={ass_path}:fontsdir={fonts_dir}",
        "-c:a", "copy", output_path
    ]
    try:
        subprocess.run(command, check=True)
        print(f"✅ 자막 포함 영상 저장 완료: {output_path}")
    except subprocess.CalledProcessError as e:
        print("❌ FFmpeg 실행 실패:", e)
    return output_path
