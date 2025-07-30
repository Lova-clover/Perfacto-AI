from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json
import os

token_path = os.path.join(os.path.dirname(__file__), "token.json")


def upload_to_youtube(video_path, title="AI 자동 생성 영상", description="AI로 생성된 숏폼입니다."):
    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    # ✅ secrets.toml에서 문자열로 받아오기
    token_json_str = st.secrets["YT_TOKEN_JSON"]

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