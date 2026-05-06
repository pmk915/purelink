from __future__ import annotations

from enum import StrEnum
import re


WHITESPACE_PATTERN = re.compile(r"\s+")


class QAIntent(StrEnum):
    KB_FACT_QA = "kb_fact_qa"
    KB_OVERVIEW = "kb_overview"
    GENERAL_CHAT = "general_chat"


OVERVIEW_KEYWORDS: tuple[str, ...] = (
    "总结",
    "概括",
    "主要内容",
    "关键点",
    "梳理",
    "整体",
    "有哪些内容",
    "讲了什么",
    "这些资料主要",
    "这些文档主要",
    "summarize",
    "summary",
    "overview",
    "key points",
    "main topics",
    "what is this knowledge base about",
)


def normalize_qa_question(question: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", question.strip()).lower()


def classify_qa_intent(question: str) -> QAIntent:
    normalized = normalize_qa_question(question)
    if any(keyword in normalized for keyword in OVERVIEW_KEYWORDS):
        return QAIntent.KB_OVERVIEW
    return QAIntent.KB_FACT_QA
