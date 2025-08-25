import subprocess, shlex, os
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

def _shrink_to_720_inplace(path: str):
    """
    원본을 720p 세로 기준으로 즉시 재인코딩하여 덮어쓴다.
    - 9:16 캔버스 기준으로 scale+crop
    - CRF 30, ultrafast → 클라우드에서도 가볍게
    """
    tmp = path + ".shrink.mp4"
    vf = 'scale=720:-2:force_original_aspect_ratio=increase,crop=720:1080,format=yuv420p'
    cmd = f'ffmpeg -y -i {shlex.quote(path)} -vf {shlex.quote(vf)} -r 24 -c:v libx264 -preset ultrafast -crf 30 -c:a aac -b:a 96k {shlex.quote(tmp)}'
    subprocess.run(cmd, shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    os.replace(tmp, path)

def _retry_session(total=4, backoff=0.8):
    """
    429/5xx 재시도 + 타임아웃/연결풀 설정된 requests 세션
    """
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    retry = Retry(
        total=total, read=total, connect=total, status=total,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods={"GET", "HEAD"},
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s

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
    sess = _retry_session()  # ✅ 재시도/타임아웃/UA 세션
    saved = []
    page = 1
    per_page = min(max(num_videos, 1), 80)

    while len(saved) < num_videos:
        params = {"query": query, "per_page": per_page, "page": page}
        r = sess.get(
            "https://api.pexels.com/videos/search",
            headers=headers, params=params, timeout=(5, 20)
        )
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

            # ✅ 720~1080 중 가장 작은 해상도 우선
            candidates = [
                f for f in v.get("video_files", [])
                if f.get("link", "").endswith(".mp4") and 720 <= (f.get("width") or 0) <= 1080
            ]
            if not candidates:
                candidates = [f for f in v.get("video_files", []) if f.get("link", "").endswith(".mp4")]

            if not candidates:
                continue

            picked = sorted(candidates, key=lambda f: f.get("width") or 10**9)[0]
            url = picked["link"]
            save_path = f"assets/video_{start_index + len(saved)}.mp4"
            tmp_path = save_path + ".part"

            try:
                # ✅ (1) HEAD로 대략 용량 확인해서 150MB↑는 스킵
                try:
                    head = sess.head(url, timeout=(5, 10), allow_redirects=True)
                    cl = head.headers.get("Content-Length")
                    if cl and int(cl) > 150 * 1024 * 1024:
                        print(f"⚠️ 용량 초과로 스킵: {int(int(cl)/1024/1024)}MB {url}")
                        continue
                except Exception:
                    pass  # HEAD 실패 시 GET에서 한 번 더 체크

                # ✅ (2) GET 다운로드(재시도/타임아웃/UA 유지)
                resp = sess.get(url, stream=True, timeout=(5, 60))
                resp.raise_for_status()

                cl = resp.headers.get("Content-Length")
                if cl and int(cl) > 150 * 1024 * 1024:
                    print(f"⚠️ 용량 초과로 스킵: {int(int(cl)/1024/1024)}MB {url}")
                    resp.close()
                    continue

                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(tmp_path, "wb") as out:
                    for chunk in resp.iter_content(1024 * 1024):
                        if chunk:
                            out.write(chunk)
                os.replace(tmp_path, save_path)
                print(f"✅ 영상 저장 완료: {save_path}")

                # ✅ (3) 다운로드 직후 720p 세로 기준 경량화
                try:
                    _shrink_to_720_inplace(save_path)
                    print(f"✅ 720p 경량화 완료: {save_path}")
                except Exception as e:
                    print(f"⚠️ 720p 경량화 실패(원본으로 진행): {e}")

                saved.append(save_path)
                if len(saved) >= num_videos:
                    break

            except Exception as e:
                print(f"⚠️ 영상 다운로드 실패 ({url}): {e}")
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except:
                    pass
                continue

        if not data.get("next_page"):
            break
        page += 1

    return saved


