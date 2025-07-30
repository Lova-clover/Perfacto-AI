import os
import re
import whisper
import subprocess   
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
import streamlit as st
from deep_translator import GoogleTranslator
from googleapiclient.discovery import build
from yt_dlp import YoutubeDL

# ========== 설정 ==========
API_KEY = st.secrets["API_KEY"] #유튜브 데이터 받아오기 api키
MAX_RESULTS = 70
AUDIO_DIR = os.path.join("output", "youtube_subtitle", "audio")
TXT_DIR = os.path.join("output", "youtube_subtitle", "texts")    
MAX_WORKERS = 4  # 병렬 처리할 스레드 수

# 디렉토리 생성
os.makedirs(AUDIO_DIR, exist_ok=True)   
os.makedirs(TXT_DIR, exist_ok=True)

model = whisper.load_model("base")

# 안전한 영어 파일명 생성
def safe_filename(title):
    """한글 제목이면 영어로 번역해서 안전한 파일명 생성"""
    if any('\uac00' <= c <= '\ud7a3' for c in title):
        try:
            translated = GoogleTranslator(source='ko', target='en').translate(title)
        except Exception:
            translated = title
    else:
        translated = title
    safe_title = unicodedata.normalize("NFKD", translated)
    safe_title = safe_title.encode("ascii", "ignore").decode("ascii")
    safe_title = re.sub(r'[\\/*?:"<>|#;]', "", safe_title)
    safe_title = safe_title.strip().replace(" ", "_")
    return safe_title[:100] or "untitled"

# [수정] 키워드 기반 인기 영상 리스트(조회수순)
def get_videos_by_query(keyword, max_results):
    youtube = build("youtube", "v3", developerKey=API_KEY)
    videos = []
    next_page_token = None

    # 최대 200개까지 반복해서 가져오기
    while len(videos) < 200 and len(videos) < max_results * 2:
        search_request = youtube.search().list(
            q=keyword,
            type="video",
            part="id,snippet",
            maxResults=50,
            pageToken=next_page_token,
            videoDuration="any",  # short/medium/long/any
            relevanceLanguage="ko"  # 한글 우선 (원하면 삭제)
        )
        search_response = search_request.execute()
        for item in search_response["items"]:
            title = item["snippet"]["title"]
            video_id = item["id"]["videoId"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            # shorts 등 걸러내기
            if "shorts" in title.lower() or "/shorts/" in video_url:
                continue
            videos.append((title, video_url, video_id))
            if len(videos) >= max_results * 2:
                break
        next_page_token = search_response.get("nextPageToken")
        if not next_page_token:
            break

    # 조회수 정보 추가
    video_info = []
    youtube_videos = youtube.videos()
    for i in range(0, len(videos), 50):
        chunk = videos[i:i+50]
        ids = [v[2] for v in chunk]
        stats_response = youtube_videos.list(
            part="statistics,snippet",
            id=",".join(ids)
        ).execute()
        for item in stats_response["items"]:
            view_count = int(item["statistics"].get("viewCount", 0))
            title = item["snippet"]["title"]
            video_url = f"https://www.youtube.com/watch?v={item['id']}"
            video_info.append((title, video_url, view_count))
    # 조회수순 정렬 후 max_results만 반환
    video_info.sort(key=lambda x: x[2], reverse=True)
    return [(title, link) for title, link, _ in video_info[:max_results]]

# yt-dlp로 오디오 다운로드
def download_audio(link, title):
    safe_title = safe_filename(title)
    output_path = os.path.join(AUDIO_DIR, f"{safe_title}.mp3")

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'noplaylist': True,
        'verbose': True
    }

    st.info(f"🌀 [DEBUG] yt-dlp 다운로드 시작:\n🔗 {link}\n📁 저장 위치: `{output_path}`")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([link])
    except Exception as e:
        st.error(f"❌ [DEBUG] yt-dlp 다운로드 실패:\n```\n{e}\n```")
        raise RuntimeError(f"❌ yt-dlp 오류 발생: {e}")

    # 디렉토리 내부 파일 목록 확인
    try:
        file_list = os.listdir(AUDIO_DIR)
        st.info(f"📂 [DEBUG] AUDIO_DIR 내부 파일:\n{file_list}")
    except Exception as e:
        st.warning(f"⚠️ AUDIO_DIR 목록 확인 실패: {e}")

    if not os.path.exists(output_path):
        st.warning(f"❗ [DEBUG] mp3 파일이 존재하지 않음: `{output_path}`")
        raise FileNotFoundError(f"❌ mp3 생성 실패: {output_path}")

    st.success(f"✅ [DEBUG] mp3 생성 성공: `{output_path}`")
    return output_path, safe_title

# Whisper로 자막 추출 후 print 출력
def transcribe_to_txt(audio_path, filename_base):
    result = model.transcribe(audio_path, task="transcribe", verbose=False)
    segments = result.get("segments", [])
    
    # 텍스트를 리스트로 수집
    subtitle_texts = []
    for segment in segments:
        if segment["text"].strip():
            start_time = format_time(segment["start"])
            end_time = format_time(segment["end"])
            text = segment["text"].strip()
            subtitle_texts.append(f"[{start_time} → {end_time}] {text}")
    
    return subtitle_texts

# 시간을 HH:MM:SS 형식으로 변환
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

# 단일 비디오 처리 함수
def process_video(video_data):
    idx, total, title, link = video_data
    print(f"\n[{idx+1}/{total}] 🎬 {title}")
    print(f"🔗 {link}")
    
    try:
        audio_path, filename_base = download_audio(link, title)
        print(f"[{idx+1}/{total}] 🧠 Whisper 텍스트 추출 중...")
        subtitle_texts = transcribe_to_txt(audio_path, filename_base)
        
        # 자막 텍스트 출력
        print(f"\n[{idx+1}/{total}] 📄 자막 내용:")
        print("=" * 80)
        for subtitle in subtitle_texts:
            print(subtitle)
        print("=" * 80)
        
        print(f"[{idx+1}/{total}] ✅ 자막 출력 완료")
        return True
    except Exception as e:
        print(f"[{idx+1}/{total}] ❌ 오류 발생: {e}")
        return False

# 메인
def main():
    keyword = input("🔍 유튜브에서 찾을 주제/키워드 입력 (예: 일제강점기): ").strip()
    print(f"\n🔎 '{keyword}' 관련 유튜브 영상 {MAX_RESULTS}개 (조회수순) 가져오는 중...")
    videos = get_videos_by_query(keyword, MAX_RESULTS)
    
    print(f"\n🚀 병렬 처리 시작 (최대 {MAX_WORKERS}개 동시 처리)")
    
    # 병렬 처리
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 작업 제출
        future_to_video = {
            executor.submit(process_video, (idx, len(videos), title, link)): (idx, title)
            for idx, (title, link) in enumerate(videos)
        }
        
        # 결과 수집
        completed = 0
        failed = 0
        
        for future in as_completed(future_to_video):
            idx, title = future_to_video[future]
            try:
                success = future.result()
                if success:
                    completed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"[{idx+1}] ❌ 예상치 못한 오류: {e}")
                failed += 1
            
            print(f"\n📊 진행 상황: {completed + failed}/{len(videos)} 완료 (성공: {completed}, 실패: {failed})")
    
    print(f"\n🎉 모든 작업 완료! 성공: {completed}개, 실패: {failed}개")

if __name__ == "__main__":
    main()
