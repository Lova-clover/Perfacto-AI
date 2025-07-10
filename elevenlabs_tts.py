import requests
import os
from dotenv import load_dotenv

load_dotenv()
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")

#voice_id를 지정해서 사용하면 될 것으로 보인다.
TTS_TEMPLATES = {
    "educational": {
        "stability": 0.4, #목소리의 일관성 - 낮을수록: 감정 표현이 풍부하지만 톤이 변할 수 있음(예: 흥분했다가 차분해짐) , 높을수록: 감정 변화 없이 안정된 톤 유지(예: 뉴스 앵커 스타일)
        "similarity_boost": 0.7, #목소리 유사도 강화, 낮을수록: 목소리에 자유도 부여 → 다양한 스타일 실험 가능, 높을수록: 해당 voice ID 고유의 특징 유지
        "style": 0.3,  # 숫자 값 (감정 톤 정도)
        "speed_multiplier": 0.9, # 말하는 속도를 조절, 1.0은 기본 속도, 낮을수록 느리게 높을수록 빠르게, 0.7 ~ 1.2 까지 가능하다
        "voice_id": "EXAVITQu4vr4xnSDxMaL" # Bella의 목소리
    },
    "entertainer": {
        "stability": 0.8,
        "similarity_boost": 0.9,
        "style": 0.8,  # 활기찬 감정
        "speed_multiplier": 0.85,
        "voice_id": "21m00Tcm4TlvDq8ikWAM" # Rachel의 목소리
    },
    "slow": {
        "stability": 0.9,
        "similarity_boost": 0.9,
        "style": 0.2,
        "speed_multiplier": 0.8,
        "voice_id": "pMsXgVXv3BLzUgSXRplE" # Sarah의 목소리
    },
    "default": {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.5,
        "speed_multiplier": 1.0,
        "voice_id": "xakE6uxghF6n5lwzlFDa" # Larry의 목소리
    },
    "korean_male":{
        "stability": 0.7,         # 자연스러운 억양과 감정을 위해 0.5~0.75 사이 권장
        "similarity_boost": 0.85, # 원본 목소리 특징을 살리되 과장되지 않게 0.75~0.95 사이 권장
        "style": 0.5,             # 적절한 표현력을 위해 0.3~0.7 사이 권장
        "speed_multiplier": 1.0,  # 일반적인 대화 속도를 위해 1.0에서 시작
        "voice_id": "s07IwTCOrCDCaETjUVjx" # Hyun Bin
    },
    "korean_male2": {
        "stability": 0.7,         # 자연스러운 억양과 감정을 위해 0.5~0.75 권장
        "similarity_boost": 0.85, # 목소리 특징을 잘 살리되 과장되지 않게 0.75~0.95 권장
        "style": 0.5,             # 적절한 표현력, 0.3~0.7 권장
        "speed_multiplier": 1.0,  # 기본 대화 속도
        "voice_id": "7Nah3cbXKVmGX7gQUuwz"  # JoonPark 음성 ID
    },
    "korean_female": {
        "stability": 0.7,
        "similarity_boost": 0.85,
        "style": 0.7,
        "speed_multiplier": 1.1,
        "voice_id": "ksaI0TCD9BstzEzlxj4q" # SeulKi
    },
    "korean_female2": {
        "stability": 0.7,
        "similarity_boost": 0.85,
        "style": 0.5,
        "speed_multiplier": 1.0,
        "voice_id": "AW5wrnG1jVizOYY7R1Oo"  # JiYoung 
    }
}


def generate_tts(text, save_path="assets/audio.mp3", template_name="default", voice_id=None):
    settings = TTS_TEMPLATES.get(template_name, TTS_TEMPLATES["default"])
    
    # ✅ voice_id가 주어지지 않으면 템플릿의 voice_id 사용
    voice_id = voice_id or settings["voice_id"]

    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": settings["stability"],
            "similarity_boost": settings["similarity_boost"],
            "style": settings["style"],
            "speed": settings["speed_multiplier"]
        }
    }

    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers=headers,
        json=data
    )

    if response.status_code == 200:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(response.content)
        print(f"✅ ElevenLabs 음성 저장 완료: {save_path}")
        return save_path
    else:
        raise RuntimeError(f"TTS 생성 실패: {response.status_code} {response.text}")
