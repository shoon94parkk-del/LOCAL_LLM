class MockLLM:
    async def generate(self, prompt: str) -> str:
        if "[AGENT_REQUEST]" in prompt:
            import json
            payload = json.loads(prompt[prompt.index('{"goal":'):])
            if not payload['steps']:
                return json.dumps({"plan": "관련 기억을 검색합니다", "tool": "memory_search", "arguments": {"query": payload['goal']}})
            return json.dumps({"tool": "finish", "arguments": {"answer": "[MOCK] 기억 검색 도구 실행을 완료했습니다. 실제 분석에는 회사 GLM 연결이 필요합니다."}})
        if "[REFLECTION_REQUEST]" in prompt:
            return (
                '{"rules":[{"rule":"실제 해결/실패 결과를 함께 비교해 다음 대응 조건을 결정한다.",'
                '"confidence":0.7}]}'
            )

        question = prompt.split("[현재 질문]", 1)[-1].split("[관련 과거 기록]", 1)[0].strip()
        return (
            "[MOCK GLM RESPONSE]\n"
            f"질문: {question}\n\n"
            "실제 회사 GLM 연결 전 테스트 응답입니다. "
            "메모리 검색과 저장 흐름이 정상인지 확인할 수 있습니다."
        )
