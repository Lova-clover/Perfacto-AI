import requests
import os
import streamlit as st
import boto3 # Import the boto3 library for AWS services

# Load API keys from Streamlit secrets
ELEVEN_API_KEY = st.secrets["ELEVEN_API_KEY"]
AWS_ACCESS_KEY_ID = st.secrets["AWS_ACCESS_KEY_ID"]
AWS_SECRET_ACCESS_KEY = st.secrets["AWS_SECRET_ACCESS_KEY"]
AWS_REGION = st.secrets.get("AWS_REGION", "ap-northeast-2") # Default to Seoul region

# Initialize Amazon Polly client
# This client will be reused for Polly TTS requests.
polly_client = boto3.client(
    'polly',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

# ElevenLabs TTS Templates (unchanged from your original code)
TTS_ELEVENLABS_TEMPLATES = {
    "educational": {
        "stability": 0.4, # 목소리의 일관성 - 낮을수록: 감정 표현이 풍부하지만 톤이 변할 수 있음(예: 흥분했다가 차분해짐) , 높을수록: 감정 변화 없이 안정된 톤 유지(예: 뉴스 앵커 스타일)
        "similarity_boost": 0.7, # 목소리 유사도 강화, 낮을수록: 목소리에 자유도 부여 → 다양한 스타일 실험 가능, 높을수록: 해당 voice ID 고유의 특징 유지
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

# Amazon Polly Voice Mappings
# Amazon Polly uses VoiceIds. We can map descriptive names to these IDs.
TTS_POLLY_VOICES = {
    "default_male": "Matthew",       # 영어 (미국) 남성 - 유명한 이름
    "default_female": "Joanna",      # 영어 (미국) 여성 - 유명한 이름
    # 한국어 남성은 제외 (Polly에는 한국어 남성 음성이 현재 없음)
    "korean_female1": "Jihye",        
    "korean_female2": "Seoyeon",      # 한국어 여성
    "english_male_uk": "Brian",      # 영어 (영국) 남성 - 유명한 이름
    "english_female_uk": "Amy",      # 영어 (영국) 여성 - 유명한 이름
    "japanese_male": "Takumi",       # 일본어 남성 (추가)
    "japanese_female": "Mizuki",     # 일본어 여성 (추가)
    "spanish_male": "Enrique",       # 스페인어 (카스티야) 남성 (추가)
    "spanish_female": "Conchita",    # 스페인어 (카스티야) 여성 (추가)
    "french_male": "Mathieu",        # 프랑스어 남성 (추가)
    "french_female": "Celine",       # 프랑스어 여성 (추가)
    # 필요에 따라 더 많은 언어/성별 조합 추가 가능
}

def generate_elevenlabs_tts(text, save_path, template_name, voice_id):
    """
    Generates speech using ElevenLabs API.
    This is the original generate_tts logic, refactored into a private helper function.
    """
    settings = TTS_ELEVENLABS_TEMPLATES.get(template_name, TTS_ELEVENLABS_TEMPLATES["default"])

    # voice_id가 주어지지 않으면 템플릿의 voice_id 사용
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
        raise RuntimeError(f"ElevenLabs TTS 생성 실패: {response.status_code} {response.text}")

def generate_polly_tts(text, save_path, polly_voice_name_key):
    voice_id = TTS_POLLY_VOICES.get(polly_voice_name_key, "Matthew")  # 안전 폴백을 영어로
    # 보이스 키 → 언어 매핑(필요한 것만)
    VOICE_LANG = {
        "default_female":"en-US","default_male":"en-US",
        "english_female_uk":"en-GB","english_male_uk":"en-GB",
        "korean_female1":"ko-KR","korean_female2":"ko-KR",
    }
    lang = VOICE_LANG.get(polly_voice_name_key, "en-US")
    use_ssml = lang.startswith("en")  # 영어 보이스면 SSML로 감싸 정확도 ↑

    def synth(engine):
        args = dict(OutputFormat='mp3', VoiceId=voice_id, Engine=engine)
        if use_ssml:
            ssml = f"<speak><lang xml:lang='{lang}'>{text}</lang></speak>"
            return polly_client.synthesize_speech(Text=ssml, TextType='ssml', **args)
        else:
            return polly_client.synthesize_speech(Text=text, TextType='text', **args)

    try:
        resp = synth('neural')
    except Exception as e:
        # neural 미지원 등 → standard로 재시도
        resp = synth('standard')

    with open(save_path, 'wb') as f:
        f.write(resp['AudioStream'].read())
    return save_path


def generate_tts(text, save_path="assets/audio.mp3", provider="Amazon Polly", template_name="default", voice_id=None, polly_voice_name_key="Matthew"):
    """
    Generates text-to-speech using either ElevenLabs or Amazon Polly based on the provider.

    Args:
        text (str): The text to convert to speech.
        save_path (str): The path to save the generated audio file.
        provider (str): The TTS provider to use ('elevenlabs' or 'polly').
        template_name (str, optional): For ElevenLabs, the name of the voice template. Defaults to "default".
        voice_id (str, optional): For ElevenLabs, a specific voice ID to override the template's voice. Defaults to None.
        polly_voice_name_key (str, optional): For Amazon Polly, the key from TTS_POLLY_VOICES to select the voice. Defaults to "default_male".

    Returns:
        str: The path to the saved audio file.

    Raises:
        ValueError: If an unsupported provider is specified.
        RuntimeError: If TTS generation fails from the chosen provider.
    """
    if provider == "elevenlabs":
        return generate_elevenlabs_tts(text, save_path, template_name, voice_id)
    elif provider == "polly":
        return generate_polly_tts(text, save_path, polly_voice_name_key)
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}. Choose 'elevenlabs' or 'polly'.")
