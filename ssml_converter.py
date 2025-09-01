from RAG.chain_builder import get_default_chain
import re
from html import escape as _xml_escape

try:
    from llm_utils import complete_text  # 존재하면 활용
except Exception:
    complete_text = None

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None
    
def _looks_english(text: str) -> bool:
    if not text: return False
    en = len(re.findall(r"[A-Za-z]", text))
    ko = len(re.findall(r"[\uac00-\ud7a3]", text))
    return en >= 3 and en > ko * 1.2

def koreanize_if_english(text: str) -> str:
    """문장이 사실상 영어면, 의미 동일 한국어 한 문장으로 변환."""
    t = (text or "").strip()
    if not t or not _looks_english(t):
        return t

    # 1) LLM 시도 (의미 동일 한국어 한 문장)
    prompt = (
        "역할: 너는 한국어 문장 변환기다.\n"
        "출력은 한국어 **한 문장**만. 마크다운/주석/설명 금지.\n"
        "규칙: 의미를 100% 유지. 숫자/단위/고유명사는 보존. 문장 끝 어미는 평서체.\n\n"
        "[입력]\n" + t + "\n\n[출력]\n"
    )
    try:
        out = _complete_with_any_llm(prompt)
        if out and out.strip():
            # 안전 정리
            s = re.sub(r"\s+", " ", out).strip()
            return s
    except Exception:
        pass

    # 2) 폴백: Google 번역
    if GoogleTranslator is not None:
        try:
            return GoogleTranslator(source="auto", target="ko").translate(t)
        except Exception:
            pass

    # 3) 실패 시 원문 유지
    return t
    
def _heuristic_breath_lines(text: str) -> list[str]:
    """LLM 부재 시 쓰는 간단 브레스 분할 (1~3조각 권장, 원문 보존/줄바꿈만 추가)"""
    t = (text or "").strip()
    if not t:
        return []
    # 담화표지/연결어/구두점 뒤에서 1차 분할(경계 토큰은 앞 조각에 둠)
    t = re.sub(r"(그리고|하지만|근데|그런데|그래서|그러니까|즉|특히|게다가|한편|반면에|다만)\s*", r"\g<0>§", t)
    t = re.sub(r"(고|지만|는데요?|면서|며|라면|면|니까|다가|으며|거나|든지)(?=\s|\Z)", r"\1§", t)
    t = re.sub(r"(?<=[,，、;:·?])\s*", "§", t)
    parts = [p.strip() for p in t.split("§") if p.strip()] or [t]

    # 길이 보정(8~18자/3~6단어 권장)
    out = []
    for p in parts:
        if len(p) <= 18:
            out.append(p)
        else:
            cur = p
            while len(cur) > 18:
                window = cur[:24]
                spaces = [m.start() for m in re.finditer(r"\s", window)]
                cut = spaces[-1] if spaces else 18
                out.append(cur[:cut].strip())
                cur = cur[cut:].strip()
            if cur:
                out.append(cur)

    # 1~2단어 초단문은 이웃과 병합
    def _wc(s): return len(re.findall(r'\S+', s))
    i = 1
    while i < len(out):
        if _wc(out[i]) < 2:
            out[i-1] = (out[i-1].rstrip() + " " + out[i].lstrip()).strip()
            out.pop(i)
        else:
            i += 1

    # 3조각 초과면 가장 짧은 인접쌍부터 합쳐 최대 3개
    def _len_like(s): return len(s)
    while len(out) > 3:
        best_i, best_sum = 0, 10**9
        for k in range(len(out)-1):
            ssum = _len_like(out[k]) + _len_like(out[k+1])
            if ssum < best_sum:
                best_sum, best_i = ssum, k
        out[best_i] = (out[best_i] + " " + out[best_i+1]).strip()
        out.pop(best_i+1)

    return out


