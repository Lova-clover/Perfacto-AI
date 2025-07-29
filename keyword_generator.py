import requests
import json
import time
from typing import List, Dict, Tuple
import re
import os
from datetime import datetime
import streamlit as st

# Groq API 설정 (질문 세분화용)
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
# =============================================================================

class QuestionSegmentationSystem:
    def __init__(self, model_name: str = "llama3-8b-8192"):
        """
        질문 세분화 시스템 초기화 (Groq Llama-3-8B 모델 사용)
        
        Args:
            model_name: 사용할 모델명 (기본값: llama3-8b-8192)
        """
        self.model_name = model_name
        
        # Groq API 설정
        self.groq_api_key = GROQ_API_KEY
        self.groq_api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.groq_headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }
        
        print(f"✅ Groq API 설정 완료 (모델: {model_name})")
        
        # 성능 측정을 위한 변수들
        self.response_times = []
        self.segmented_questions = []
        
    def segment_question(self, user_question: str, num_segments: int = 3) -> Tuple[List[str], float]:
        """
        사용자 질문을 세분화하여 검색용 질문들로 변환 (Llama-3 8B 모델 사용)
        
        Args:
            user_question: 사용자 질문
            num_segments: 생성할 세분화 질문 수
            
        Returns:
            (세분화된 질문 리스트, 응답 시간)
        """
        start_time = time.time()
        
        try:
            # Groq API를 사용한 질문 세분화
            messages = [
                {
                    "role": "system",
                    "content": f"당신은 질문을 세분화하는 전문가입니다. 주어진 질문을 {num_segments}개의 서로 다른 관점의 검색 질문으로 변환해주세요. 각 질문은 자연스러운 한국어로 작성하고, 검색에 최적화된 형태여야 합니다."
                },
                {
                    "role": "user", 
                    "content": f"다음 질문을 {num_segments}개의 세분화된 검색 질문으로 변환해주세요: {user_question}"
                }
            ]
            
            payload = {
                "model": self.model_name,
                "messages": messages,
                "max_tokens": 300,
                "temperature": 0.7,
                "top_p": 0.9
            }
            
            response = requests.post(self.groq_api_url, headers=self.groq_headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                generated_text = result['choices'][0]['message']['content']
                print(f"✅ Groq API 응답 성공")
            else:
                print(f"Groq API 오류: {response.status_code} {response.reason}")
                print(f"응답 내용: {response.text}")
                # Groq 실패 시 기본 규칙 기반 세분화로 fallback
                segmented_questions = self._fallback_segmentation(user_question, num_segments)
                end_time = time.time()
                response_time = end_time - start_time
                return segmented_questions[:num_segments], response_time

            # 생성된 텍스트에서 질문들 추출
            segmented_questions = self._extract_questions_from_response(generated_text, num_segments)
            
            # 질문이 부족하면 기본 질문들로 보완
            if len(segmented_questions) < num_segments:
                keywords = self._extract_keywords(user_question)
                if len(keywords) >= 2:
                    basic_questions = [
                        f"{keywords[0]}가 {keywords[1]}를 못하는 이유",
                        f"{keywords[0]}가 {keywords[1]}를 못하는 원리"
                    ]
                    for q in basic_questions:
                        if q not in segmented_questions and len(segmented_questions) < num_segments:
                            segmented_questions.append(q)
                    
        except Exception as e:
            print(f"세분화 오류: {e}")
            print(f"오류 타입: {type(e).__name__}")
            import traceback
            print(f"상세 오류: {traceback.format_exc()}")
            # 오류 발생 시 기본 규칙 기반 세분화로 fallback
            segmented_questions = self._fallback_segmentation(user_question, num_segments)
        
        end_time = time.time()
        response_time = end_time - start_time
        
        return segmented_questions[:num_segments], response_time
    
    def _extract_questions_from_response(self, response_text: str, num_segments: int) -> List[str]:
        """
        LLM 응답에서 질문들을 추출
        
        Args:
            response_text: LLM이 생성한 텍스트
            num_segments: 필요한 질문 수
            
        Returns:
            추출된 질문 리스트
        """
        # 줄바꿈으로 분리
        lines = response_text.strip().split('\n')
        
        questions = []
        for line in lines:
            line = line.strip()
            if line and ('?' in line or '?' in line or '는' in line or '가' in line):
                # 질문 형태로 보이는 텍스트만 추출
                if len(line) > 5 and len(line) < 100:
                    questions.append(line)
        
        # 중복 제거
        unique_questions = []
        for q in questions:
            if q not in unique_questions:
                unique_questions.append(q)
        
        return unique_questions[:num_segments]
    
    def _fallback_segmentation(self, user_question: str, num_segments: int) -> List[str]:
        """
        API 실패 시 사용할 기본 규칙 기반 세분화
        
        Args:
            user_question: 사용자 질문
            num_segments: 필요한 질문 수
            
        Returns:
            세분화된 질문 리스트
        """
        keywords = self._extract_keywords(user_question)
        segmented_questions = []
        
        if len(keywords) >= 2:
            # 기본 질문들 생성 (문법 수정)
            basic_questions = [
                f"{keywords[0]}가 {keywords[1]}를 못하는 이유",
                f"{keywords[0]}가 {keywords[1]}를 못하는 원리",
                f"{keywords[0]}와 {keywords[1]}의 관계"
            ]
            
            for q in basic_questions:
                if len(segmented_questions) < num_segments:
                    segmented_questions.append(q)
        
        # 질문이 부족하면 키워드 기반으로 보완
        if len(segmented_questions) < num_segments:
            for keyword in keywords:
                if len(segmented_questions) < num_segments:
                    question = f"{keyword}에 대한 정보"
                    if question not in segmented_questions:
                        segmented_questions.append(question)
        
        return segmented_questions[:num_segments]
    
    def _extract_keywords(self, question: str) -> List[str]:
        """
        질문에서 핵심 키워드 추출
        
        Args:
            question: 원본 질문
            
        Returns:
            추출된 키워드 리스트
        """
        # 불용어 및 조사 제거
        stop_words = ['왜', '어떻게', '무엇', '뭐', '어떤', '언제', '어디서', '누가', '이유', '방법', '전략', '영향', '결과']
        particles = ['은', '는', '이', '가', '을', '를', '의', '에', '에서', '로', '으로', '와', '과', '도', '만', '부터', '까지']
        
        # 특수문자 제거 및 단어 분리
        words = re.findall(r'[가-힣a-zA-Z]+', question)
        
        # 불용어 및 조사 제거 및 길이 필터링
        keywords = []
        for word in words:
            # 조사가 포함된 단어에서 조사 제거
            clean_word = word
            for particle in particles:
                if clean_word.endswith(particle):
                    clean_word = clean_word[:-len(particle)]
                    break
            
            if clean_word not in stop_words and len(clean_word) > 1:
                keywords.append(clean_word)
        
        # 빈도수 기반 정렬 (간단한 구현)
        keyword_freq = {}
        for word in keywords:
            keyword_freq[word] = keyword_freq.get(word, 0) + 1
        
        # 빈도수 순으로 정렬
        sorted_keywords = sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)
        
        return [word for word, freq in sorted_keywords[:5]]  # 상위 5개 키워드 반환

    def print_segmented_questions(self, search_questions: List[str]):
        """
        세분화된 질문들을 print로 출력
        
        Args:
            search_questions: 출력할 세분화된 질문들
        """
        print(f"\n📝 세분화된 질문들:")
        print("=" * 60)
        for i, question in enumerate(search_questions, 1):
            print(f"{i}. {question}")
        print("=" * 60)

    def process_single_question(self, user_question: str) -> Dict:
        """
        단일 사용자 질문 처리 (세분화 + 출력)
        
        Args:
            user_question: 사용자 질문
            
        Returns:
            처리 결과 딕셔너리
        """
        print(f"\n🔍 질문: {user_question}")
        print("=" * 60)
        
        # 1. 질문 세분화
        segmented_questions, response_time = self.segment_question(user_question)
        
        if not segmented_questions:
            print("❌ 세분화 실패")
            return {}
        
        print(f"✅ 세분화 완료 ({response_time:.2f}초)")
        
        # 2. 세분화된 질문들 출력
        self.print_segmented_questions(segmented_questions)
        
        # 결과 반환
        return {
            "원본 질문": user_question,
            "세분화된 질문": segmented_questions,
            "응답시간(초)": round(response_time, 2)
        }

def main():
    """메인 실행 함수"""
    print("🔍 질문 세분화 시스템")
    print("=" * 60)
    
    # 시스템 초기화
    try:
        system = QuestionSegmentationSystem()
        print("✅ 시스템 초기화 완료")
        print(f"📝 사용할 모델: {system.model_name}")
    except ValueError as e:
        print(f"❌ 초기화 오류: {e}")
        return
    
    # 직접 질문 입력
    user_question = input("\n🔍 질문을 입력하세요: ").strip()
    if user_question:
        result = system.process_single_question(user_question)
        if result:
            print(f"\n✅ 처리 완료! 응답시간: {result['응답시간(초)']}초")
            print("\n👋 시스템을 종료합니다.")
    else:
        print("❌ 질문을 입력해주세요.")
        print("👋 시스템을 종료합니다.")

if __name__ == "__main__":
    main() 