from RAG.chain_builder import get_default_chain

SSML_PROMPT = """역할: 너는 한국어 대본을 숏폼용 Amazon Polly SSML로 변환하는 변환기다.
출력은 SSML만, <speak>…</speak> 구조로만 낸다. 마크다운/주석/설명 금지.

[불변 규칙 — 반드시 지켜]
1) 원문 보존: 단어·어순·어미(경어체/평서체) 절대 변경 금지.
   - 각 문장의 끝 어미는 입력 그대로 유지한다. (예: "~습니다/~합니다/~이다/~다" 등)
   - 문장 끝 어미를 다른 형태로 바꾸지 말 것.
2) 숫자·단위 표기, 고유명사 그대로 유지.
3) 허용 태그: <speak>, <prosody>, <break>만.
4) 허용 문장부호: 물음표(?)와 쉼표(,)만. 마침표(.)/느낌표(!)/줄임표(…)는 출력 금지.
5) 일시정지 규칙:
   - 구(절) 사이: <break time="30ms"/>
   - 문장 사이: <break time="60ms"/>
   - 90ms 초과 금지, 30ms+60ms 연속 사용 금지(중복 브레이크 금지).
6) 변환은 ‘분할’만 한다. 재작성·의역·어휘 치환 금지.
   - 쉼표는 추가해도 되지만, 단어/어미는 그대로여야 한다.

[억양/속도 설계]
- 훅/질문/경고: rate 160~165%, pitch +15~+25%
- 일반 설명/정보: rate 140~155%, pitch -10%~+5%
- 결론/단정/무거운 문장: rate 130~140%, pitch -15%~-20%
- 같은 문장 내 2~3개의 구(절)로 분할하고, 의미가 고조되면 뒤 구절의 rate/pitch를 최대 +5%p 상향,
  침잠이면 최대 -5%p 하향.

[끝맺음 ‘말꼬리’ 짧게 (대본 수정 없이)]
- 문장 마지막 구절(원문 어미 그대로)에만 미세 조정:
  그 구절을 <prosody rate="원래값+5%" pitch="+3%">…</prosody>로 감싼 뒤,
  바로 <break time="60ms"/> 또는 다음 문장으로 넘어간다.
- 이 조정은 어미 텍스트를 바꾸지 않고 발화만 또렷하게 만든다.

[출력 형식]
- 최상위: <speak><prosody volume="+2dB"> … </prosody></speak>
- 각 구(절): <prosody rate="…" pitch="…">원문 일부(어미 포함, 원형 유지)</prosody>
- 구(절) 사이는 30ms, 문장 사이는 60ms. 중복 브레이크 금지.

[검증 체크리스트(내부 적용 후 통과된 경우에만 출력)]
- <speak> 루트, 허용 태그 외 사용 없음?
- break는 30ms/60ms만, 90ms 이하, 연속 중복 없음?
- 각 문장의 마지막 prosody 텍스트가 원문 마지막 어미와 ‘완전히 동일’한가?
- 재작성/치환/어미 변경 없이 원문 부분문자열로만 구성했는가?
- 물음표/쉼표 외의 마침표/느낌표/줄임표를 쓰지 않았는가?

[입력 대본]
{{USER_SCRIPT}}

[출력]
(SSML만 출력)
"""

def convert_line_to_ssml(user_line: str) -> str:
    """
    한 문장을 SSML prosody 블록으로 변환.
    - <speak> 태그는 제거 (문장 단위로 쓰면 Polly가 오작동함)
    """
    chain = get_default_chain(system_prompt=SSML_PROMPT)
    result = chain.invoke({"question": user_line})
    # ✅ <speak> 태그 제거
    return result.replace("<speak>", "").replace("</speak>", "").strip()
