# keyword_generator.py
import json
from typing import List
import re 
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
import streamlit as st

# ===== 공통 LLM 호출 유틸 =====
def _complete_with_any_llm(prompt: str) -> str:
    """
    프로젝트 공통 LLM 호출. OpenAI(gpt-5-mini) 사용.
    """
    llm = ChatOpenAI(
        api_key=st.secrets["OPENAI_API_KEY"],
        model="gpt-5-mini",
        temperature=1,
    )
    output_parser = StrOutputParser()
    chain = ChatPromptTemplate.from_messages([
        ("system", "너는 과학 콘텐츠용 키워드 생성 보조 AI다."),
        ("human", "{question}")
    ]) | llm | output_parser

    try:
        return chain.invoke({"question": prompt}).strip()
    except Exception as e:
        return json.dumps([])

# ===== 신규 프롬프트 (배치 키워드 생성 전용) =====
NEW_IMAGE_KEYWORDS_PROMPT = """
You are an assistant that generates concise, literal visual search keywords in English for stock videos.

OUTPUT RULES (VERY IMPORTANT)
- Output ONLY a JSON array of strings. No markdown, no commentary.
- The array MUST have the same length and the same order as the input "lines".
- Each element = a single concise English keyword phrase (2–5 words).
- Use concrete, visual nouns/phrases that are easy to search (avoid abstract words).
- Do NOT include: cartoon, illustration, clipart, 3D, logo, text, quotes.
- Prefer neutral, safe, non-celebrity scenes (weather, nature, space, city, people in daily life).
- Translate non-English lines into English keywords if needed.

INPUT (JSON):
{ "lines": ["... line 1 ...", "... line 2 ...", "... line 3 ..."] }

OUTPUT (JSON ONLY):
["...", "...", "..."]
"""

# ===== 배치 키워드 생성 함수 =====
def generate_image_keywords_per_line_batch(lines: List[str]) -> List[str]:
    """
    전체 라인 배열을 한 번에 넣고, 동일 길이의 영어 키워드 배열(JSON)을 1회 반환.
    """
    if not lines:
        return []

    prompt = f"""{NEW_IMAGE_KEYWORDS_PROMPT}

Now process this input:

{json.dumps({"lines": lines}, ensure_ascii=False)}
"""
    raw = _complete_with_any_llm(prompt)
    try:
        kws = json.loads(raw)
    except Exception:
        # 모델이 JSON 형식을 깨뜨린 경우: 줄 단위 fallback
        kws = [x.strip() for x in raw.splitlines() if x.strip()]

    if not isinstance(kws, list):
        raise ValueError("❌ 키워드 결과가 JSON 배열이 아님")

    if len(kws) != len(lines):
        raise AssertionError(f"❌ 키워드 배열 길이 불일치: {len(kws)} vs {len(lines)}")

    # 출력 정리
    norm = []
    for kw in kws:
        k = " ".join((kw or "").lower().split())
        if not k:
            k = "abstract background"
        norm.append(k)
    return norm
