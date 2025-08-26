import subprocess, shlex, os
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Iterable, List, Tuple, Optional, Set

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

# 기존 함수 교체
def generate_images_for_topic(
    query: str,
    num_images: int,
    start_index: int = 0,
    page: int = 1,                              # ★ 추가: 시작 페이지
    exclude_ids: Optional[Iterable[int]] = None,# ★ 추가: 이미 사용한 사진 ID 집합
    return_ids: bool = False                    # ★ 추가: 사진 ID 반환 여부
):
    headers = {"Authorization": PEXELS_API_KEY}
    per_page = min(max(num_images, 1), 80)
    image_paths: List[str] = []
    kept_ids: List[int] = []

    exclude: Set[int] = set(exclude_ids or [])
    current_page = max(1, page)
    saved = 0

    while saved < num_images:
        params = {"query": query, "per_page": per_page, "page": current_page}
        resp = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        photos = data.get("photos", [])
        if not photos:
            break

        for photo in photos:
            if saved >= num_images:
                break
            pid = int(photo["id"])
            if pid in exclude:
                continue

            src = photo["src"].get("large2x") or photo["src"].get("large") or photo["src"].get("original")
            if not src:
                continue

            save_path = f"assets/image_{start_index + saved}.jpg"
            try:
                img = requests.get(src, timeout=30).content
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(img)
                image_paths.append(save_path)
                kept_ids.append(pid)
                saved += 1
            except Exception as e:
                print(f"⚠️ 이미지 다운로드 실패 ({src}): {e}")

        current_page += 1

    return (image_paths, kept_ids) if return_ids else image_paths

def generate_videos_for_topic(
    query: str,
    num_videos: int,
    start_index: int = 0,
    min_duration: float = 3.0,
    orientation: str = "portrait",
    page: int = 1,                              # ✅ 추가: 시작 페이지
    exclude_ids: Optional[Iterable[int]] = None,# ✅ 추가: 제외할 Pexels video id
    return_ids: bool = False,                   # ✅ 추가: 선택된 id도 반환
) -> List[str] | Tuple[List[str], List[int]]:
    headers = {"Authorization": PEXELS_API_KEY}
    sess = _retry_session()
    saved: List[str] = []
    chosen_ids: List[int] = []                  # ✅ 추가
    exclude: Set[int] = set(int(x) for x in (exclude_ids or []))
    per_page = min(max(num_videos, 1), 80)

    while len(saved) < num_videos:
        params = {"query": query, "per_page": per_page, "page": page}
        r = sess.get("https://api.pexels.com/videos/search",
                     headers=headers, params=params, timeout=(5, 20))
        r.raise_for_status()
        data = r.json()
        videos = data.get("videos", [])
        if not videos:
            break

        for v in videos:
            vid = int(v.get("id") or 0)        # ✅ Pexels video id
            if vid and vid in exclude:
                continue

            w, h = v.get("width"), v.get("height")
            dur = float(v.get("duration", 0))
            if orientation == "portrait" and not (w and h and h > w):
                continue
            if dur < min_duration:
                continue

            candidates = [f for f in v.get("video_files", [])
                          if f.get("link", "").endswith(".mp4")
                          and 720 <= (f.get("width") or 0) <= 1080]  # 그대로 유지
            if not candidates:
                candidates = [f for f in v.get("video_files", [])
                              if f.get("link", "").endswith(".mp4")]
            if not candidates:
                continue

            picked = sorted(candidates, key=lambda f: f.get("width") or 10**9)[0]
            url = picked["link"]
            save_path = f"assets/video_{start_index + len(saved)}.mp4"
            tmp_path = save_path + ".part"

            # --- robust download to tmp (.part) then atomically rename ---
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            try:
                with sess.get(url, stream=True, timeout=(5, 30)) as r:
                    r.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        for chunk in r.iter_content(1024 * 64):
                            if chunk:
                                f.write(chunk)

                # sanity check: too-small file은 버림
                if os.path.getsize(tmp_path) < 10 * 1024:  # 10KB 미만이면 실패로 간주
                    raise IOError(f"Downloaded file too small: {tmp_path}")

                # 원자적 치환 → 완성본으로 승격
                os.replace(tmp_path, save_path)

                # 해상도/코덱 정리(선택): 9:16 720x1080 커버로 재인코딩
                try:
                    _shrink_to_720_inplace(save_path)
                except Exception as _:
                    pass

                saved.append(save_path)
                if vid:
                    chosen_ids.append(vid)

            except Exception as e:
                # 실패 시 .part 깨끗이 정리
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except:
                    pass
                print(f"⚠️ 영상 다운로드 실패: {e} | {url}")
                # 다음 후보/다음 비디오로 계속 진행
            if len(saved) >= num_videos:
                break

        page += 1                                # ✅ 더 찾으려면 다음 페이지로

    return (saved, chosen_ids) if return_ids else saved