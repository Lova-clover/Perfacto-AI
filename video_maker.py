from moviepy import (
    ImageClip, VideoFileClip, AudioFileClip, concatenate_videoclips,
    CompositeVideoClip, TextClip, ColorClip, CompositeAudioClip
)
import os
import random
import subprocess
import numpy as np
from moviepy.audio.AudioClip import AudioArrayClip, concatenate_audioclips
import gc
import imageio_ffmpeg
# 상단 임포트 근처
try:
    from moviepy.audio.fx import audio_loop          # moviepy 2.x
except Exception:
    try:
        from moviepy.audio.fx.all import audio_loop  # moviepy 1.x
    except Exception:
        audio_loop = None

def _st(msg):
    try:
        import streamlit as st
        st.write(msg)
    except Exception:
        print(msg)

def _with_audio_compat(video, audio):
    try:
        return video.with_audio(audio)   # moviepy 2.x
    except AttributeError:
        return video.set_audio(audio)    # moviepy 1.x
    
def _loop_audio_manual(clip, duration):
    rep = int(np.ceil(duration / max(clip.duration, 0.1)))
    looped = concatenate_audioclips([clip] * max(1, rep))
    return looped.subclip(0, duration)

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
    split_idx = None
    for i, word in enumerate(words):
        char_count += len(word)
        if (char_count >= target or char_count >= max_first_line_chars) and i < len(words) - 1:
            split_idx = i + 1
            break

    if split_idx is None:
        return text, ""  # 한 줄
    return " ".join(words[:split_idx]), " ".join(words[split_idx:])

