from langchain_core.documents import Document as LangChainDocument
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableMap, RunnableLambda, RunnablePassthrough
from langchain_groq import ChatGroq  # ✅ Groq import




def get_conversational_rag_chain(retriever, system_prompt):
    """
    최종적으로 생성된 문장 단위의 출처를 사용하여 답변을 생성하는 RAG 체인을 구성합니다.
    """
    llm = ChatGroq(model_name="openai/gpt-oss-120b", temperature=0.1)  # ✅ Groq LLM 설정

    
    rag_prompt_template = f"""{system_prompt}

Answer the user's request based *only* on the provided "Context".
If the context does not contain the answer, say you don't know.
Do not use any prior knowledge.

**Context:**
{{context}}

**User's Request:**
{{input}}

**Answer (in Korean):**
"""
    rag_prompt = ChatPromptTemplate.from_template(rag_prompt_template)
    
    def format_docs_with_metadata(docs: list[LangChainDocument]) -> str:
        """문서 리스트를 LLM 프롬프트 형식에 맞게 변환합니다."""
        if not docs:
            return "No context provided."
        
        sources = {}
        for doc in docs:
            source_url = doc.metadata.get("source", "Unknown Source")
            title = doc.metadata.get("title", "No Title")
            key = (source_url, title)
            if key not in sources:
                sources[key] = []
            sources[key].append(doc.page_content)

        formatted_string = ""
        for (source_url, title), sentences in sources.items():
            formatted_string += f"\n--- Source: {title} ({source_url}) ---\n"
            formatted_string += "\n".join(f"- {s}" for s in sentences)

        return formatted_string.strip()

    rag_chain = RunnableMap({
        "answer": (
            {"context": retriever | RunnableLambda(format_docs_with_metadata), "input": RunnablePassthrough()}
            | rag_prompt
            | llm
            | StrOutputParser()
        ),
        "source_documents": retriever  # 원본 문서를 그대로 반환
    })

    return rag_chain

def get_default_chain(system_prompt):
    prompt = ChatPromptTemplate.from_messages(
        [("system", system_prompt), ("user", "{question}")]
    )
    llm = ChatGroq(model_name="openai/gpt-oss-120b", temperature=0.7)  # ✅ Groq LLM
    return prompt | llm | StrOutputParser()
