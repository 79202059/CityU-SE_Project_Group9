# 把 PyExamine Delta 接进 PR 流水线

三个文件决定一切：

| 文件 | 作用 |
| --- | --- |
| `github-actions.yml` | 可直接拷进 `.github/workflows/` 的工作流 |
| `.pyexamine-baseline.json` | 主干现状的快照，提交到仓库根目录 |
| `pyexamine-thresholds.yaml`（可选） | `calibrate` 产出的项目自适应阈值 |

## 1. 三步接入

```bash
# ① 在主干上拍一份基线（write 模式快照的是 --head 指向的 commit）
git checkout main
pyexamine-delta . --base HEAD --head HEAD --baseline-mode write
git add .pyexamine-baseline.json && git commit -m "chore: pyexamine baseline"

# ② 拷工作流
mkdir -p .github/workflows && cp docs/ci/github-actions.yml .github/workflows/pyexamine-delta.yml

# ③（可选）先看阈值分布，再决定要不要校准
pyexamine-delta calibrate . --percentile 95 --max-multiplier 2 --format text
```

## 2. 三个旋钮

工作流顶层 `env:` 里三个变量决定门禁松紧，别一次全开：

| 变量 | 含义 | 建议起点 | 调松/调紧的依据 |
| --- | --- | --- | --- |
| `PYEX_FAIL_ON` | NEW finding 达到该严重度即阻断 | `medium` | 用 `high` 起步最安全，但结构性 high 占 33–43%，容易每个 PR 都红 |
| `PYEX_MIN_RISK` | 只有风险分 ≥ 该值的 NEW 才参与阻断 | `40` | 三语料 p90 在 34–40，取 40 约等于「只看最上游那 10%」 |
| `PYEX_BUDGET` | 单个 PR 最多容忍多少条 NEW | `20` | 先统计历史 PR 的中位数，再每次 sprint 收紧 20% |
| `PYEX_LEVEL_POLICY` | SARIF 严重度映射 | `triage` | `strict` 直译；`triage` 把结构性 high 降为 warning，`advisory` 再降一档 |

`triage` 的依据是实测：4 个真实项目上结构性 finding 占总量 53–72%，其中 46–57% 被标 high。原样直译会让「按 high 阻断」在每个 PR 上都触发。

## 3. 为什么需要 `fetch-depth: 0`

增量分析要解析 base 与 head 两个 commit（`git worktree add --detach`），
浅克隆里拿不到 `origin/main` 的历史，`git rev-parse` 会失败。

## 4. 失败时怎么读

```
risk: scored 2 new finding(s); highest 42.1; 1 at or above 40.0
gate: 1 new finding(s) at or above 'medium' - failing the run
```

- 第一行来自 `--min-risk`：说明有几条 NEW 够得上风险门槛；
- 第二行来自 `--fail-on-new`：说明剩下几条仍然超过严重度门槛；
- `budget: N new finding(s) exceed the budget of M - failing the run` 来自 `--max-new`，与严重度无关，纯粹是数量预算。

顺序是 **严重度 → 预算**：先看「有没有特别严重的新问题」，再看「整体数量有没有失控」。
两者都要红的时候只报前者，因为严重度更值得先处理。

## 5. 本地复现 CI 的判断

```bash
# 与工作流里 Gate 那一步等价
pyexamine-delta . --base origin/main --head HEAD \
  --baseline-mode diff --format text \
  --risk --min-risk 40 --fail-on-new medium --max-new 20

# 与工作流里 Markdown summary 那一步等价（贴到 PR 评论里看排版）
pyexamine-delta . --base origin/main --head HEAD \
  --baseline-mode diff --format markdown --risk | tee /dev/tty
```

## 6. 已知限制

1. **私有仓库没有 Code Scanning**：`upload-sarif` 需要 GitHub Advanced Security。
   没启用时删掉那一步，其余步骤（step summary、退出码门禁）照常工作。
2. **baseline 会随阈值变化失效**：改过 `pyexamine-thresholds.yaml` 之后必须重新
   `--baseline-mode write`，否则被收紧掉的 finding 会一次性变成 RESOLVED。
3. **`--baseline-mode write` 快照的是 `--head`**：在 PR 上生成主干基线必须写成
   `--base "$BASE" --head "$BASE"`，否则会把 PR 自己的问题写进基线，门禁从此失灵。
4. **没有 diff 时风险分上限约 53**：`change` 分量恒为 0。PR 场景（有 diff）上限约 78，
   所以风险分不能跨 baseline 比较。