# ✅ 영상 생성 메인 함수 (size=None 전달 금지 처리 포함)
def create_video_with_segments(
    image_paths,
    segments,
    audio_path,
    topic_title,
    include_topic_title=True,
    bgm_path="",
    save_path="assets/video.mp4",
    ass_path=None,   # (호환용) 여기선 사용하지 않음. 자막은 main에서 add_subtitles_to_video로 번인.
):
    W, H = 720, 1080
    clips = []
    total_dur = segments[-1]['end'] if segments else 10.0

    # ---------- 내부 헬퍼들 ----------
    def _normalize_image_paths(paths, n_needed):
        paths = list(paths or [])
        if len(paths) < n_needed:
            last_valid = next((p for p in reversed(paths) if p and os.path.exists(p)), None)
            paths += [last_valid] * (n_needed - len(paths))
        elif len(paths) > n_needed:
            paths = paths[:n_needed]
        return [p if (p and os.path.exists(p)) else None for p in paths]

    def _build_text_clip(text: str, font_path: str, font_size: int, max_width: int):
        try:
            clip = TextClip(
                text=text + "\n",
                font=font_path, font_size=font_size,
                color="white",
                stroke_color="skyblue", stroke_width=1,
                method="caption", size=(max_width, None),
                align="center",
            )
            return clip, True
        except TypeError:
            clip = TextClip(
                text=text + "\n",
                font=font_path, font_size=font_size,
                color="white",
                method="label",
            )
            return clip, False
        except Exception:
            return None, False

    def _measure_text_h(text: str, font_path: str, font_size: int, max_width: int, used_caption: bool):
        try:
            if used_caption:
                dummy = TextClip(text=text, font=font_path, font_size=font_size, method="caption", size=(max_width, None))
            else:
                dummy = TextClip(text=text, font=font_path, font_size=font_size, method="label")
            h = dummy.h
            try: dummy.close()
            except: pass
            return h
        except Exception:
            return 0

    def auto_split_title(text: str, max_first_line_chars=18):
        words = text.split()
        total = sum(len(w) for w in words)
        target = max_first_line_chars if total > max_first_line_chars*2 else (total // 2 or total)
        acc = 0
        for i, w in enumerate(words[:-1]):
            acc += len(w)
            if acc >= target:
                return " ".join(words[:i+1]), " ".join(words[i+1:])
        return text, ""

    def _fallback_motion_clip(img_path, duration, width, height):
        try:
            base = ImageClip(img_path)
            scale = max(width / base.w, height / base.h)
            base = base.resized(scale).with_duration(duration)
            cx = round((width - base.w) / 2)
            cy = round((height - base.h) / 2)
            return base.with_position((cx, cy))
        except Exception:
            return ColorClip(size=(width, height), color=(0, 0, 0)).with_duration(duration)

    # ---------- 음성(내레이션) ----------
    narration = None
    if audio_path and os.path.exists(audio_path):
        try:
            narration = AudioFileClip(audio_path)
        except Exception as e:
            print(f"⚠️ 내레이션 로드 실패: {e}")
            narration = None

    # ---------- 이미지 리스트 정리 ----------
    image_paths = _normalize_image_paths(image_paths, len(segments))

    # ---------- 타이틀(옵션) ----------
    title_clip_proto, used_caption, title_bar_h = None, False, 0
    title_text = (topic_title or "").strip()
    if include_topic_title and title_text:
        font_path = os.path.join("assets", "fonts", "BMJUA_ttf.ttf")
        l1, l2 = auto_split_title(title_text)
        full_title = l1 + ("\n" + l2 if l2 else "")
        title_clip_proto, used_caption = _build_text_clip(full_title, font_path, 32, W - 40)
        if title_clip_proto is not None:
            title_bar_h = _measure_text_h(full_title, font_path, 32, W - 40, used_caption) + 32
        else:
            title_bar_h = 0

    # ---------- 세그먼트별 합성 ----------
    for i, seg in enumerate(segments):
        start = seg['start']
        dur   = max(0.1, seg['end'] - start)

        img_path = image_paths[i]
        if img_path is None:
            base = ColorClip(size=(W, H), color=(0, 0, 0)).with_duration(dur)
        else:
            try:
                base = create_motion_clip(img_path, dur, W, H)  # 프로젝트에 있으면 사용
            except NameError:
                base = _fallback_motion_clip(img_path, dur, W, H)
            except Exception:
                base = ColorClip(size=(W, H), color=(0, 0, 0)).with_duration(dur)

        overlays = [base]

        if title_clip_proto is not None:
            title_clip = title_clip_proto.with_duration(dur)
            black_bar  = ColorClip(size=(W, int(title_bar_h)), color=(0, 0, 0)).with_duration(dur).with_position(("center","top"))
            tx = int(round((W - title_clip.w) / 2))
            ty = int(max(0, min(round((title_bar_h - title_clip.h) / 2) + 10, title_bar_h - title_clip.h)))
            overlays += [black_bar, title_clip.with_position((tx, ty))]

        seg_clip = CompositeVideoClip(overlays, size=(W, H)).with_duration(dur)
        clips.append(seg_clip)

    # ---------- BGM 선택 ----------
    chosen_bgm = bgm_path if (bgm_path and os.path.exists(bgm_path)) else None
    target_duration = narration.duration if narration else total_dur

    # 🔧 pydub로 미리 믹스(보이스 없어도 BGM만 길이에 맞춰 깔림)
    mixed_path = os.path.join(os.path.dirname(save_path) or ".", "_mix_audio.mp3")
    final_audio = None
    try:
        _mix_voice_and_bgm(
            voice_path=(audio_path if (audio_path and os.path.exists(audio_path)) else None),
            bgm_path=chosen_bgm,
            out_path=mixed_path,
            bgm_gain_db=-30, #BGM 소리 크기     
            add_tail_ms=250
        )
        final_audio = AudioFileClip(mixed_path)
    except Exception as e:
        print(f"⚠️ pre-mix 실패 → 즉석 믹스로 폴백: {e}")
        # ─ 폴백: MoviePy만으로 안전하게 믹스
        try:
            import math
            parts = []
            if narration is not None:
                parts.append(narration)
            if chosen_bgm and os.path.exists(chosen_bgm):
                bgm_raw = AudioFileClip(chosen_bgm)
                need = target_duration if narration is None else narration.duration
                rep = int(math.ceil(need / max(bgm_raw.duration, 0.1)))
                bgm_tiled = concatenate_audioclips([bgm_raw] * max(1, rep)).subclip(0, need).volumex(0.15)
                parts.append(bgm_tiled)
            if parts:
                final_audio = CompositeAudioClip(parts)
        except Exception as ee:
            print(f"⚠️ 폴백 믹스도 실패: {ee}")
            final_audio = narration  # 그래도 보이스는 유지

    # ---------- 파일 쓰기 ----------
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    tmp_out = os.path.join(os.path.dirname(save_path) or ".", "_temp_no_subs.mp4")

    video = concatenate_videoclips(clips, method="chain").with_fps(24)
    if final_audio is not None:
        video = _with_audio_compat(video, final_audio)

    video.write_videofile(
        tmp_out,
        codec="libx264",
        audio_codec="aac",
        audio_bitrate="192k"
    )

    try: video.close()
    except: pass
    try:
        for c in clips: c.close()
    except: pass
    if narration: 
        try: narration.close()
        except: pass
    gc.collect()

    if tmp_out != save_path:
        try:
            os.replace(tmp_out, save_path)
        except Exception:
            pass

    print(f"✅ (자막 미적용) 영상 저장 완료: {save_path}")
    return save_path


ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

# ✅ 자막 추가 함수
def add_subtitles_to_video(input_video_path, ass_path, output_path):
    import subprocess, shlex, os
    fonts_dir = os.path.abspath(os.path.join("assets", "fonts"))
    # 경로에 공백/역슬래시가 있어도 안전하게
    ass_q = ass_path.replace("\\", "/")
    fonts_q = fonts_dir.replace("\\", "/")

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video_path,
        "-vf", f"ass='{ass_q}':fontsdir='{fonts_q}'",
        "-c:v", "libx264",
        "-c:a", "aac", "-b:a", "192k",
        # ★ 비디오/오디오 모두 유지(오디오 없으면 무시)
        "-map", "0:v:0", "-map", "0:a?", 
        output_path
    ]
    subprocess.run(cmd, check=True)
    return output_path

