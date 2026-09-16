class MockLLM:
    async def generate(self, prompt: str) -> str:
        question = prompt.split("[현재 질문]", 1)[-1].split("[관련 과거 기록]", 1)[0].strip()
        return (
            "[MOCK GLM RESPONSE]\n"
            f"질문: {question}\n\n"
            "실제 회사 GLM 연결 전 테스트 응답입니다. "
            "메모리 검색과 저장 흐름이 정상인지 확인할 수 있습니다."
        )
