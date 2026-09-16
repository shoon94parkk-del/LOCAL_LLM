from typing import Any


SYSTEM_GUIDE = """당신은 사내 엔지니어링 문제 해결 보조 AI다.
제공된 과거 기록은 참고자료이며 사실 여부를 다시 판단해야 한다.
과거 사례와 현재 조건이 다르면 그 차이를 명시한다.
근거가 부족하면 추측하지 말고 부족하다고 말한다.
가능하면 원인 가설, 확인 방법, 다음 행동을 분리해서 답한다.
"""


def build_prompt(question: str, memories: list[dict[str, Any]]) -> str:
    chunks = [SYSTEM_GUIDE.strip(), "", "[현재 질문]", question.strip()]

    if memories:
        chunks.extend(["", "[관련 과거 기록]"])
        for idx, item in enumerate(memories, start=1):
            chunks.append(
                f"\n#{idx} source={item['source']} id={item['source_id']}\n"
                f"제목: {item['title']}\n"
                f"내용: {item['body']}"
            )
    else:
        chunks.extend(["", "[관련 과거 기록]", "검색된 기록 없음"])

    chunks.extend(
        [
            "",
            "[응답 규칙]",
            "1. 과거 기록을 그대로 정답으로 취급하지 말 것",
            "2. 현재 질문과 직접 관련된 기록만 활용할 것",
            "3. 확실하지 않은 내용은 '확실하지 않음'으로 표시할 것",
            "4. 필요하면 다음 실험 또는 확인 항목을 제안할 것",
        ]
    )
    return "\n".join(chunks)
