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