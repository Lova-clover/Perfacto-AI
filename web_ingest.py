import requests
from bs4 import BeautifulSoup
from googlesearch import search
from sentence_transformers import SentenceTransformer # 현재 사용되지 않음
import faiss # 현재 사용되지 않음
import numpy as np # 현재 사용되지 않음
import os
from langchain_community.vectorstores import FAISS # 현재 사용되지 않음
from langchain_google_genai import GoogleGenerativeAIEmbeddings # 현재 사용되지 않음
from langchain_core.documents import Document
import re


def get_links(query, num=30):
    return [
        url for url in search(query, num_results=num)
        if any(domain in url for domain in ["blog", "wiki", "naver", "tistory"])
    ]

def clean_html(url):
    try:
        html = requests.get(url, timeout=10).text
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "footer", "nav", "form", "header"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    except:
        return ""

def filter_noise(html_content):
    """
    HTML 내용에서 노이즈(스크립트, 스타일, 헤더, 푸터, 내비게이션, 광고, 봇 방지 페이지 등)를 제거하고
    실제 텍스트 콘텐츠만 추출합니다.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, 'html.parser')

    # 스크립트 및 스타일 태그 제거
    for script_or_style in soup(["script", "style"]):
        script_or_style.decompose()

    # 특정 HTML 태그 제거 (헤더, 푸터, 내비게이션, 폼, 버튼, 이미지, 아이콘 등)
    for tag_name in ["header", "footer", "nav", "aside", "form", "button", "input", "select", "textarea", "img", "svg", "iframe", "noscript"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()
            
    # 클래스나 ID로 특정 노이즈 영역 제거 (예: 광고, 사이드바, 팝업, 쿠키 배너)
    unwanted_classes = ["sidebar", "ad", "advertisement", "popup", "modal", "cookie-banner", "menu", "nav-menu", "footer-links", "header-links"]
    for unwanted_class in unwanted_classes:
        for tag in soup.find_all(class_=re.compile(r'\b' + re.escape(unwanted_class) + r'\b')): # 부분 일치 대신 단어 경계 일치
            tag.decompose()
    
    unwanted_ids = ["header", "footer", "navbar", "sidebar", "ads", "cookie-notice", "consent-banner"]
    for unwanted_id in unwanted_ids:
        if soup.find(id=unwanted_id):
            soup.find(id=unwanted_id).decompose()

    # 텍스트 추출
    text = soup.get_text()

    # 여러 공백, 탭, 줄바꿈을 하나의 공백으로 축소
    text = re.sub(r'\s+', ' ', text).strip()

    # 특정 노이즈 패턴 제거 (특히 봇 방지 페이지, 위키백과 특유의 메타데이터 등)
    noise_patterns = [
        # 봇 방지/보안 검사 메시지
        r"Just a moment\.\.\. Enable JavaScript and cookies to continue\.\.\.",
        r"Please wait while we verify your access\.",
        r"Checking your browser before accessing",
        r"This process is automatic\. Your browser will redirect to your requested content shortly\.",
        r"DDoS protection by Cloudflare",
        r"You are being redirected\.",
        r"Click here if you are not redirected\.",
        r"Verify you are human",
        r"Are you a robot\?",
        r"To continue, please type the characters below:",
        r"Loading\.\.\.",
        r"Please enable cookies to use this site\.",

        # 일반적인 웹사이트 푸터/헤더/UI 요소
        r"Privacy Policy",
        r"Terms of Service",
        r"Cookie Policy",
        r"All Rights Reserved",
        r"Copyright \d{4}(-\d{4})?", # 예: Copyright 2023, Copyright 2023-2024
        r"Skip to content",
        r"Toggle navigation",
        r"Search for:",
        r"Subscribe to our newsletter",
        r"Enter your email",
        r"Sign Up",
        r"Log In",
        r"Register",
        r"Contact Us",
        r"About Us",
        r"Home",
        r"Blog",
        r"Categories",
        r"Tags",
        r"Recent Posts",
        r"Related Articles",
        r"Read More",
        r"Share this article",
        r"Comments",
        r"View All",
        r"Back to Top",
        r"Powered by",

        # 위키백과 특유의 노이즈
        r"\[\d+\]", # [1], [2] 와 같은 각주 번호
        r"\[edit\]", # 위키백과 편집 링크
        r"\[citation needed\]", # 위키백과 인용 필요
        r"\[hide\]", # 위키백과 숨기기
        r"\[show\]", # 위키백과 보이기
        r"\(listen\)", # 오디오 링크
        r"\(help\)", # 도움말 링크
        r"\(file\)", # 파일 링크
        r"\(PDF\)", # PDF 링크
        r"\(DOC\)", # DOC 링크
        r"\(TXT\)", # TXT 링크
        r"\(URL\)", # URL 링크
        r"전거 통제 : 국가 미국 이스라엘 원본 주소", # 위키백과 하단 메타데이터
        r"분류 : 체스 규칙 숨은 분류: 참조 오류가 있는 문서 존재하지 않는 문서를 대상으로 하는 hatnote 틀을 사용하는 문서 Harv 및 Sf...", # 위키백과 분류
        r"이 문서는 체스에 관한 토막글입니다\. 서로 돕고 도와서 위키백과를 문서로 만들 수 있습니다\.", # 위키백과 토막글 안내
        r"이 문서는 체스에 관한 문서를 다룹니다\.", # 위키백과 서두 문구
        r"이 문서에는 다음 언어로 된 본문이 포함되어 있습니다\.", # 위키백과 언어 링크
        r"이 문서는 \d{4}년 \d{1,2}월 \d{1,2}일에 마지막으로 편집되었습니다\.", # 위키백과 편집일
        r"이 문서는 크리에이티브 커먼즈 저작자표시-동일조건변경허락 \d.\d 국제 라이선스에 따라 이용할 수 있습니다\.", # 위키백과 라이선스
        r"Wikipedia®는 등록 상표입니다\.", # 위키백과 상표
        r"위키백과, 우리 모두의 백과사전\.", # 위키백과 슬로건
        r"Jump to navigation",
        r"Jump to search",
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

    # 여러 줄 바꿈을 하나의 공백으로 다시 축소 (regex 적용 후 발생할 수 있는 추가 공백 처리)
    text = re.sub(r'\s+', ' ', text).strip()

    # 너무 짧거나 내용이 없는 텍스트는 무시
    if len(text) < 100: # 최소 텍스트 길이 기준을 50에서 100으로 상향 (더 많은 노이즈 제거)
        return ""

    return text

def save_texts(text_list, filename):
    with open(filename, "w", encoding="utf-8") as f:
        for i, t in enumerate(text_list):
            f.write(f"[문서 {i+1}]\n{t}\n\n")

def embed_and_save(texts, output_dir):
    print("[+] 문서 벡터화 및 인덱싱 중...")

    # HuggingFaceEmbeddings 대신 GoogleGenerativeAIEmbeddings 사용
    embedding = GoogleGenerativeAIEmbeddings(
        model="models/embedding-001" # Google의 기본 임베딩 모델
        # API 키는 Streamlit secrets에 GOOGLE_API_KEY로 설정되어 있어야 합니다.
    )
    
    vectorstore = FAISS.from_texts(texts, embedding)

    vectorstore.save_local(output_dir)
    print(f"[+] FAISS 인덱스 저장 완료: {output_dir}")

def full_web_ingest(query): # output_dir 매개변수 제거
    try:
        print(f"[+] '{query}' 검색 중...")
        urls = get_links(query)
        if not urls:
            return [], "검색 결과가 없습니다." # 문서 리스트와 에러 메시지 반환

        cleaned_texts_with_urls = []
        for url in urls:
            raw_text = clean_html(url)
            filtered_text = filter_noise(raw_text)
            if filtered_text:
                # Langchain Document 객체로 변환하고 URL을 metadata에 추가
                doc = Document(page_content=filtered_text, metadata={"source": url, "query": query})
                cleaned_texts_with_urls.append(doc)

        if not cleaned_texts_with_urls:
            return [], "유효한 웹 문서를 찾을 수 없습니다." # 문서 리스트와 에러 메시지 반환

        print(f"[+] {len(cleaned_texts_with_urls)}개의 웹 문서 수집 및 정리 완료.")

        # 여기서는 FAISS 인덱스를 저장하지 않습니다.
        # 문서 리스트 자체를 반환하여 main.py에서 파일 문서와 통합합니다.
        return cleaned_texts_with_urls, None # 문서 리스트와 에러 없음 반환

    except Exception as e:
        print(f"[-] 웹 수집 중 오류 발생: {e}")
        return [], f"웹 수집 중 오류 발생: {e}" # 빈 문서 리스트와 에러 메시지 반환