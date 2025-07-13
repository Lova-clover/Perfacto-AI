import requests
from bs4 import BeautifulSoup
from googlesearch import search
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import os
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings

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

def full_web_ingest(query, output_dir="output"):
    urls = get_links(query)
    texts = []
    for url in urls:
        raw = clean_html(url)
        filtered = filter_noise(raw)
        if len(filtered) > 300:
            texts.append(filtered)

    if not texts:
        return None, None, "충분한 문서를 수집하지 못했습니다."

    os.makedirs(output_dir, exist_ok=True)
    text_path = os.path.join(output_dir, "result_text.txt")
    embed_and_save(texts, output_dir)

    return text_path, output_dir, None