def breath_linebreaks(text: str) -> list[str]:
    """
    LLM 기반 호흡 줄바꿈. complete_text가 없거나 실패하면 휴리스틱 사용.
    - 원문 글자/공백/어미는 그대로, '줄바꿈만' 추가
    - 빈 줄 생성 금지
    """
    t = (text or "").strip()
    if not t:
        return []
    if complete_text is not None:
        prompt = (
            "역할: 너는 한국어 대본의 호흡(브레스) 라인브레이크 편집기다.\n"
            "출력은 텍스트만, 줄바꿈으로만 호흡을 표현한다. 다른 기호·주석·설명·마크다운·태그 금지.\n\n"
            "[불변 규칙]\n"
            "원문 완전 보존(글자/공백/숫자/단위/어미/어순). 줄바꿈만 추가.\n"
            "빈 줄 금지. 1–2단어 초단문은 피하기. 한 줄 길이 가이드 3–6단어 또는 8–18글자.\n"
            "수치/부호 결합(-173도, 1만 2천 km 등) 분리 금지. ‘… 수 있다/없다, … 것이다/것입니다’ 등 분리 금지.\n"
            "담화표지는 강조 시 단독 줄 허용. 물음표 ? 뒤 줄바꿈 허용.\n\n"
            "[입력]\n" + t + "\n\n[출력]\n"
        )
        try:
            out = complete_text(prompt)
            lines = [ln.rstrip() for ln in (out or "").splitlines() if ln.strip()]
            # 라인브레이크만 추가했는지 대략 검증
            if lines and abs(len("".join(lines)) - len(t.replace("\n", ""))) <= max(10, int(len(t)*0.2)):
                return lines
        except Exception:
            pass
    # 폴백
    return _heuristic_breath_lines(t)

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

BREATH_PROMPT = """역할: 너는 한국어 대본의 호흡(브레스) 라인브레이크 편집기다.
출력은 텍스트만, 줄바꿈으로만 호흡을 표현한다. 다른 기호·주석·설명·마크다운·태그를 절대 쓰지 않는다.

[불변 규칙]
원문 완전 보존(글자/공백/숫자/단위/어미/어순). 줄바꿈만 추가.
빈 줄 금지. 1–2단어 초단문은 피하기.
한 줄 길이 가이드: 3–6단어 또는 8–18글자 권장.
수치·부호 결합(-173도, 1만 2천 km 등) 분리 금지.
“… 수 있다/없다, … 것이다/것입니다, … 해야 한다” 등은 한 줄 유지.
담화표지(물론/따라서/즉/그러니까/그리고/그러나/하지만 등)는 강조 시 단독 줄 허용.
질문부호 ? 뒤는 줄바꿈 가능.

[입력]
{{TEXT}}

[출력]
(라인브레이크 적용된 텍스트만)"""


def _complete_with_any_llm(prompt: str) -> str | None:
    if complete_text is not None:
        try:
            return complete_text(prompt)
        except Exception:
            pass
    try:
        chain = get_default_chain()
        for payload in ({"question": prompt}, {"input": prompt}, prompt):
            try:
                out = chain.invoke(payload)
                if isinstance(out, str):
                    return out
                if isinstance(out, dict):
                    texts = [str(v) for v in out.values() if isinstance(v, (str, bytes))]
                    return max(texts, key=len) if texts else None
            except Exception:
                continue
    except Exception:
        pass
    return None

def _unwrap_speak(ssml: str) -> str:
    m = re.search(r"<speak[^>]*>(.*)</speak>", ssml or "", flags=re.S|re.I)
    return (m.group(1) if m else (ssml or "")).strip()

