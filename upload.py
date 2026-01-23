from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json
import os


def _get_youtube_token():
    """
    YouTube OAuth 토큰을 Streamlit secrets 또는 환경변수에서 가져옵니다.
    
    우선순위:
    1. Streamlit secrets (st.secrets["YT_TOKEN_JSON"])
    2. 환경변수 (YOUTUBE_TOKEN_JSON)
    """
    # 1. Streamlit secrets 시도
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and 'YT_TOKEN_JSON' in st.secrets:
            return st.secrets["YT_TOKEN_JSON"]
    except (ImportError, RuntimeError, KeyError):
        pass
    
    # 2. 환경변수 시도
    token_json_str = os.getenv("YOUTUBE_TOKEN_JSON")
    if token_json_str:
        return token_json_str
    
    raise RuntimeError(
        "YouTube OAuth 토큰을 찾을 수 없습니다.\n"
        "- Streamlit: .streamlit/secrets.toml에 YT_TOKEN_JSON 추가\n"
        "- 환경변수: YOUTUBE_TOKEN_JSON 설정\n"
        "- GitHub Actions: Secrets에 YOUTUBE_TOKEN_JSON 추가"
    )


def upload_to_youtube(video_path, title="AI 자동 생성 영상", description="AI로 생성된 숏폼입니다."):
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    # ✅ Streamlit 또는 환경변수에서 토큰 가져오기
    token_json_str = _get_youtube_token()

    # ✅ 문자열을 파싱해서 dict로 변환
    token_data = json.loads(token_json_str)

    # ✅ token dict로 자격 증명 생성
    credentials = Credentials.from_authorized_user_info(token_data, SCOPES)

    youtube = build("youtube", "v3", credentials=credentials)

    request_body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["AI", "쇼츠", "자동화"],
            "categoryId": "22"
        },
        "status": {
            "privacyStatus": "public"
        }
    }

    media_file = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True)
    upload_request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=media_file
    )
    response = upload_request.execute()
    return f"https://youtube.com/watch?v={response['id']}"