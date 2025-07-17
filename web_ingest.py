import requests
from bs4 import BeautifulSoup
from googlesearch import search
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import os
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_core.documents import Document

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

def filter_noise(text):
    ad_keywords = ["구매", "배너", "후원", "제휴", "마케팅", "광고"]
    lines = text.split("\n")
    return "\n".join([
        line.strip() for line in lines
        if not any(word in line for word in ad_keywords) and len(line.strip()) > 30
    ])

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