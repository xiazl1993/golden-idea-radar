# Golden Idea Radar v0.1

面向**中国 ToC 软件 / AI 副业**的机会雷达第一版。

核心原则：**Idea 必须由 Evidence 推出来，而不是让模型拍脑袋生成。**

## Pipeline

```text
GitHub live + CSV evidence
          ↓
     gi_observations
          ↓
   Pain Signal Miner
          ↓
   Dedup / Clustering
          ↓
      Idea Candidate
          ↓
 Opportunity Score (100)
          ↓
 Risk Penalty / Kill Checks
          ↓
       Top20 → Top3
          ↓
 Evidence-backed Markdown/API
```

## v0.1 能力

- GitHub Issues 公共信号采集
- CSV 半自动导入 App Store / 百度 / 知乎 / 小红书 / 抖音 / 微信小程序证据
- 中文抱怨句式抽取 Pain Signal
- 轻量关键词/Jaccard 聚类，保留历史 cluster / idea 记录
- 100 分 Opportunity Score + 5 类 Risk Penalty
- Giant Killer / Model Killer 的启发式预筛
- 输出 Top20 + Top3 Markdown，Top3 带原始 Evidence 样本
- FastAPI：排名查询 + Idea 原始证据回溯
- SQLite 本地启动；附 Supabase Postgres migration + RLS
- GitHub Actions 定时扫描骨架（要求持久化 Supabase/Postgres）
- DEMO 数据显式隔离，正式 run 不会混入 demo signal
- 评分历史按 run 保留，便于后续复盘与校准

## Why not scrape everything on day one

小红书、抖音、微信小程序等来源的稳定采集往往涉及登录态、反爬和平台规则。v0.1 把半自动导入当作正式路径：先证明“这个雷达找得到值得验证的点子”，再为高价值来源做合规、稳定的采集适配器。

## Local start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 用 demo 验证闭环
python -m app.cli ingest-csv samples/evidence.csv
python -m app.cli run --include-demo --report reports/demo.md

# API
uvicorn app.main:app --reload --port 8810
```

API：

```text
GET  /health
POST /pipeline/run
GET  /ideas?limit=20
GET  /ideas/{idea_id}/evidence
```

## GitHub live signals

在 `.env` 配置 `GITHUB_TOKEN` 后：

```bash
python -m app.cli ingest-github --per-query 30
python -m app.cli run
```

## Real evidence CSV

最少字段：

```csv
source,external_id,url,title,text,published_at,is_demo
zhihu,abc123,https://...,标题,"用户原话",2026-09-13T10:00:00+08:00,false
```

建议 `external_id` 使用平台稳定 ID；没有时用 URL hash。时间会统一转换为 UTC 后再参与 7d/14d 趋势计算。

## Supabase / scheduled run

先在 Supabase SQL Editor 执行：

```text
migrations/001_golden_idea.sql
```

然后使用 Direct Connection / Session Pooler 的 Postgres URL：

```env
DATABASE_URL=postgresql+psycopg://...
```

Postgres 模式**不会自动 create_all**，避免绕过 migration 中的 RLS。GitHub Actions 需要：

```text
GIR_DATABASE_URL      # Supabase/Postgres URL
GIR_GITHUB_TOKEN      # GitHub token，可选但建议配置
```

没有 `GIR_DATABASE_URL` 时定时任务直接失败，避免每次 Action 都写入一次性 SQLite 导致“看起来运行、实际上没有历史”。

## Score v0.1

Opportunity 100：

- 痛点强度 15
- 频率 10
- 增长 10
- 付费意图 15
- 竞品满意度缺口 10
- MVP 可验证性 10
- 分发/来源多样性 10
- Builder Fit 10
- 数据/工作流壁垒 10

Risk Penalty：

- 巨头威胁 0–20
- 模型吞噬 0–20
- 监管 0–15
- 获客 0–15
- 重运营 0–15

`Final = Opportunity - Penalty`。

> v0.1 的风险评分是**预筛**，不是最终市场结论。进入 Top20 后仍要执行真实的竞品搜索、低星评论挖掘、巨头产品检查和模型替代性检查。

## Acceptance target for first real week

- ≥ 500 条真实 Observation
- ≥ 4 个来源类别
- ≥ 100 条有效 Pain Signal
- Top20 每条都有 Evidence Count + Source Diversity
- Top3 每条有人群、痛点、MVP、巨头风险、模型风险
- 任意 Idea 可以回溯原始 URL / 文本
- 重跑 Observation 幂等，Score 按 run 留历史

## v0.2 after validation

1. App Store 竞品 / 低星评论 adapter
2. 百度/知乎搜索结果自动化 adapter
3. 小红书 / 抖音半自动浏览器采集
4. `gi_competitors` / `gi_competitor_reviews` 真正接入评分
5. Giant Killer / Model Killer 独立 research stage，而非仅启发式关键词
6. Top20 → Top3 多 Agent 独立打分
7. MVP experiment 回写，形成正反馈 loop