from pydub import AudioSegment
import math, os

def _mix_voice_and_bgm(voice_path: str | None, bgm_path: str | None, out_path: str,
                       bgm_gain_db: float = 6, add_tail_ms: int = 250) -> str | None:
    """
    - voice만 있으면 그대로 복사(꼬리 무음 추가)
    - bgm만 있으면 길이에 맞춰 자르고 내보냄
    - 둘 다 있으면 voice 길이에 bgm을 루프/트림해서 -18dB로 깔고 overlay
    """
    if not voice_path and not bgm_path:
        return None

    voice = AudioSegment.silent(duration=0)
    bgm   = AudioSegment.silent(duration=0)

    if voice_path and os.path.exists(voice_path):
        voice = AudioSegment.from_file(voice_path)
    if bgm_path and os.path.exists(bgm_path):
        bgm = AudioSegment.from_file(bgm_path)

    if len(voice) == 0 and len(bgm) == 0:
        return None

    if len(voice) == 0:
        # 보이스가 없으면 BGM만 트림
        out = bgm[:]
        out.export(out_path, format="mp3")
        return out_path

    # 보이스가 있으면 길이에 맞춰 BGM을 루프/트림하고 감쇠
    target_len = len(voice) + add_tail_ms
    if len(bgm) == 0:
        bed = AudioSegment.silent(duration=target_len)
    else:
        rep = math.ceil(target_len / len(bgm))
        bed = (bgm * max(1, rep))[:target_len]
        bed = bed + bgm_gain_db  # 음량 감쇠(예: -18dB)

    mixed = bed.overlay(voice)  # 보이스를 위에 얹는다
    mixed.export(out_path, format="mp3")
    return out_path

