from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Observation, PainSignal


PAIN_PHRASES = {
    "有没有": 0.8,
    "求推荐": 0.8,
    "太麻烦": 1.0,
    "麻烦": 0.5,
    "受够": 1.0,
    "为什么不能": 0.9,
    "不支持": 0.8,
    "不好用": 0.9,
    "难用": 0.9,
    "崩溃": 0.9,
    "被坑": 1.0,
    "避雷": 0.9,
    "一直不处理": 1.0,
    "怎么自动": 0.9,
    "怎么批量": 0.8,
    "有没有办法": 0.9,
    "每次都要": 0.8,
    "希望增加": 0.7,
    "希望支持": 0.7,
    "feature request": 0.6,
    "would love": 0.6,
    "missing": 0.5,
    "there is no way": 0.9,
    "no built-in way": 0.8,
    "wish there was": 0.7,
    "no way to": 0.8,
}

COMMERCIAL_TERMS = ["多少钱", "价格", "收费", "订阅", "退款", "维修", "保养", "报价", "押金", "发票", "报销", "赔偿", "省钱"]
INPUT_TERMS = ["截图", "照片", "图片", "账单", "报价单", "发票", "链接", "文档", "记录", "聊天"]
MOAT_TERMS = ["历史", "持续", "监控", "记录", "库存", "订单", "工作流", "账户", "车型", "里程", "设备", "案例"]
CN_STOP_PHRASES = {"有没有", "有没有办法", "怎么自动", "怎么批量", "为什么不能", "希望支持", "希望增加", "这个", "那个", "一个", "可以", "需要", "软件", "工具", "应用", "真的", "感觉", "每次"}
EN_STOP = {"the", "and", "for", "with", "this", "that", "from", "have", "would", "could", "please", "feature", "request"}


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def keywords(text: str, limit: int = 10) -> list[str]:
    text = normalize(text)
    counts: Counter[str] = Counter()
    for seq in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        for stop in CN_STOP_PHRASES:
            seq = seq.replace(stop, " ")
        for chunk in seq.split():
            if len(chunk) < 2:
                continue
            max_n = min(4, len(chunk))
            for n in range(2, max_n + 1):
                for i in range(0, len(chunk) - n + 1):
                    counts[chunk[i:i+n]] += n / 2
    for word in re.findall(r"[a-z][a-z0-9_-]{2,}", text):
        if word not in EN_STOP:
            counts[word] += 1
    return [w for w, _ in counts.most_common(limit)]


def extract_pain_signals(session: Session, include_demo: bool = False) -> int:
    query = select(Observation)
    if not include_demo:
        query = query.where(Observation.is_demo.is_(False))
    changed = 0
    for obs in session.scalars(query).all():
        existing = session.scalar(select(PainSignal).where(PainSignal.observation_id == obs.id))
        low = obs.text.lower()
        matches = [p for p in PAIN_PHRASES if p.lower() in low]
        if not matches:
            if existing:
                session.delete(existing)
                changed += 1
            continue
        raw = sum(PAIN_PHRASES[p] for p in matches)
        severity = min(1.0, 0.35 + raw / 3.0)
        commercial_hits = sum(1 for term in COMMERCIAL_TERMS if term.lower() in low)
        intent = min(1.0, 0.25 + commercial_hits * 0.18 + (0.15 if "有没有" in low else 0))
        tags: list[str] = []
        if any(x in low for x in INPUT_TERMS):
            tags.append("structured_input")
        if any(x in low for x in MOAT_TERMS):
            tags.append("workflow_or_history")
        values = dict(normalized_text=normalize(obs.text), severity=severity, intent_score=intent, matched_phrases=matches, tags=tags)
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
        else:
            session.add(PainSignal(observation_id=obs.id, **values))
        changed += 1
    session.commit()
    return changed
