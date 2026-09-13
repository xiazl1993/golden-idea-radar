from __future__ import annotations

import math
from datetime import timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .config import settings
from .models import ClusterMember, Idea, Observation, PainCluster, PainSignal, Run, Score
from .timeutil import utcnow_naive

GIANTS = ["闲鱼", "支付宝", "微信", "京东", "淘宝", "美团", "抖音", "小红书", "百度", "腾讯", "阿里", "字节", "chatgpt", "豆包", "千问"]
PURE_MODEL_TERMS = ["改写", "翻译", "总结", "摘要", "润色", "写文案", "聊天", "提示词"]
REGULATED = ["医疗", "诊断", "法律", "律师", "投资", "股票", "保险理赔", "贷款", "处方"]
OPS = ["上门", "物流", "配送", "仓库", "租赁", "线下", "维修师傅", "跑腿"]
ACQUISITION = ["同城", "附近", "社区", "撮合", "双边", "商家入驻", "用户发布"]
WORKFLOW = ["记录", "历史", "持续", "监控", "工作流", "订单", "库存", "档案", "证据", "时间线", "车型", "里程"]
STRUCTURED_INPUT = ["截图", "照片", "图片", "账单", "报价单", "发票", "链接", "文档", "聊天记录"]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _cluster_signals(session: Session, cluster_id: int) -> list[tuple[PainSignal, Observation]]:
    rows = session.execute(select(PainSignal, Observation).join(ClusterMember, ClusterMember.pain_signal_id == PainSignal.id).join(Observation, Observation.id == PainSignal.observation_id).where(ClusterMember.cluster_id == cluster_id)).all()
    return [(s, o) for s, o in rows]


def build_and_score(session: Session, run: Run) -> int:
    now = utcnow_naive()
    total = 0
    for cluster in session.scalars(select(PainCluster)).all():
        pairs = _cluster_signals(session, cluster.id)
        if not pairs:
            continue
        text = " ".join([cluster.representative_text] + [o.text.lower() for _, o in pairs])
        idea = session.scalar(select(Idea).where(Idea.cluster_id == cluster.id))
        if not idea:
            mvp = "上传/粘贴一个真实输入 → 输出一个可执行结果"
            if any(t in text for t in STRUCTURED_INPUT):
                mvp = "上传截图/照片/账单/文档 → 自动结构化 → 给出明确判断与下一步动作"
            idea = Idea(cluster_id=cluster.id, title=cluster.title[:160], problem=cluster.representative_text[:1200], proposed_mvp=mvp, first_seen_at=cluster.first_seen_at or now, last_seen_at=cluster.last_seen_at or now)
            session.add(idea)
            session.flush()
        else:
            idea.title = cluster.title[:160]
            idea.problem = cluster.representative_text[:1200]
            idea.last_seen_at = cluster.last_seen_at or now

        severities = [s.severity for s, _ in pairs]
        intents = [s.intent_score for s, _ in pairs]
        pain_score = _clamp(sum(severities) / len(severities) * 15, 0, 15)
        frequency_score = _clamp(math.log1p(len(pairs)) / math.log(11) * 10, 0, 10)
        timestamps = [(o.published_at or o.captured_at) for _, o in pairs]
        current = sum(1 for ts in timestamps if ts >= now - timedelta(days=7))
        previous = sum(1 for ts in timestamps if now - timedelta(days=14) <= ts < now - timedelta(days=7))
        growth_ratio = (current + 1) / (previous + 1)
        growth_score = _clamp((growth_ratio - 0.5) / 2.5 * 10, 0, 10)
        payment_score = _clamp(sum(intents) / len(intents) * 15, 0, 15)
        negative_solution_hits = sum(text.count(term) for term in ["不好用", "难用", "广告", "订阅", "贵", "不准", "崩溃", "限制", "不能"])
        gap_score = _clamp(2 + negative_solution_hits * 1.4, 0, 10)
        mvp_score = 9.0 if any(t in text for t in STRUCTURED_INPUT) else 6.0
        distribution_score = _clamp(cluster.source_diversity * 2.2 + min(4, len(pairs) / 3), 0, 10)
        builder_fit_score = _clamp(float(settings.builder_fit_score), 0, 10)
        moat_score = _clamp(2 + sum(1.2 for t in WORKFLOW if t in text), 0, 10)
        opportunity = sum([pain_score, frequency_score, growth_score, payment_score, gap_score, mvp_score, distribution_score, builder_fit_score, moat_score])
        giant_risk = _clamp(sum(1 for g in GIANTS if g in text) * 4.0, 0, 20)
        pure_hits = sum(1 for t in PURE_MODEL_TERMS if t in text)
        workflow_hits = sum(1 for t in WORKFLOW if t in text)
        model_risk = _clamp(5 + pure_hits * 4 - workflow_hits * 1.3, 0, 20)
        regulatory_risk = _clamp(sum(5 for t in REGULATED if t in text), 0, 15)
        acquisition_risk = _clamp(sum(3 for t in ACQUISITION if t in text), 0, 15)
        operation_risk = _clamp(sum(3 for t in OPS if t in text), 0, 15)
        penalty = giant_risk + model_risk + regulatory_risk + acquisition_risk + operation_risk
        final = _clamp(opportunity - penalty, 0, 100)
        session.add(Score(idea_id=idea.id, run_id=run.id, pain_score=round(pain_score, 2), frequency_score=round(frequency_score, 2), growth_score=round(growth_score, 2), payment_score=round(payment_score, 2), gap_score=round(gap_score, 2), mvp_score=round(mvp_score, 2), distribution_score=round(distribution_score, 2), builder_fit_score=round(builder_fit_score, 2), moat_score=round(moat_score, 2), opportunity_score=round(opportunity, 2), giant_risk=round(giant_risk, 2), model_risk=round(model_risk, 2), regulatory_risk=round(regulatory_risk, 2), acquisition_risk=round(acquisition_risk, 2), operation_risk=round(operation_risk, 2), final_score=round(final, 2), rationale={"evidence_count": len(pairs), "source_diversity": cluster.source_diversity, "current_7d": current, "previous_7d": previous}))
        total += 1
    session.flush()

    ranked = session.execute(select(Idea, Score).join(Score, Score.idea_id == Idea.id).where(Score.run_id == run.id).order_by(desc(Score.final_score))).all()
    for rank, (idea, _) in enumerate(ranked, start=1):
        idea.status = "TOP3" if rank <= 3 else "TOP20" if rank <= 20 else "WATCHING"
    session.commit()
    return total
