import json
from typing import Any

from app.memory import MemoryStore


REFLECTION_HEADER = "[REFLECTION_REQUEST]"


def build_reflection_prompt(cases: list[dict[str, Any]]) -> str:
    lines = [
        REFLECTION_HEADER,
        "아래의 실제 해결/실패 사례를 비교해서 재사용 가능한 지식 규칙 후보를 추출하라.",
        "사례에 없는 사실을 만들지 말고, 서로 충돌하면 조건 차이를 규칙에 포함하라.",
        "반드시 JSON만 반환하라.",
        '{"rules":[{"rule":"규칙 문장","confidence":0.0}]}',
        "confidence는 현재 사례만 근거로 한 0~1 값이다.",
        "",
        "[CASES]",
    ]
    for case in cases:
        lines.extend(
            [
                f"Case #{case['id']} status={case['status']}",
                f"Problem: {case['problem']}",
                f"Solution: {case['solution']}",
                f"Outcome: {case.get('outcome') or ''}",
                "",
            ]
        )
    return "\n".join(lines)


def parse_rules(raw: str) -> list[dict[str, Any]]:
    text = raw.strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return []
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []

    rules = payload.get("rules", []) if isinstance(payload, dict) else []
    parsed: list[dict[str, Any]] = []
    for item in rules:
        if not isinstance(item, dict):
            continue
        rule = str(item.get("rule", "")).strip()
        if not rule:
            continue
        try:
            confidence = float(item.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        parsed.append({"rule": rule, "confidence": min(1.0, max(0.0, confidence))})
    return parsed


async def run_reflection(memory: MemoryStore, llm, limit: int = 50) -> dict[str, Any]:
    cases = memory.recent_cases(limit)
    if not cases:
        return {"case_count": 0, "created": [], "raw": ""}

    raw = await llm.generate(build_reflection_prompt(cases))
    rules = parse_rules(raw)
    created = []
    for rule in rules:
        knowledge_id = memory.add_knowledge(
            rule=rule["rule"],
            confidence=rule["confidence"],
            status="candidate",
        )
        created.append({"knowledge_id": knowledge_id, **rule})

    return {"case_count": len(cases), "created": created, "raw": raw}
