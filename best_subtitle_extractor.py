import os
import re
import whisper
import subprocess
import unicodedata
import streamlit as st
from deep_translator import GoogleTranslator
from googleapiclient.discovery import build

from langchain_core.documents import Document as LangChainDocument
from langchain_openai import OpenAIEmbeddings
from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.vectorstores import FAISS

# ===============================
# 🔑 [API KEY 설정 구역]
# ===============================
# 1. 유튜브 API키 (Youtube Data API v3 활성화 필요) # 유튜브 데이터 받아오기 api키
GOOGLE_API_KEYS = st.secrets["GOOGLE_API_KEYS"]

# 2. 오픈AI API키 (https://platform.openai.com/api-keys) #임베딩 및 랭체인 구현
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]

# ===============================
# 🗂️ [디렉토리/환경 설정]
# ===============================
MAX_RESULTS = 50
AUDIO_DIR = os.path.join("output", "youtube_subtitle", "audio")
TXT_DIR = os.path.join("output", "youtube_subtitle", "texts")
YT_DLP_PATH = r"C:\Users\jaemd\Downloads\yt-dlp.exe"

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TXT_DIR, exist_ok=True)
model = whisper.load_model("base")

# ===============================
# 📺 [유튜브 채널 ID 해석]
# ===============================
def extract_channel_id(input_str):
    if '@' in input_str:
        handle = re.search(r'@[\w\-.]+', input_str)
        if handle:
            return 'handle', handle.group()[1:]
    match = re.search(r'channel/([A-Za-z0-9_-]+)', input_str)
    if match:
        return 'id', match.group(1)
    if input_str.startswith('UC'):
        return 'id', input_str  
    return 'username', input_str

def resolve_channel_id(input_str):
    yt = build("youtube", "v3", developerKey=GOOGLE_API_KEYS)
    mode, value = extract_channel_id(input_str)
    if mode == 'handle':
        req = yt.channels().list(part="id", forHandle=value)
        res = req.execute()
        if res.get("items"): return res["items"][0]["id"]
    elif mode == 'id':
        req = yt.channels().list(part="id", id=value)
        res = req.execute()
        if res.get("items"): return res["items"][0]["id"]
    else:
        req = yt.channels().list(part="id", forUsername=value)
        res = req.execute()
        if res.get("items"): return res["items"][0]["id"]
        # fallback: search
        search_req = yt.search().list(q=value, type="channel", part="snippet", maxResults=1)
        search_res = search_req.execute()
        items = search_res.get("items", [])
        if items:
            return items[0]["snippet"]["channelId"]
    raise Exception("채널 ID를 찾을 수 없음.")

# ===============================
# 📝 [파일명 변환, 오디오 다운로드 등]
# ===============================
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

def get_videos_by_viewcount(channel_id, max_results):
    yt = build("youtube", "v3", developerKey=GOOGLE_API_KEYS)
    uploads_pid = yt.channels().list(part="contentDetails", id=channel_id)\
        .execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    videos, next_page = [], None
    while len(videos) < 200:
        pl_req = yt.playlistItems().list(
            part="snippet", playlistId=uploads_pid, maxResults=50, pageToken=next_page
        )
        pl_res = pl_req.execute()
        for item in pl_res["items"]:
            title = item["snippet"]["title"]
            video_id = item["snippet"]["resourceId"]["videoId"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            if "shorts" in title.lower() or "/shorts/" in video_url: continue
            videos.append((title, video_url))
            if len(videos) >= 200: break
        next_page = pl_res.get("nextPageToken")
        if not next_page: break
    # 인기순 정렬
    video_ids = [link.split("v=")[-1] for _, link in videos]
    video_info = []
    for i in range(0, len(video_ids), 50):
        sub_ids = video_ids[i:i+50]
        stats_res = yt.videos().list(
            part="statistics,snippet", id=",".join(sub_ids)
        ).execute()
        for item in stats_res["items"]:
            view_count = int(item["statistics"].get("viewCount", 0))
            title = item["snippet"]["title"]
            video_url = f"https://www.youtube.com/watch?v={item['id']}"
            video_info.append((title, video_url, view_count))
    video_info.sort(key=lambda x: x[2], reverse=True)
    return [(title, link) for title, link, _ in video_info[:max_results]]

def download_audio(link, title):
    safe_title = safe_filename(title)
    output_path = os.path.join(AUDIO_DIR, f"{safe_title}.%(ext)s")
    cmd = [
        YT_DLP_PATH, "-f", "bestaudio", "-o", output_path,
        "--extract-audio", "--audio-format", "mp3", link
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    final_path = os.path.join(AUDIO_DIR, f"{safe_title}.mp3")
    if not os.path.exists(final_path):
        raise FileNotFoundError(f"mp3 생성 실패: {final_path}")
    return final_path, safe_title

def transcribe_to_txt(audio_path, filename_base):
    result = model.transcribe(audio_path, task="transcribe", verbose=False)
    segments = result.get("segments", [])
    texts = [seg["text"].strip() for seg in segments if seg["text"].strip()]
    return texts

# ===============================
# 💾 [임베딩/벡터화(랭체인)]
# ===============================
def vectorize_txt(txt_path):
    with open(txt_path, encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    docs = [LangChainDocument(page_content=line) for line in lines]
    embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)
    splitter = SemanticChunker(embeddings, breakpoint_threshold_type="percentile")
    splits = splitter.split_documents(docs)
    vectorstore = FAISS.from_documents(splits, embeddings)
    print(f"✅ {txt_path} → {len(splits)}개 문단으로 임베딩, 벡터DB 저장 완료")
    return vectorstore

def query_vectorstore(vectorstore, query, k=5):
    results = vectorstore.similarity_search(query, k=k)
    print(f"\n[검색결과 Top-{k}]")
    for i, doc in enumerate(results):
        print(f"\n--- {i+1} ---")
        print(doc.page_content)

# ===============================
# 🚀 [메인]
# ===============================
def main():
    user_input = input("유튜브 @아이디/채널ID/URL 입력: ").strip()
    try:
        channel_id = resolve_channel_id(user_input)
    except Exception as e:
        print(f"채널 인식 실패: {e}"); return
    print(f"채널ID: {channel_id}")

    videos = get_videos_by_viewcount(channel_id, MAX_RESULTS)
    for idx, (title, link) in enumerate(videos):
        print(f"\n[{idx+1}/{len(videos)}] 🎬 {title}")
        try:
            audio_path, filename_base = download_audio(link, title)
            print("🧠 Whisper 텍스트 추출 중...")
            texts = transcribe_to_txt(audio_path, filename_base)
            
            # 텍스트 출력
            print(f"\n[{idx+1}/{len(videos)}] 📄 자막 내용:")
            print("=" * 80)
            for text in texts:
                print(text)
            print("=" * 80)
            print(f"✅ 텍스트 출력 완료")

        except Exception as e:
            print(f"❌ 오류: {e}"); continue

if __name__ == "__main__":
    main()
