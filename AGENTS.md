# AGENTS.md

## Mandatory handoff protocol

`HANDOFF.md` in this directory is the single source of truth for what exists in this project.

**Before writing any code:**
1. Read `HANDOFF.md` in full.
2. Verify the claims you are about to depend on — read the actual file or hit the actual endpoint. The handoff describes state, not a contract; it can be stale.
3. Do not duplicate what the handoff says already exists.

**After finishing any code change:**
1. Update `HANDOFF.md` so it still describes reality — specifically the "Implemented and working", "Known gaps / landmines", and stack/layout sections.
2. If you introduced a limitation, a workaround, or broke an assumption listed there, replace the old line. Do not append. Two contradicting lines is worse than none.
3. If you changed how something is run (a command, a port, a path), the "Running it" section changes too.

A handoff that lies is worse than no handoff. If you cannot verify something, say so in the file rather than guessing.

## Other conventions

- Backend commands run from inside `backend/`. Paths are CWD-relative.
- `backend/outputs/` is generated and gitignored. Never hand-edit parquet there.
- Model assumptions live in `backend/risk_engine/config.py`, not inline in calculation modules. Keep it that way — the project is judged on traceability of every number to a named source.
- README.md overstates things (Gemini vs. an HF-routed OpenAI-compatible client). Trust `HANDOFF.md` over README when they disagree.

## Never invent a number in the UI

This project is judged on where every figure comes from. Fabricated fallbacks
were deliberately deleted from the dashboard; panels now render an empty state
when there is no real data. Do not reintroduce placeholder series, EAL
multipliers, or hardcoded compliance scores to make a panel look populated.

Related: any metric derived from limited data must say so. Report
`mean_f1_macro` and the majority-class baseline rather than raw F1. Do not
present a model output as a trend when the history is too short to support it.

## Verify before you claim done

Run all three. A change is not finished until they pass:

```bash
cd backend && python -m pytest tests/ -v    # 33 tests
cd frontend && npm run lint                 # oxlint, must exit 0
cd frontend && npm run build                # must succeed
```

`npm run build` catches the JSX mistakes that oxlint misses, and the browser
console catches what both miss. If you touched a panel, load it at
`localhost:5173/insights` and confirm zero console errors.