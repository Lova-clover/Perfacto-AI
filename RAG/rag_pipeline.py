import nest_asyncio
nest_asyncio.apply()

import asyncio
import time
import traceback

from .data_loader import load_documents
from .retriever_builder import build_retriever

async def get_retriever_from_source_async(source_type, source_input):
    """
    소스에서 문서를 로드하고 Retriever를 생성하는 전체 파이프라인을 실행합니다.
    """
    start_time = time.time()
    
    print("\n[1단계: 관련 콘텐츠 추출 시작]")
    documents = await load_documents(source_type, source_input)
    
    if not documents:
        print("처리할 문서를 찾지 못했습니다.")
        return None
    
    print(f"콘텐츠 추출 완료. (소요 시간: {time.time() - start_time:.2f}초)")
    
    retriever = build_retriever(documents)
    
    return retriever

def get_retriever_from_source(source_type, source_input):
    """
    비동기 함수인 get_retriever_from_source_async를 실행하고 결과를 반환합니다.
    """
    try:
        return asyncio.run(get_retriever_from_source_async(source_type, source_input))
    except Exception as e:
        print(f"Retriever 생성 중 오류 발생: {e}")
        traceback.print_exc()
        return None
