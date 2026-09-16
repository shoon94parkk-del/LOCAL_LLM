import json
from typing import Any

from app.memory import MemoryStore


REFLECTION_HEADER = "[REFLECTION_REQUEST]"


def build_reflection_prompt(
    cases: list[dict[str, Any]], existing_knowledge: list[dict[str, Any]] | None = None
) -> str:
    lines = [
        REFLECTION_HEADER,
        "아래 실제 해결/실패 사례를 비교해서 재사용 가능한 지식 규칙 후보를 추출하라.",
        "사례에 없는 사실을 만들지 말고, 규칙마다 근거가 된 Case ID를 evidence_case_ids에 넣어라.",
        "기존 지식과 같은 의미면 duplicate, 보강하지만 별도 규칙이면 supports, 반대되면 conflicts, 관계가 없으면 new로 표시하라.",
        "duplicate/supports/conflicts인 경우 target_knowledge_id에 기존 Knowledge ID를 넣어라.",
        "충돌이 있으면 억지로 하나로 합치지 말고 conflicts로 남겨라.",
        "반드시 JSON 객체 하나만 반환하라.",
        '{"rules":[{"rule":"규칙 문장","confidence":0.0,"evidence_case_ids":[1,2],"relation":"new","target_knowledge_id":null}]}',
        "confidence는 현재 사례만 근거로 한 0~1 값이다.",
        "",
        "[EXISTING_KNOWLEDGE]",
    ]
    existing_knowledge = existing_knowledge or []
    if existing_knowledge:
        for item in existing_knowledge:
            lines.append(
                f"Knowledge #{item['id']} status={item['status']} confidence={item['confidence']:.2f} evidence={item['evidence_count']}: {item['rule']}"
            )
    else:
        lines.append("없음")

    lines.extend(["", "[CASES]"])
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
        evidence_case_ids = []
        raw_ids = item.get("evidence_case_ids", [])
        if isinstance(raw_ids, list):
            for value in raw_ids:
                try:
                    case_id = int(value)
                except (TypeError, ValueError):
                    continue
                if case_id > 0:
                    evidence_case_ids.append(case_id)
        relation = str(item.get("relation", "new")).strip().lower()
        if relation not in {"new", "duplicate", "supports", "conflicts"}:
            relation = "new"
        target = item.get("target_knowledge_id")
        try:
            target_knowledge_id = int(target) if target is not None else None
        except (TypeError, ValueError):
            target_knowledge_id = None
        parsed.append(
            {
                "rule": rule,
                "confidence": min(1.0, max(0.0, confidence)),
                "evidence_case_ids": sorted(set(evidence_case_ids)),
                "relation": relation,
                "target_knowledge_id": target_knowledge_id,
            }
        )
    return parsed


async def run_reflection(memory: MemoryStore, llm, limit: int = 50) -> dict[str, Any]:
    cases = memory.recent_cases(limit)
    if not cases:
        return {
            "case_count": 0,
            "created": [],
            "merged": [],
            "validated": [],
            "conflicted": [],
            "processed": [],
            "raw": "",
        }

    existing = memory.list_knowledge(40, ("candidate", "validated"))
    raw = await llm.generate(build_reflection_prompt(cases, existing))
    rules = parse_rules(raw)
    processed = []
    for item in rules:
        result = memory.upsert_knowledge_candidate(
            rule=item["rule"],
            confidence=item["confidence"],
            evidence_case_ids=item["evidence_case_ids"],
            relation=item["relation"],
            target_knowledge_id=item["target_knowledge_id"],
        )
        processed.append(result)

    created = [item for item in processed if item["action"] == "created"]
    merged = [item for item in processed if item["action"] == "merged"]
    validated = [item for item in processed if item["status"] == "validated"]
    conflicted = [item for item in processed if item["status"] == "conflicted"]
    return {
        "case_count": len(cases),
        "created": created,
        "merged": merged,
        "validated": validated,
        "conflicted": conflicted,
        "processed": processed,
        "raw": raw,
    }