def convert_line_to_ssml(user_line: str) -> str:
    """
    한 줄 대본을 Amazon Polly 친화 SSML로 분할(구/절 단위 prosody + 짧은 break).
    - 태그: <prosody>, <break>만 사용 (여기서는 <speak>는 붙이지 않음)
    - 마침표/느낌표는 폴백에서만 정리(Polly 안정성), 물음표/쉼표는 유지
    - 원문 어휘/어순 보존, '분할'만 수행
    """
    try:
        from xml.sax.saxutils import escape as _xml_escape
    except Exception:
        def _xml_escape(s: str) -> str:
            return (s or "") \
                .replace("&", "&amp;").replace("<", "&lt;") \
                .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

    t = (user_line or "").strip()
    if not t:
        return ""

    # ── [전처리: 의미 보존/발음 안정화] ─────────────────────────────────────
    # 마이너스 기호 통일(−, –, — → -), 얇은 공백 등 정리
    t = t.replace("\xa0", " ").translate(str.maketrans({"–": "-", "—": "-", "−": "-"}))

    # ① 천단위 콤마 제거: 1,234,567 → 1234567  (숫자 사이에만 있는 콤마 모두 제거)
    t = re.sub(r'(?<=\d),(?=\d)', '', t)

    # ② 숫자+단위 붙이기: "10000 km" → "10000km"  (공백만 제거, 본문 의미 불변)
    unit_pat = r'(km|m|cm|mm|μm|nm|kg|g|mg|t|L|l|ml|℃|°C|°F|도|%)'
    t = re.sub(rf'(\d)\s+({unit_pat})(\b)', r'\1\2', t)

    # ③ 비율/속도: "1 / 3" → "1/3" , "30 km/h" → "30 km/h" (가독만 정리)
    t = re.sub(r'(\d)\s*/\s*(\d)', r'\1/\2', t)        # 분수/비율
    t = re.sub(r'(\d)\s+(km/h|m/s)', r'\1 \2', t)      # 속도 단위 앞은 한 칸 유지

    # ── [LLM 경로: 있으면 그대로 사용] ────────────────────────────────────
    try:
        prompt = SSML_PROMPT.replace("{{USER_SCRIPT}}", t)
        out = _complete_with_any_llm(prompt) or ""
        out = out.strip()
        if out:
            frag = _unwrap_speak(out)  # <speak> 감싸져 오면 껍데기 제거
            # 허용 외 태그 제거 (prosody/break만 허용)
            frag = re.sub(r"</?(?!prosody\b|break\b)[a-zA-Z0-9:_-]+\b[^>]*>", "", frag)
            # 연속 break 1회로 축약
            frag = re.sub(r'(?:<break\b[^>]*/>\s*){2,}', '<break time="30ms"/>', frag)
            if frag.strip():
                return frag
    except Exception:
        pass

    # ── [폴백 경로: 소수점 보호 후 문장부호 정리] ──────────────────────────
    tt = t
    tt = tt.replace("…", "")

    # 소수점 보호: 9.0 / 3.14 안의 '.'은 남기고, 나머지 마침표만 제거
    tt = re.sub(r'(?<=\d)\.(?=\d)', '§DECIMAL§', tt)  # 9.0 -> 9§DECIMAL§0
    tt = re.sub(r"[.]+", "", tt)                      # 문장 끝 마침표 제거
    tt = tt.replace('§DECIMAL§', '.')                 # 소수점 복원

    # 느낌표는 제거(Polly 안정성), 공백 정리
    tt = re.sub(r"[!]+", "", tt)
    tt = re.sub(r"\s+", " ", tt).strip()

    # ── [분절: 담화표지/?, , / 콜론(시간 제외)] ────────────────────────────
    tmp = re.sub(r"(그리고|하지만|근데|그런데|그래서|그러니까|즉|특히|게다가|한편|반면에|다만|또한|결국|우선)\s*",
                 r"\g<0>§", tt)
    # 콤마: 숫자 밖의 콤마만 분절
    tmp = re.sub(r'(?<!\d),(?!\d)\s*', "§", tmp)
    # 물음표/중국권 구두점/세미콜론/가운뎃점
    tmp = re.sub(r'(?<=[，、;·?])\s*', "§", tmp)
    # 콜론은 시간이 아닐 때만 분절(예: 12:30 보호)
    tmp = re.sub(r'(?<!\d):(?!\d)\s*', "§", tmp)

    parts = [p.strip() for p in tmp.split("§") if p.strip()] or [tt]

    # ── [길이 보정: 너무 길면 안전한 공백 기준으로만 자르기] ────────────────
    chunks = []
    for p in parts:
        if len(p) <= 18:
            chunks.append(p)
        else:
            cur = p
            while len(cur) > 18:
                window = cur[:24]
                spaces = [m.start() for m in re.finditer(r"\s", window)]
                cut = spaces[-1] if spaces else 18
                chunks.append(cur[:cut].strip())
                cur = cur[cut:].strip()
            if cur:
                chunks.append(cur)

    # ── [스타일: 질문/경어/서술 어미에 따라 rate/pitch 살짝만] ────────────────
    def _style(s: str):
        s2 = s.strip()
        if s2.endswith("?"):
            return "162%", "+20%"
        if re.search(r"(입니다|니다|합니다|어요|예요)$", s2):
            return "152%", "+0%"
        if re.search(r"(이다|다|없습니다|못합니다|것이다)$", s2):
            return "138%", "-18%"
        return "150%", "+0%"

    ssml = []
    for i, c in enumerate(chunks):
        rate, pitch = _style(c)
        ssml.append(f'<prosody rate="{rate}" pitch="{pitch}">{_xml_escape(c)}</prosody>')
        if i != len(chunks) - 1:
            ssml.append('<break time="30ms"/>')

    # 연속 break 1회로 축약 후 리턴
    return re.sub(r'(?:<break\b[^>]*/>\s*){2,}', '<break time="30ms"/>', "".join(ssml)).strip()
