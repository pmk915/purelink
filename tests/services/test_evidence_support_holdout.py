from __future__ import annotations

import pytest

from app.services.evidence_support import REASON_SUPPORTED, evaluate_evidence_support
from app.services.qa import build_query_evidence_profile
from app.services.retrieval.types import RetrievedEvidence


@pytest.mark.parametrize(
    ("question", "evidence"),
    [
        ("Alice Chen 出生于哪一年？", "Alice Chen 的角色是检索工程师，办公地点是 Singapore。"),
        ("Aurora Air 使用哪款 CPU？", "Aurora Air 的颜色是蓝色，重量是 0.9 kg，特点是轻量。"),
        ("Acme 的融资金额是多少？", "Acme 员工政策涵盖假期、远程办公和绩效沟通。"),
        ("White Rabbit 的身高是多少？", "White Rabbit carries a watch and starts Alice's adventure."),
        ("PostgreSQL 的创始人是谁？", "PostgreSQL uses MVCC and supports several transaction isolation levels."),
        ("PureLink 的月收入是多少？", "PureLink retrieval trace records candidate and final evidence metadata."),
        ("Carol Wang 的生日是哪一天？", "Carol Wang 属于 Product Group，负责知识库工作台和用户研究。"),
        ("Aurora Server 的显卡型号是什么？", "Aurora Server 的颜色是灰色，重量是 8.5 kg，特点是可扩展。"),
        ("公司总部的街道地址是什么？", "员工政策说明远程办公需要经理批准。"),
        ("Python class 是在哪一年发明的？", "A Python class is a user-defined type that organizes data and behavior together."),
    ],
)
def test_evidence_support_holdout_rejects_unsupported_paraphrases(question: str, evidence: str) -> None:
    decision = _decision(question, evidence)

    assert decision.answerable is False
    assert decision.reason != REASON_SUPPORTED


@pytest.mark.parametrize(
    ("question", "evidence"),
    [
        ("Bob Li 的办公城市是什么？", "Bob Li 的角色是平台工程师，办公地点：Shanghai，负责 Docker、监控和部署。"),
        ("Carol Wang 属于哪个组？", "Carol Wang 隶属：Product Group，负责知识库工作台和用户研究。"),
        ("Aurora Air 有多重？", "Aurora Air 的颜色是蓝色，重量：0.9 kg，特点是轻量。"),
        ("White Rabbit 随身携带什么？", "White Rabbit carries a watch and helps start Alice's adventure."),
        ("__init__ 在什么阶段执行？", "Python calls `__init__` during instantiation after creating a new instance object."),
        ("FastAPI 的 dependency 能否嵌套？", "A dependency can depend on another dependency. FastAPI resolves this tree during one request."),
        ("MVCC 的主要目的是什么？", "PostgreSQL uses MVCC so readers and writers can often operate without blocking each other."),
        ("block_aware 与 fixed 是什么关系？", "PureLink supports fixed and block_aware chunk strategies; block_aware uses document block boundaries."),
        ("docker compose down -v 会删除什么？", "`docker compose down -v` removes volumes while plain down preserves named volumes."),
        ("retrieval trace 记录什么？", "PureLink retrieval trace records candidate and final evidence metadata, selected mode, and scores."),
    ],
)
def test_evidence_support_holdout_accepts_supported_paraphrases(question: str, evidence: str) -> None:
    decision = _decision(question, evidence)

    assert decision.answerable is True
    assert decision.reason == REASON_SUPPORTED


def test_relation_support_combines_entities_with_explicit_relation_in_local_scope() -> None:
    question = "White Rabbit 和 Alice 的情节关系是什么？"
    decision = _multi_decision(
        question,
        [
            _evidence(
                "Alice follows him into the rabbit-hole.",
                chunk_id="1:1",
                section_title="Opening encounter",
            ),
            _evidence(
                "The White Rabbit carries a watch and starts the adventure.",
                chunk_id="1:2",
                section_title="Opening encounter",
            ),
        ],
    )

    assert decision.answerable is True
    assert decision.signals["relation_entity_coverage"] is True


def test_relation_support_uses_heading_and_unit_text_with_explicit_relation() -> None:
    question = "White Rabbit 和 Alice 的情节关系是什么？"
    decision = _multi_decision(
        question,
        [
            _evidence(
                "Alice follows him, which leads her into Wonderland.",
                heading_path=["Characters", "White Rabbit"],
            )
        ],
    )

    assert decision.answerable is True


def test_relation_support_accepts_explicit_lock_conflict_semantics() -> None:
    decision = _decision(
        "MVCC 和显式锁是什么关系？",
        "MVCC allows readers and writers to operate without blocking each other.",
    )

    assert decision.answerable is True


def test_relation_support_rejects_entity_descriptions_without_relation() -> None:
    question = "White Rabbit 和 Alice 的情节关系是什么？"
    decision = _multi_decision(
        question,
        [
            _evidence("Alice is the central character.", section_title="Characters", chunk_id="1:1"),
            _evidence("White Rabbit carries a watch.", section_title="Characters", chunk_id="1:2"),
        ],
    )

    assert decision.answerable is False


def test_relation_support_does_not_combine_different_documents() -> None:
    question = "White Rabbit 和 Alice 的情节关系是什么？"
    decision = _multi_decision(
        question,
        [
            _evidence("Alice follows him.", document_id=1, section_title="Opening"),
            _evidence("White Rabbit starts the adventure.", document_id=2, section_title="Opening"),
        ],
    )

    assert decision.answerable is False


def test_relation_support_ignores_broad_parent_chunk_metadata() -> None:
    question = "White Rabbit 和 Alice 的情节关系是什么？"
    evidence = _evidence("Alice follows him.", section_title="Opening")
    evidence.metadata["parent_chunk_text"] = "White Rabbit starts the adventure."

    decision = _multi_decision(question, [evidence])

    assert decision.answerable is False


def test_relation_support_rejects_entity_cooccurrence_without_relation_semantics() -> None:
    decision = _decision(
        "White Rabbit 和 Alice 的情节关系是什么？",
        "Alice and the White Rabbit attended the same meeting.",
    )

    assert decision.answerable is False


def _decision(question: str, evidence: str):
    return _multi_decision(question, [_evidence(evidence)])


def _multi_decision(question: str, evidence_units: list[RetrievedEvidence]):
    return evaluate_evidence_support(
        query=question,
        evidence_units=evidence_units,
        profile=build_query_evidence_profile(question),
    )


def _evidence(
    text: str,
    *,
    document_id: int = 1,
    chunk_id: str = "1:0",
    section_title: str | None = None,
    heading_path: list[str] | None = None,
) -> RetrievedEvidence:
    return RetrievedEvidence(
        document_id=document_id,
        chunk_id=chunk_id,
        chunk_db_id=1,
        text=text,
        document_name="holdout.txt",
        final_score=0.92,
        section_title=section_title,
        heading_path=heading_path,
        metadata={"marker": "S1"},
    )