def create_dark_text_video(script_text, title_text, audio_path=None, bgm_path="", save_path="assets/dark_text_video.mp4"):
    video_width, video_height = 720, 1080
    font_path = os.path.abspath(os.path.join("assets", "fonts", "BMJUA_ttf.ttf"))
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"폰트가 없습니다: {font_path}")

    if audio_path and os.path.exists(audio_path):
        audio = AudioFileClip(audio_path)
        duration = audio.duration
    else:
        duration = 2
        audio = AudioArrayClip(np.array([[0.0, 0.0]]), fps=44100).with_duration(duration)

    bg_clip = ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_duration(duration)

    # ===== 레이아웃 상수 =====
    TOP_MARGIN = 150
    BOTTOM_MARGIN = 80
    SAFE_BOTTOM_PAD = 24
    SAFE_SIDE_PAD = 24
    LEFT_BLEED_PAD = 12
    CONTENT_WIDTH = video_width - SAFE_SIDE_PAD * 2

    # ===== 제목 2줄 + 말줄임 =====
    def ellipsize_two_lines(text, max_chars_per_line=20):
        if not text: return ""
        import textwrap
        wrapped = textwrap.wrap(text.strip(), width=max_chars_per_line, break_long_words=True, break_on_hyphens=False)
        if len(wrapped) <= 2: return "\n".join(wrapped)
        out = wrapped[:2]
        out[1] = (out[1].rstrip()[:-1] + "…") if len(out[1].rstrip()) > 0 else "…"
        return "\n".join(out)

    title_text = ellipsize_two_lines(title_text or "", max_chars_per_line=18)

    # ===== 폭 측정 유틸(래핑/폭 계산만 label로 사용) =====
    def line_width(s: str, fs: int) -> int:
        if not s: return 0
        c = TextClip(text=s, font=font_path, font_size=fs, method="label")
        w = c.w
        c.close()
        return w

    # 단어 단위 래핑
    def wrap_to_width(text: str, max_w: int, fs: int):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if not cur or line_width(test, fs) <= max_w:
                cur = test
            else:
                lines.append(cur); cur = w
        if cur: lines.append(cur)
        return lines if lines else [""]

    # 입력 줄바꿈 보존 + 블록별 래핑
    def wrap_preserving_newlines(text: str, max_w: int, fs: int):
        out = []
        for block in (text or "").splitlines():
            if block.strip() == "":
                out.append("")              # 빈 줄 유지
            else:
                out.extend(wrap_to_width(block, max_w, fs))
        return out

    # 제목 가운데 맞춤(시각적)
    def center_label_multiline(raw_text: str, max_w: int, fs: int, pad_char="\u00A0"):
        blocks = raw_text.split("\n")
        lines = [b if b.strip() else "" for b in blocks]
        def _w(s):
            if not s: return 0
            c = TextClip(text=s, font=font_path, font_size=fs, method="label")
            w = c.w; c.close(); return w
        maxw = max((_w(l) for l in lines), default=0)
        spacew = max(_w(pad_char), 1)
        centered = []
        for l in lines:
            lw = _w(l)
            pad = int(round((maxw - lw) / (2 * spacew))) if maxw > lw else 0
            centered.append(pad_char * pad + l)
        return "\n".join(centered) + "\n"

    # ===== 제목 =====
    title_fontsize = 38
    max_title_width = CONTENT_WIDTH - 2 * LEFT_BLEED_PAD
    centered_title_text = center_label_multiline(title_text, max_title_width, title_fontsize)
    title_clip_tmp = TextClip(
        text=centered_title_text, font=font_path, font_size=title_fontsize, color="white", method="label"
    )
    title_h = title_clip_tmp.h
    title_y = TOP_MARGIN
    title_x = int(SAFE_SIDE_PAD + LEFT_BLEED_PAD + ((CONTENT_WIDTH - 2 * LEFT_BLEED_PAD) - title_clip_tmp.w) / 2)
    title_clip = title_clip_tmp.with_position((title_x, int(title_y))).with_duration(duration)

    # ===== 본문(왼쪽 정렬처럼 보이게 + 하단 잘림 방지) =====
    GAP_TITLE_BODY = 32
    allowed_body_height = video_height - BOTTOM_MARGIN - (title_y + title_h + GAP_TITLE_BODY) - SAFE_BOTTOM_PAD

    if allowed_body_height <= 0:
        video = CompositeVideoClip([bg_clip, title_clip], size=(video_width, video_height)).with_duration(duration)
    else:
        body_fontsize  = 28
        body_width_px  = CONTENT_WIDTH

        LINE_GAP       = int(round(body_fontsize * 0.3))  # 줄 사이 추가 간격
        TOP_PAD_PX     = int(round(body_fontsize * 0.12))  # 첫 줄 위 여유
        BOTTOM_PAD_PX  = int(round(body_fontsize * 0.25))  # 마지막 줄 아래 여유
        DESCENDER_EXTRA = 2                                # 각 줄 하단 여유용 보정(px)

        MIN_FONT_SIZE   = 14
        MIN_WIDTH_RATIO = 0.60
        min_width_px    = int(CONTENT_WIDTH * MIN_WIDTH_RATIO)

        # 좌우 1.5 글자 내부 패딩
        base_char_w = max(8, line_width("가", body_fontsize), line_width("M", body_fontsize))
        INNER_PAD = int(round(base_char_w * 1.5))

        NBSP, HAIR = "\u00A0", "\u200A"

        def spacer(h):
            return ColorClip(size=(1, max(1, int(h))), color=(0, 0, 0)).with_opacity(0)

        def build_body(fs: int, width_px: int):
            eff_wrap_w = max(20, width_px - 2 * INNER_PAD - 2 * LEFT_BLEED_PAD)
            lines = wrap_preserving_newlines((script_text or "").rstrip(), eff_wrap_w, fs)

            clips = []
            y = TOP_PAD_PX
            maxw = 1

            for i, line in enumerate(lines):
                if line.strip() == "":
                    sg = spacer(fs + LINE_GAP)
                    clips.append(sg.with_position((0, y))); y += sg.h
                    continue

                # 1) 이 줄의 실제 텍스트 폭을 label로 측정
                plain_w = line_width(line, fs)
                # 2) 가운데 정렬을 막기 위해 caption 박스 폭을 "실제 텍스트폭 + 여유"로 설정
                cap_w = max(plain_w + 6, 10)

                # 3) 하단 잘림 방지를 위해 줄 끝에 "\n\u200A" 추가
                safe_line = NBSP + line + "\n" + HAIR

                c = TextClip(
                    text=safe_line,
                    font=font_path,
                    font_size=fs,
                    color="white",
                    method="label",
                    size=(cap_w, None),   # 줄 길이만큼만 박스 생성 → 시각적 왼쪽정렬
                    interline=0
                )
                clips.append(c.with_position((0, y)))
                y += c.h + DESCENDER_EXTRA
                maxw = max(maxw, c.w)

                if i < len(lines) - 1:
                    gap = spacer(LINE_GAP)
                    clips.append(gap.with_position((0, y))); y += gap.h

            total_h = y + BOTTOM_PAD_PX
            if not clips:
                return CompositeVideoClip([spacer(int(fs * 1.2)).with_position((0, 0))],
                                          size=(1, int(fs * 1.2))).with_duration(duration)

            return CompositeVideoClip(clips, size=(maxw, total_h)).with_duration(duration)

        # allowed_body_height에 맞춰 조정
        fit_clip = None
        for _ in range(80):
            body_label = build_body(body_fontsize, body_width_px)
            if body_label.h <= allowed_body_height:
                fit_clip = body_label
                break
            if body_fontsize > MIN_FONT_SIZE:
                body_fontsize = max(MIN_FONT_SIZE, body_fontsize - 2)
                base_char_w = max(8, line_width("가", body_fontsize), line_width("M", body_fontsize))
                INNER_PAD = int(round(base_char_w * 1.5))
                continue
            if body_width_px > min_width_px:
                body_width_px = max(min_width_px, body_width_px - 10)
                continue
            scale = allowed_body_height / float(body_label.h)
            fit_clip = body_label.resized(scale)
            break

        if fit_clip is None:
            fit_clip = build_body(body_fontsize, body_width_px)

        # 좌우 1.5자 패딩 래퍼
        body_wrapper_w = fit_clip.w + 2 * INNER_PAD
        body_wrapper_h = fit_clip.h
        body_wrapper = CompositeVideoClip(
            [fit_clip.with_position((INNER_PAD, 0))],
            size=(body_wrapper_w, body_wrapper_h)
        ).with_duration(duration)

        # 중앙 정렬(래퍼 기준)
        body_x = int(SAFE_SIDE_PAD + ((CONTENT_WIDTH - body_wrapper.w) / 2))
        body_y = int(title_y + title_h + GAP_TITLE_BODY)
        body_clip = body_wrapper.with_position((body_x, body_y)).with_duration(duration)

        # 하단 투명 패드
        pad_clip = ColorClip(size=(video_width, SAFE_BOTTOM_PAD), color=(0, 0, 0)).with_opacity(0) \
                   .with_duration(duration).with_position(("center", video_height - SAFE_BOTTOM_PAD))

        video = CompositeVideoClip([bg_clip, title_clip, body_clip, pad_clip],
                                   size=(video_width, video_height)).with_duration(duration)

    # ===== 오디오 & 저장 =====
    final_audio = audio
    if bgm_path and os.path.exists(bgm_path):
        bgm = AudioFileClip(bgm_path).volumex(0.05).with_duration(duration)
        final_audio = CompositeAudioClip([audio, bgm])

    final_video = video.with_audio(final_audio).with_fps(24)
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    final_video.write_videofile(save_path, codec="libx264", audio_codec="aac")
    return save_path

