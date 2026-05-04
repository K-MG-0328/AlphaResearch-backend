"""LangGraph Investment Workflow 의 stateless helper 함수.

워크플로우 본체에서 ``@staticmethod`` 였던 함수들을 free function 으로 분리.
self 미사용이라 1:1 이동. 동작 변경 0.
"""

from typing import Any


def format_retrieval_text(retrieved_data: list[dict[str, Any]]) -> str:
    """retrieved_data 리스트를 required_data 순서 그대로 포맷팅하여 하나의 텍스트로 반환한다.

    Analysis/Synthesis 노드에서 LLM 컨텍스트 조립 시 활용할 수 있다.
    """
    parts: list[str] = []
    for entry in retrieved_data:
        source = entry["source"]
        if entry["status"] != "ok":
            parts.append(f"[{source}] 수집 실패: {entry.get('error', '알 수 없는 오류')}")
            continue
        items = entry.get("items", [])
        if not items:
            parts.append(f"[{source}] 수집된 항목 없음")
            continue
        if source == "뉴스":
            lines = [item.get("summary_text") or item.get("title", "") for item in items[:5]]
            parts.append(f"[{source}]\n" + "\n".join(f"- {line}" for line in lines if line))
        elif source == "유튜브":
            lines = [
                f"[{item.get('channel_name', '')}] {item.get('title', '')}"
                for item in items[:5]
            ]
            parts.append(f"[{source}]\n" + "\n".join(f"- {line}" for line in lines if line))
        else:
            parts.append(f"[{source}] {len(items)}건 수집")
    return "\n\n".join(parts)


def confidence_label(confidence: float) -> str:
    """confidence 수치를 사람이 읽기 쉬운 확신 수준 레이블로 변환한다."""
    if confidence >= 0.7:
        return "높은 확신"
    if confidence >= 0.4:
        return "일정 수준의 가능성"
    return "불확실성이 높은 상태"


def print_synthesis_result(verdict: str, confidence: float, body: str) -> None:
    """최종 응답 요약을 콘솔에 pretty-print 한다."""
    preview = body[:120].replace("\n", " ")
    print(
        f"\n[SynthesisAgent] ══ 최종 응답 ══════════════════════════════\n"
        f"  verdict    : {verdict}\n"
        f"  confidence : {confidence:.4f} "
        f"({confidence_label(confidence)})\n"
        f"  본문 미리보기: {preview}...\n"
        f"  전체 길이  : {len(body)}자\n"
        f"  ══════════════════════════════════════════════════════"
    )
