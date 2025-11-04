import os
import tempfile
from llama_parse import LlamaParse

# LlamaParse를 사용하기 위한 parser 객체 초기화
parser = LlamaParse(result_type="markdown")

def get_documents_from_files(uploaded_files):
    """
    업로드된 파일 리스트를 LlamaParse를 사용하여 동기적으로 로드하고 구조화합니다.
    """
    all_documents = []
    
    # 파일을 하나씩 동기적으로 파싱
    for uploaded_file in uploaded_files:
        temp_file_path = None
        try:
            # 임시 파일 생성
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                temp_file_path = tmp_file.name

            # 동기 파싱 실행 (load_data는 document list를 반환)
            print(f"'{uploaded_file.name}' 파일 파싱 중...")
            documents = parser.load_data(temp_file_path)
            all_documents.extend(documents)
            print(f"'{uploaded_file.name}' 파일 파싱 완료.")

        except Exception as e:
            print(f"'{uploaded_file.name}' 파일 처리 중 오류 발생: {e}")
        finally:
            # 처리 후 임시 파일 삭제
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            
    return all_documents