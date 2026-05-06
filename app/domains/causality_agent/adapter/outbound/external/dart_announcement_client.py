"""DART 한국 공시 → AnnouncementItem 변환 (OKR 1 P1.5).

causality_agent 의 collect_non_economic_node 가 한국 종목일 때 호출.
disclosure 도메인의 `DartDisclosureApiClient` 를 재사용해 DART list.json 을
조회한 뒤 timeline_response 와 동일한 형식의 dict 배열로 반환.

매핑 정책:
- DART pblntf_ty/detail_ty 는 코드만 있고 한글 라벨은 report_nm 에 들어감
- 가장 안정적인 분류 키는 report_nm 한글 키워드. AnnouncementEventType 매핑 시
  사용자가 차트 카드에서 의미 있게 인식할 수 있는 type 으로 환원
- 매칭 실패 시 MAJOR_EVENT fallback (KR3 안전장치 — 환각보다 보수적 fallback)
"""
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.domains.causality_agent.application.port.out.disclosure_ports import (
    DartAnnouncementPort,
)
from app.domains.dashboard.domain.entity.announcement_event import AnnouncementEventType
from app.domains.disclosure.adapter.outbound.external.dart_disclosure_api_client import (
    DartDisclosureApiClient,
)

logger = logging.getLogger(__name__)


def _classify_dart_type(report_nm: str, pblntf_ty: str) -> AnnouncementEventType:
    """DART 공시 분류 — report_nm 한글 키워드 기반.

    DART 공시 유형 코드 (pblntf_ty): A(정기) / B(주요사항) / C(발행) / D(지분) /
    E(기타) / F(외부감사) / I(거래소) — 코드만으론 세부 분류 불가.
    report_nm("연결재무제표 기준 영업(잠정)실적(공정공시)") 등 한글 키워드 매칭.

    분기 순서 주의: "정정"·"사채" 같은 강한 신호를 더 일반적인 키워드보다 먼저 매칭.
    예: "신주인수권부사채권발행결정" 의 "인수" 가 합병으로 잡히면 안 됨 → 사채 먼저.
    """
    name = report_nm or ""

    # ① 정정 — 다른 키워드 매칭보다 우선 (회계 이슈 가능성)
    if "정정" in name:
        return AnnouncementEventType.ACCOUNTING_ISSUE

    # ② 잠정실적 (정기실적과 별개 — 한국 특화)
    if "잠정실적" in name or ("공정공시" in name and "실적" in name):
        return AnnouncementEventType.EARNINGS_GUIDANCE

    # ③ 채권 / 사채 — "신주인수권부사채" 의 "인수" 가 합병 분류 잡히지 않도록 먼저
    if any(k in name for k in ("회사채", "전환사채", "신주인수권부사채", "교환사채")):
        return AnnouncementEventType.DEBT_ISSUANCE

    # ④ 한국 시장 특화
    if "자기주식" in name or "자사주" in name:
        return AnnouncementEventType.TREASURY_STOCK
    if "액면분할" in name or "액면병합" in name:
        return AnnouncementEventType.STOCK_SPLIT
    if "유상증자" in name:
        return AnnouncementEventType.RIGHTS_OFFERING
    if "무상증자" in name or "주식배당" in name:
        return AnnouncementEventType.BONUS_ISSUE

    # ⑤ 정기 실적 (사업/분기/반기보고서) — 정정·잠정실적 분기 후
    if pblntf_ty == "A" or any(k in name for k in ("사업보고서", "분기보고서", "반기보고서")):
        return AnnouncementEventType.EARNINGS_RELEASE

    # ⑥ 합병/인수/분할
    if "합병" in name or "인수" in name or "분할" in name:
        return AnnouncementEventType.MERGER_ACQUISITION

    # ⑦ 거래정지 / 상장폐지 / 관리종목
    if any(k in name for k in ("거래정지", "상장폐지", "관리종목", "투자주의", "투자위험")):
        return AnnouncementEventType.CRISIS

    # ⑧ 정관 / 주주총회 / 임원
    if "정관" in name:
        return AnnouncementEventType.ARTICLES_AMENDMENT
    if "주주총회" in name:
        return AnnouncementEventType.SHAREHOLDER_MEETING
    if "대표이사" in name or "임원" in name or "이사회" in name:
        return AnnouncementEventType.MANAGEMENT_CHANGE

    # ⑨ 계약
    if "계약" in name or "수주" in name:
        return AnnouncementEventType.CONTRACT

    return AnnouncementEventType.MAJOR_EVENT


def _parse_rcept_dt(rcept_dt: str) -> Optional[date]:
    """DART rcept_dt 형식 'YYYYMMDD' → date. 형식 불일치 시 None."""
    try:
        return datetime.strptime(rcept_dt, "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _build_dart_url(rcept_no: str) -> str:
    """rcept_no(접수번호) 로 DART 공시 상세 페이지 URL 구성."""
    return f"https://dart.fss.or.kr/dsaf001/main.do?rceptNo={rcept_no}"


class DartAnnouncementClient(DartAnnouncementPort):
    """DART 공시 → causality_agent state 의 announcements dict 변환."""

    def __init__(self, dart_client: Optional[DartDisclosureApiClient] = None):
        self._dart_client = dart_client or DartDisclosureApiClient()

    async def fetch_announcements(
        self,
        ticker: str,
        corp_code: str,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """기간 내 corp_code 공시 → AnnouncementItem 호환 dict 배열.

        반환 dict 키: date, type, title, source="dart", url, items_str=None.
        DART API 실패 시 빈 배열 (timeline 전체 죽지 않도록 graceful).
        """
        if not corp_code:
            return []

        try:
            items = await self._dart_client.fetch_all_pages(
                bgn_de=start_date.strftime("%Y%m%d"),
                end_de=end_date.strftime("%Y%m%d"),
                corp_code=corp_code,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[DartAnnouncementClient] DART list.json 호출 실패 — ticker=%s corp_code=%s err=%s",
                ticker, corp_code, exc,
            )
            return []

        announcements: List[Dict[str, Any]] = []
        for item in items:
            ann_date = _parse_rcept_dt(item.rcept_dt)
            if ann_date is None:
                continue
            ann_type = _classify_dart_type(item.report_nm, item.pblntf_ty)
            announcements.append({
                "date": ann_date.isoformat(),
                "type": ann_type.value,
                "title": item.report_nm.strip(),
                "source": "dart",
                "url": _build_dart_url(item.rcept_no),
                "items_str": None,  # DART 는 8-K Item 코드 구조 없음
            })

        logger.info(
            "[DartAnnouncementClient] ticker=%s corp_code=%s 기간=%s~%s → %d건",
            ticker, corp_code,
            start_date.isoformat(), end_date.isoformat(),
            len(announcements),
        )
        return announcements