def create_video_from_videos(
    video_paths,
    segments,
    audio_path,
    topic_title,
    include_topic_title=True,
    bgm_path="",
    save_path="assets/video_from_videos.mp4",
):
    """
    여러 소스 동영상을 세그먼트 길이에 맞춰 자르고(부족하면 반복),
    상단 타이틀 오버레이(선택)를 얹은 뒤, 내레이션/배경음악을 믹스해
    최종 영상을 저장합니다.

    - MoviePy의 TextClip(method="label")에 size=None을 넘기지 않도록 안전 처리.
    - caption 가능하면 caption을 사용(size=(W,None)), 실패 시 label로 폴백.
    - 세그먼트별 파일로 먼저 렌더링 후 ffmpeg concat → 오디오 mux.
    """
    import os
    import math
    import re
    import gc
    import shutil
    import tempfile
    import subprocess
    import numpy as np
    
    # ── 기본 설정
    video_width, video_height = 720, 1080
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

    # ── 전체 길이(세그먼트 끝)
    total_video_duration = segments[-1]["end"] if segments else 10.0

    # ── 내레이션(or 무음)
    if audio_path and os.path.exists(audio_path):
        narration = AudioFileClip(audio_path)
    else:
        # 무음(스테레오) 생성
        nframes = max(1, int(total_video_duration * 44100))
        silent = np.zeros((nframes, 2), dtype=np.float32)
        narration = AudioArrayClip(silent, fps=44100)
        narration = narration.with_duration(total_video_duration)
        print("🔊 음성 파일이 없어 무음 오디오 트랙을 생성했습니다.")

        # ── BGM 믹스(옵션)
    final_audio = narration
    if bgm_path and os.path.exists(bgm_path):
        try:
            _st(f"🎧 BGM path: {bgm_path} (exists={os.path.exists(bgm_path)})")
            bgm_raw = AudioFileClip(bgm_path)
            sr = 44100

            if not getattr(bgm_raw, "duration", 0) or bgm_raw.duration <= 0.1:
                raise RuntimeError("BGM duration too short")

            narr_dur = float(narration.duration)

            # BGM을 배열로 변환 → 길이에 맞춰 타일링
            bgm_arr = bgm_raw.to_soundarray(fps=sr)
            if bgm_arr.ndim == 1:  # 모노면 스테레오로 복제
                bgm_arr = np.column_stack([bgm_arr, bgm_arr])

            need = int(np.ceil(narr_dur / max(bgm_raw.duration, 0.001)))
            tiled = np.tile(bgm_arr, (need, 1))
            n_samples = int(np.round(narr_dur * sr))
            tiled = tiled[:n_samples]

            # 볼륨: 적당히 들리게 (원하면 0.5~0.8 사이로 조절)
            gain = 0.2
            tiled = tiled * gain

            # 배열 → AudioArrayClip → 내레이션과 합성
            bgm_clip = AudioArrayClip(tiled, fps=sr).with_duration(narr_dur)
            final_audio = CompositeAudioClip([narration, bgm_clip])

            _st(f"✅ Mixed BGM (narr={narr_dur:.3f}s, bgm={bgm_raw.duration:.3f}s, sr={sr})")
        except Exception as e:
            _st(f"⚠️ BGM mix failed (continue w/o BGM): {e}")
    else:
        _st("ℹ️ No BGM path or not found — narration only")

    # ── 소스 동영상 수 보정(부족 시 순환)
    if len(video_paths) < len(segments) and video_paths:
        cycle = (len(segments) + len(video_paths) - 1) // len(video_paths)
        video_paths = (video_paths * cycle)[:len(segments)]

    # ── 타이틀 도우미(내부)
    def _auto_split_title(title: str):
        t = (title or "").strip()
        if not t:
            return "", ""
        # 길면 대략 절반에서 공백 근처로 분리
        if len(t) <= 14:
            return t, ""
        mid = len(t) // 2
        # mid 주변 공백 탐색
        left = t.rfind(" ", 0, mid)
        right = t.find(" ", mid)
        if left == -1 and right == -1:
            return t, ""
        cut = left if (left != -1 and (mid - left) <= (right - mid if right != -1 else 1e9)) else (right if right != -1 else left)
        return t[:cut].strip(), t[cut:].strip()

    # ── 안전한 TextClip 빌더
    def _build_text_clip(text: str, font_path: str, font_size: int, max_width: int):
        # caption 먼저 시도
        try:
            clip = TextClip(
                text=text + "\n",
                font_size=font_size,
                color="white",
                font=font_path,
                stroke_color="skyblue",
                stroke_width=1,
                method="caption",               # ← caption이면 size 허용
                size=(max_width, None),
                align="center",
            )
            return clip, True
        except TypeError:
            # label 폴백 (size 절대 전달하지 않음!)
            clip = TextClip(
                text=text + "\n",
                font_size=font_size,
                color="white",
                font=font_path,
                method="label",
            )
            return clip, False

    # ── 리사이즈(cover)
    def _resize_cover(clip, W, H):
        scale = max(W / clip.w, H / clip.h)
        resized = clip.resized(scale)
        x = int(round((W - resized.w) / 2))
        y = int(round((H - resized.h) / 2))
        return resized.with_position((x, y))

    # ── 세그먼트별 파일 생성
    seg_files = []
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()

    for i, seg in enumerate(segments):
        duration = max(0.1, seg["end"] - seg["start"])
        src_path = video_paths[i % len(video_paths)] if video_paths else None

        if (not src_path) or (not os.path.exists(src_path)):
            # 비상: 색 배경
            base = ColorClip(size=(video_width, video_height), color=(0, 0, 0)).with_duration(duration)
        else:
            raw = VideoFileClip(src_path).without_audio()
            try:
                if raw.duration < duration:
                    # 부족하면 반복
                    repeat = int(math.ceil(duration / max(raw.duration, 0.1)))
                    rep = concatenate_videoclips([raw] * repeat, method="chain").subclip(0, duration)
                    base = _resize_cover(rep, video_width, video_height)
                else:
                    base = _resize_cover(raw.subclipped(0, duration), video_width, video_height)
            finally:
                try:
                    raw.close()
                except Exception:
                    pass

        overlays = [base]

        # ── 상단 타이틀(선택)
        if include_topic_title and (topic_title or "").strip():
            font_path = os.path.join("assets", "fonts", "BMJUA_ttf.ttf")
            line1, line2 = _auto_split_title(topic_title)
            title_text = line1 + ("\n" + line2 if line2 else "")
            max_title_w = video_width - 40

            title_clip, used_caption = _build_text_clip(title_text, font_path, 48, max_title_w)
            # bar 높이는 만들어진 clip 높이에 padding만 더함 (dummy 불필요)
            title_bar_h = int(title_clip.h + 32)

            black_bar = ColorClip(size=(video_width, title_bar_h), color=(0, 0, 0)).with_duration(duration).with_position(("center", "top"))

            tx = int(round((video_width - title_clip.w) / 2))
            ty = int(max(0, min(round((title_bar_h - title_clip.h) / 2) + 10, title_bar_h - title_clip.h)))
            title_clip = title_clip.with_duration(duration).with_position((tx, ty))

            overlays.extend([black_bar, title_clip])

        seg_clip = CompositeVideoClip(overlays, size=(video_width, video_height)).with_duration(duration)

        seg_out = os.path.join(os.path.dirname(save_path) or ".", f"_seg_{i:03d}.mp4")
        seg_clip.write_videofile(
            seg_out,
            codec="libx264",
            audio=False,
            fps=24,
            preset="ultrafast",
            threads=max(1, (os.cpu_count() or 2) // 2),
            ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=None,
        )
        try:
            seg_clip.close()
        except Exception:
            pass
        gc.collect()

        seg_files.append(os.path.abspath(seg_out))

    # ── 잘못된 세그먼트 검사
    bad = [p for p in seg_files if (not os.path.exists(p)) or os.path.getsize(p) < 1024]
    if bad:
        raise RuntimeError(f"잘못된 세그먼트 파일 발견: {bad}")

    # ── 경로 sanitize + concat 리스트
    def _sanitize_for_concat(paths):
        safe = []
        tmp_dir = None
        for p in paths:
            ap = os.path.abspath(p).replace("\\", "/").replace("\r", "").replace("\n", "")
            if re.search(r"[^A-Za-z0-9._/\-]", ap):
                if tmp_dir is None:
                    tmp_dir = tempfile.mkdtemp(prefix="_concat_safe_")
                base = re.sub(r"[^A-Za-z0-9._-]", "_", os.path.basename(ap))
                safe_ap = os.path.join(tmp_dir, base)
                if not os.path.exists(safe_ap):
                    shutil.copy2(ap, safe_ap)
                ap = os.path.abspath(safe_ap).replace("\\", "/")
            safe.append(ap)
        return safe

    safe_paths = _sanitize_for_concat(seg_files)
    concat_txt = os.path.join(os.path.dirname(save_path) or ".", "_concat.txt")
    with open(concat_txt, "wb") as f:
        f.write(b"ffconcat version 1.0\n")
        for ap in safe_paths:
            f.write(f"file '{ap}'\n".encode("utf-8"))

    # ── 비디오 concat
    temp_video = os.path.join(os.path.dirname(save_path) or ".", "_temp_video.mp4")
    try:
        subprocess.run(
            [ffmpeg_path, "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
             "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "23", "-an", temp_video],
            check=True,
        )
    except subprocess.CalledProcessError:
        # fallback: filter_complex concat
        cmd = [ffmpeg_path, "-y"]
        for p in safe_paths:
            cmd += ["-i", p]
        n = len(safe_paths)
        filtergraph = "".join(f"[{i}:v]" for i in range(n)) + f"concat=n={n}:v=1:a=0[outv]"
        cmd += ["-filter_complex", filtergraph, "-map", "[outv]",
                "-r", "24", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-preset", "ultrafast", "-crf", "23", "-an", temp_video]
        subprocess.run(cmd, check=True)

    # ── 오디오 추출/인코드
    audio_mix = os.path.join(os.path.dirname(save_path) or ".", "_mix_audio.m4a")
    try:
        final_audio.write_audiofile(audio_mix, fps=44100, codec="aac", bitrate="128k", logger=None)
    except Exception:
        wav_tmp = os.path.join(os.path.dirname(save_path) or ".", "_mix_audio.wav")
        try:
            final_audio.write_audiofile(wav_tmp, fps=44100, logger=None)
            subprocess.run([ffmpeg_path, "-y", "-i", wav_tmp, "-c:a", "aac", "-b:a", "128k", audio_mix], check=True)
            os.remove(wav_tmp)
        except Exception as e:
            print(f"⚠️ 오디오 인코딩 폴백 실패: {e}")

    # ── 비디오+오디오 mux
    subprocess.run(
        [ffmpeg_path, "-y",
         "-i", temp_video, "-i", audio_mix,
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
         save_path],
        check=True,
    )

    print(f"✅ 영상(동영상 소스) 저장 완료: {save_path}")

    # ── 정리
    for p in seg_files + [concat_txt, temp_video, audio_mix]:
        try:
            os.remove(p)
        except Exception:
            pass
    try:
        if final_audio is not narration:
            final_audio.close()
    except Exception:
        pass
    try:
        narration.close()
    except Exception:
        pass
    gc.collect()

    return save_path
