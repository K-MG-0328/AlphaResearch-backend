import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

from app.domains.macro.application.port.out.study_note_port import StudyNotePort
from app.domains.macro.application.port.out.macro_video_fetch_port import MacroVideoFetchPort
from app.domains.macro.application.port.out.risk_judgement_llm_port import (
    RiskJudgementLlmPort,
    RiskJudgementResult,
)
from app.domains.macro.application.response.market_risk_judgement_response import (
    MacroReferenceVideoResponse,
    MarketRiskJudgementResponse,
)
from app.domains.macro.domain.entity.macro_reference_video import MacroReferenceVideo
from app.domains.macro.domain.value_object.risk_status import RiskStatus

logger = logging.getLogger(__name__)

STUDY_CHANNEL_ID = "UC2-YdiOkgqWzIdDwCYW1utw"
LOOKBACK_DAYS = 7


class JudgeMarketRiskUseCase:
    def __init__(
        self,
        note_port: StudyNotePort,
        video_port: MacroVideoFetchPort,
        llm_port: RiskJudgementLlmPort,
    ):
        self._note_port = note_port
        self._video_port = video_port
        self._llm_port = llm_port

    async def execute(self) -> MarketRiskJudgementResponse:
        reference_date = date.today()
        published_after = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
        print(
            f"[macro.usecase] ▶ 시작 reference_date={reference_date.isoformat()} "
            f"published_after={published_after.isoformat()}"
        )

        note = await self._safe_read_note()
        print(f"[macro.usecase] Step1. 학습 노트 길이 = {len(note)}자")

        videos = await self._safe_fetch_videos(published_after)
        print(f"[macro.usecase] Step2. 최근 7일 영상 수 = {len(videos)}")

        note_available = bool(note and note.strip())
        has_context = note_available or bool(videos)

        note_context = self._build_note_context(note)
        video_context = self._build_video_context(videos)
        print(
            f"[macro.usecase] Step3. 컨텍스트 빌드 완료 "
            f"note_ctx_len={len(note_context)} video_ctx_len={len(video_context)} "
            f"has_context={has_context}"
        )

        # Step4a. contextual 을 먼저 결정해 최종 status 를 확정한다.
        print("[macro.usecase] Step4a. contextual LLM 호출")
        if has_context:
            contextual_status, contextual_reasons = await self._safe_judge(
                reference_date, note_context, video_context
            )
        else:
            contextual_status, contextual_reasons = RiskStatus.UNKNOWN, []
        print(
            f"[macro.usecase] Step4a. contextual={contextual_status.value}"
            f"({len(contextual_reasons)})"
        )

        # 통합 판단: [학습 기반] 에 우위를 둔다.
        # contextual 이 UNKNOWN 이 아니면 항상 contextual 결론을 최종 status 로 채택.
        primary_status_enum = (
            contextual_status if contextual_status != RiskStatus.UNKNOWN else RiskStatus.UNKNOWN
        )

        # Step4b. baseline 은 최종 status 에 정렬된 전문가 견해로 생성한다.
        print(
            f"[macro.usecase] Step4b. baseline LLM 호출 (aligned_to="
            f"{primary_status_enum.value})"
        )
        aligned = primary_status_enum if primary_status_enum != RiskStatus.UNKNOWN else None
        baseline_status, baseline_reasons = await self._safe_judge(
            reference_date, None, None, aligned_status=aligned
        )
        print(
            f"[macro.usecase] Step4b. baseline={baseline_status.value}"
            f"({len(baseline_reasons)})"
        )

        fallback_message = ""
        if not has_context:
            fallback_message = (
                "AlphaResearch AI 내부 매크로 데이터가 일시적으로 확보되지 않아 데이터 기반 판단은 "
                "유보하였습니다. 현재 화면에는 AlphaResearch AI 매크로 데스크의 일반 견해만 노출됩니다."
            )

        contextual_reasons_top = contextual_reasons[:3]
        baseline_reasons_top = baseline_reasons[:3]
        combined_reasons = list(baseline_reasons_top) + list(contextual_reasons_top)

        primary_status = primary_status_enum.value if primary_status_enum != RiskStatus.UNKNOWN else baseline_status.value

        response = MarketRiskJudgementResponse(
            reference_date=reference_date,
            status=primary_status,
            reasons=combined_reasons,
            contextual_status=contextual_status.value,
            contextual_reasons=contextual_reasons_top,
            baseline_status=baseline_status.value,
            baseline_reasons=baseline_reasons_top,
            reference_videos=[self._to_video_response(v) for v in videos],
            note_available=note_available,
            fallback_message=fallback_message,
        )
        print(
            f"[macro.usecase] ■ 완료 contextual={response.contextual_status}"
            f"({len(response.contextual_reasons)}) "
            f"baseline={response.baseline_status}({len(response.baseline_reasons)}) "
            f"videos={len(response.reference_videos)} note_available={response.note_available}"
        )
        return response

    async def _safe_judge(
        self,
        reference_date: date,
        note_context: Optional[str],
        video_context: Optional[str],
        aligned_status: Optional[RiskStatus] = None,
    ) -> Tuple[RiskStatus, List[str]]:
        mode = "baseline" if note_context is None and video_context is None else "contextual"
        try:
            result: RiskJudgementResult = await self._llm_port.judge(
                reference_date=reference_date,
                note_context=note_context,
                video_context=video_context,
                aligned_status=aligned_status,
            )
            return result.status, list(result.reasons)
        except Exception as exc:
            print(f"[macro.usecase]   └ ❌ {mode} LLM 실패: {exc}")
            logger.exception("[macro] %s LLM 판단 실패: %s", mode, exc)
            return RiskStatus.UNKNOWN, []

    async def _safe_read_note(self) -> str:
        try:
            return await self._note_port.read()
        except Exception as exc:
            print(f"[macro.usecase]   └ ⚠ 학습 노트 읽기 실패: {exc}")
            logger.warning("[macro] 학습 노트 읽기 실패: %s", exc)
            return ""

    async def _safe_fetch_videos(self, published_after: datetime) -> List[MacroReferenceVideo]:
        try:
            return await self._video_port.fetch_recent(
                channel_id=STUDY_CHANNEL_ID,
                published_after=published_after,
            )
        except Exception as exc:
            print(f"[macro.usecase]   └ ⚠ 유튜브 영상 수집 실패: {exc}")
            logger.warning("[macro] 유튜브 영상 수집 실패: %s", exc)
            return []

    @staticmethod
    def _build_note_context(note: str) -> str:
        if not note or not note.strip():
            return "(학습 노트 없음)"
        return note.strip()

    @staticmethod
    def _build_video_context(videos: List[MacroReferenceVideo]) -> str:
        if not videos:
            return "(최근 7일 이내 참고 영상 없음)"
        lines: List[str] = []
        for v in videos:
            description = (v.description or "").strip().replace("\n", " ")
            if len(description) > 600:
                description = description[:600] + "..."
            lines.append(
                f"- [{v.published_at.strftime('%Y-%m-%d')}] {v.title} (video_id={v.video_id})\n"
                f"  설명: {description}"
            )
        return "\n".join(lines)

    @staticmethod
    def _to_video_response(video: MacroReferenceVideo) -> MacroReferenceVideoResponse:
        return MacroReferenceVideoResponse(
            video_id=video.video_id,
            title=video.title,
            published_at=video.published_at,
            video_url=video.video_url,
        )
