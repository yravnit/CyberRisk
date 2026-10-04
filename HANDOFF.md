# HANDOFF — CyberRisk

SIH 2026 entry, PS ID 26105 (AICTE Cyber Security Cell). FAIR-based cyber risk quantification + security budget optimizer. Turns "Low/Medium/High" risk into dollars: EAL, VaR95/99, ROSI, and an ILP-solved optimal control purchase plan.

State as of last update. Verify anything you rely on before trusting it.

## Stack & layout

```
backend/            Python 3.10+, FastAPI + uvicorn. Run from inside backend/.
  api/main.py       REST routes. Reads parquet/json from backend/outputs/.
  api/upload.py     Dataset ingest: 5-CSV / ZIP / compiled JSON, or /demo. Writes data/uploads/<session>/ + outputs/active_session.json
  api/chat.py       LLM copilot. OpenAI-compatible client -> HF router, model deepseek-ai/DeepSeek-V4-Flash-0731:novita
  api/live_feed.py  GET /api/live-feed/recent + WS /ws/live-feed. Synthetic random events over the real asset list.
  risk_engine/      FAIR pipeline, one module per phase (see below)
  data/             5 CSVs + compliance_mappings.json + cve_metadata.json + compiled_risk_dataset.json
  outputs/          Generated. gitignored. Pipeline must run before the API can serve /risk/* and /controls/*
  tests/            pytest, 33 tests, all passing
frontend/           React 18 + Vite + Tailwind + Recharts + axios. oxlint for linting.
  src/api/client.js All API calls + currency/percent formatters
  src/pages/        HomePage (upload), DashboardPage (everything else)
  src/components/dashboard/  13 panels, one per feature
  .oxlintrc.json    Lint config. npm run lint / npm run lint:fix
```

## Running it

```bash
# backend — must be run from backend/ (paths are relative to CWD)
cd backend
pip install -r requirements.txt
python -m risk_engine.pipeline      # writes outputs/*.parquet, ~15s
uvicorn api.main:app --reload       # docs at localhost:8000/docs
python -m pytest tests/ -v          # 33 passed

# frontend
cd frontend
npm install
npm run dev                        # :5173
npm run lint                       # oxlint, must exit 0
npm run build
```

`backend/.venv/` is stale — it points at a Python install from another user. Ignore it. The system Python 3.13 has all deps except `pulp`, which was installed via pip.

## FAIR pipeline order (backend/risk_engine/pipeline.py)

`ingest.py` joins the 5 CSVs into one row per asset →
`likelihood.py` EPSS annualization `1-(1-e)^(365/30)`, CVSS/10, max across CVEs →
`frequency.py` TEF, triangular dist, BU fallback if <3 events →
`loss_magnitude.py` downtime×cost + IR flat + per-record×records, lognormal σ=0.75 →
`simulate.py` 20k vectorized Monte Carlo per asset →
`aggregate.py` EAL/VaR95/VaR99 + LEC, rolled up to BU and org →
`control_scenarios.py` before/after re-simulation per candidate control → ROSI →
then: `predictor.py` (RF + XGBoost), `trend_generator.py` (re-simulated history), `threat_forecaster.py` (PyTorch LSTM + Markov ATT&CK), `frontier.py` (knee point).

## Implemented and working

- All pipeline phases, producing all 8 files in `outputs/`.
- 20 REST endpoints, all returning 200 with the demo dataset.
- Knapsack ILP optimizer via PuLP/COIN-CBC, with greedy baseline.
- Investment frontier curve + knee detection, precomputed to `outputs/frontier_cache.json`.
- Compliance mapping across ISO 27001, NIST CSF 2.0, CIS v8.1, RBI CSF, SEBI CSCRF.
- RF + XGBoost exploitation predictor with 5-fold CV, feature importances, and baseline comparison.
- LSTM threat forecaster, 14-day horizon, with naive-baseline check.
- AD dependency graph + lateral movement propagation, seeded and reproducible.
- Portfolio LEC as a true quantile-sum of per-asset Monte Carlo curves.
- Risk trend by re-simulating truncated telemetry windows.
- Chat copilot with live risk context.
- All 13 dashboard panels wired and rendering with real data.
- oxlint clean: `npm run lint` exits 0, `npm run build` succeeds.

## Known gaps / landmines

- **No invented numbers anywhere in the UI.** Every fabricated fallback that used to exist was deleted, not relabeled: portfolio LEC, trend chart, investment frontier, compliance posture/gaps, asset detail LEC, executive VaR, what-if residual EAL. Each panel now renders an empty state instead. Do not reintroduce these — if you add a panel, compute it or show nothing.
- **The ML exploitation label is observed at ASSET granularity.** `threat_events` has no `cve_id`, so a vulnerability inherits its asset's `action_taken="Allowed"` outcome. Positive rate is 0.808 and the majority-class F1 baseline is 0.894 — always report `mean_f1_macro` (0.78 RF / 0.94 XGB), not raw F1. Metrics live under `metrics["_meta"]`. If no Allowed events exist, the predictor is skipped rather than fabricating a target.
- **LSTM cannot produce a directional claim on this data.** 31 days of telemetry vs a 90-day bar, so `trend_direction` is `"Insufficient History"` and `beats_naive_baseline` is False. The -56.9% shift is still computed and shown but explicitly labelled as noise. Do not feed `tef_shift_pct` into anything as if it were a trend.
- **Risk trend windows are day-based, spanning only the observed telemetry** (~20 days back), not 6 months. `is_reconstructed` marks which rows are re-simulated cutoffs. Frontend copy must not say "6mo".
- **Dependency graph edges are inferred from asset attributes** (tier, business unit), not observed network traffic. Now seeded via `build_graph(seed=)` so topology is stable, but still a model, not telemetry.
- **Two disk caches never invalidate.** `frontier_cache.json` and `threat_forecast.json` are written on first call. Delete them after a new upload.
- **`_frontier_cache` and `_graph_engine` are process globals.** Every client sees the first requester's data until restart.
- **Live threat feed is `random.choice` over the real asset list.** Labelled "Simulated data" in the panel.
- **EAL sums linearly across assets.** Documented upper-bound approximation — correlated events are not modelled. Deliberate, documented, do not silently "fix".
- **`additive_capped` drives 19 of 50 assets to exactly $0 EAL.** Assets with several strong controls (0.85 EDR + 0.95 MFA) sum past 1.0, resistance caps at 1.0, and `Vuln_asset` goes to 0, so those assets contribute nothing to the total. This is why the systemic graph shows "$0 direct standalone loss" for AST-1000 — not a display bug. `config.py` recommends `multiplicative` for production; switching drops zero-EAL assets 19 → 6 and raises org EAL $1.09B → $1.36B. Left on `additive_capped` because it is the documented default and the control values already assume strong individual controls. Do not change it without re-baselining every figure.
- **README claims Gemini; code uses an OpenAI-compatible client against an HF router.** The README is wrong, not the code.
- **README links to `docs/architecture.md`, `submission/PRESENTATION.md`, `submission/DEMO.md`, `assets/screenshots/` — none exist.** Hard blocker if this is being submitted.
- No database. Session state in `data/uploads/`, outputs as loose parquet.
- No auth on any endpoint. CORS is `allow_origins=["*"]`.
- No frontend tests. oxlint covers lint only.