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
    HTML 내용에서 노이즈(스크립트, 스타일, 헤더, 푸터, 내비게이션, 광고 등)를 제거하고
    실제 텍스트 콘텐츠만 추출합니다.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, 'html.parser')

    # 스크립트 및 스타일 태그 제거
    for script_or_style in soup(["script", "style"]):
        script_or_style.decompose()

    # 특정 HTML 태그 제거 (헤더, 푸터, 내비게이션, 광고 등)
    # 웹사이트 구조에 따라 추가하거나 제거할 수 있습니다.
    for tag_name in ["header", "footer", "nav", "aside", "form", "button", "input", "select", "textarea", "img", "svg"]:
        for tag in soup.find_all(tag_name):
            tag.decompose()
            
    # 클래스나 ID로 특정 노이즈 영역 제거 (예: 광고, 사이드바)
    # 실제 웹사이트를 분석하여 필요한 클래스/ID를 추가하세요.
    for unwanted_class in ["sidebar", "ad", "advertisement", "popup", "modal", "cookie-banner"]:
        for tag in soup.find_all(class_=unwanted_class):
            tag.decompose()
    
    for unwanted_id in ["header", "footer", "navbar", "sidebar", "ads"]:
        for tag in soup.find_all(id=unwanted_id):
            tag.decompose()

    # 텍스트 추출
    text = soup.get_text()

    # 여러 공백, 탭, 줄바꿈을 하나의 공백으로 축소
    text = re.sub(r'\s+', ' ', text).strip()

    # 특정 노이즈 패턴 제거 (예: "Just a moment...", "Enable JavaScript and cookies to continue...")
    # 이 부분은 특히 중요합니다.
    noise_patterns = [
        r"Just a moment\.\.\. Enable JavaScript and cookies to continue\.\.\.",
        r"Please wait while we verify your access\.",
        r"Checking your browser before accessing",
        r"This process is automatic\. Your browser will redirect to your requested content shortly\.",
        r"DDoS protection by Cloudflare",
        r"You are being redirected\.",
        r"Click here if you are not redirected\.",
        r"Privacy Policy", # 일반적인 푸터 링크
        r"Terms of Service",
        r"Cookie Policy",
        r"All Rights Reserved",
        r"Copyright \d{4}",
        r"Skip to content",
        r"Toggle navigation",
        r"Search for:",
        r"Subscribe to our newsletter",
        r"Enter your email",
        r"Sign Up",
        r"Log In",
        r"Register",
        r"\[\d+\]", # [1], [2] 와 같은 각주 번호
        r"\[edit\]", # 위키피디아 편집 링크
        r"\[citation needed\]", # 위키피디아 인용 필요
        r"\[hide\]", # 위키피디아 숨기기
        r"\[show\]", # 위키피디아 보이기
        r"\(listen\)", # 오디오 링크
        r"\(help\)", # 도움말 링크
        r"\(file\)", # 파일 링크
        r"\(PDF\)", # PDF 링크
        r"\(DOC\)", # DOC 링크
        r"\(TXT\)", # TXT 링크
        r"\(URL\)", # URL 링크
        r"[\u0080-\u00FF]", # 비 ASCII 문자 중 일부 (더 정교한 필터링 필요시)
    ]
    for pattern in noise_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE).strip()

    # 너무 짧거나 내용이 없는 텍스트는 무시
    if len(text) < 50: # 최소 텍스트 길이 설정 (조절 가능)
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