import os
import requests
from dotenv import load_dotenv

load_dotenv()
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

def generate_image_pexels(query: str, save_path: str, per_page: int = 1) -> str:
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": query, "per_page": per_page}
    response = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params)
    response.raise_for_status()
    data = response.json()
    image_url = data["photos"][0]["src"]["large"]
    image_data = requests.get(image_url).content
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(image_data)
    print(f"✅ 이미지 저장 완료: {save_path}")
    return save_path

def generate_images_for_topic(query: str, num_images: int, start_index: int = 0):
    image_paths = []
    headers = {"Authorization": PEXELS_API_KEY}
    # Pexels API는 per_page 최대 80까지 가능합니다.
    # 원하는 이미지 수에 따라 여러 페이지를 요청해야 할 수도 있습니다.
    params = {"query": query, "per_page": min(num_images, 80)} # 한 번에 최대 80개까지 가져옴
    
    # 페이지네이션을 고려해야 함
    current_page = 1
    images_downloaded = 0
    
    while images_downloaded < num_images:
        params["page"] = current_page
        response = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data["photos"]:
            print(f"⚠️ 더 이상 이미지를 찾을 수 없습니다. (현재 {images_downloaded}/{num_images} 장)")
            break

        for photo in data["photos"]:
            if images_downloaded >= num_images:
                break
            image_url = photo["src"]["large"]
            save_path = f"assets/image_{start_index + images_downloaded}.jpg"
            try:
                image_data = requests.get(image_url).content
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(image_data)
                print(f"✅ 이미지 저장 완료: {save_path}")
                image_paths.append(save_path)
                images_downloaded += 1
            except Exception as e:
                print(f"⚠️ 이미지 다운로드 실패 ({image_url}): {e}")
        
        if not data.get("next_page"): # 다음 페이지가 없으면 중단
            break
        current_page += 1
    
    return image_paths

# === 동영상 다운로드: Pexels Videos API ===
def generate_videos_for_topic(
    query: str,
    num_videos: int,
    start_index: int = 0,
    min_duration: float = 3.0,
    orientation: str = "portrait",  # 'portrait' 9:16 위주
):
    """
    Pexels에서 '세로형(권장)' 영상을 내려받아 assets/video_*.mp4 로 저장.
    - query: 검색 키워드(영어가 매칭 잘 됨)
    - num_videos: 필요한 개수(segments 수와 맞추면 좋음)
    - min_duration: 너무 짧은 클립 제외
    - orientation: 'portrait'이면 세로 비중 높은 것 우선 필터
    """
    headers = {"Authorization": PEXELS_API_KEY}
    saved = []
    page = 1
    per_page = min(max(num_videos, 1), 80)

    while len(saved) < num_videos:
        params = {"query": query, "per_page": per_page, "page": page}
        r = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        videos = data.get("videos", [])
        if not videos:
            break

        for v in videos:
            w, h = v.get("width"), v.get("height")
            dur = float(v.get("duration", 0))
            if orientation == "portrait" and not (w and h and h > w):
                continue
            if dur < min_duration:
                continue

            # 해상도 높은 mp4 우선
            files = sorted(
                v.get("video_files", []),
                key=lambda f: (f.get("width", 0), f.get("height", 0)),
                reverse=True,
            )
            picked = None
            for f in files:
                link = f.get("link", "")
                if link.endswith(".mp4") and f.get("width", 0) >= 720:
                    picked = f
                    break
            if not picked:
                continue

            url = picked["link"]
            save_path = f"assets/video_{start_index + len(saved)}.mp4"
            try:
                resp = requests.get(url, stream=True)
                resp.raise_for_status()
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as out:
                    for chunk in resp.iter_content(1024 * 1024):
                        if chunk:
                            out.write(chunk)
                print(f"✅ 영상 저장 완료: {save_path}")
                saved.append(save_path)
                if len(saved) >= num_videos:
                    break
            except Exception as e:
                print(f"⚠️ 영상 다운로드 실패 ({url}): {e}")

        if not data.get("next_page"):
            break
        page += 1

    return saved
