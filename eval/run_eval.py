"""
Execution-accuracy benchmark for the text-to-SQL engine.

    python -m eval.run_eval              # real model (needs LLM_API_KEY)
    python -m eval.run_eval --oracle     # sanity check: feeds the gold SQL back in (should score 100%)

Writes eval/results.md and eval/results.csv.
"""
import argparse
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import yaml

from app.db import Database
from app.engine import Analyst

HERE = Path(__file__).parent


def _norm(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "NULL"
    if isinstance(v, (int, float)) or hasattr(v, "__float__") and not isinstance(v, str):
        try:
            return f"{round(float(v), 1):.1f}"
        except (TypeError, ValueError):
            pass
    return str(v).strip().lower()


def results_match(gold: pd.DataFrame, pred: pd.DataFrame) -> bool:
    """Same rows, regardless of column names/order and row order; numbers compared to 1 decimal."""
    if gold.shape != pred.shape:
        return False
    rows = lambda df: Counter(tuple(sorted(_norm(v) for v in r)) for r in df.itertuples(index=False))
    return rows(gold) == rows(pred)


def is_unanswerable_reply(df: pd.DataFrame) -> bool:
    return df is not None and df.shape == (1, 1) and "not answerable" in str(df.iat[0, 0]).lower()


class OracleLLM:
    """Returns the gold SQL for the current question; validates the harness end to end."""
    def __init__(self, items):
        self.by_q = {i["question"]: i["gold"] for i in items}

    def complete(self, messages):
        q = messages[-1]["content"]
        return f"```sql\n{self.by_q.get(q, 'SELECT 1')}\n```"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oracle", action="store_true")
    args = ap.parse_args()

    items = yaml.safe_load((HERE / "questions.yaml").read_text())
    db = Database()
    if args.oracle:
        llm, label = OracleLLM(items), "oracle (gold SQL)"
    else:
        from app.llm import LLMClient
        llm = LLMClient()
        label = llm.model
    analyst = Analyst(llm, db)

    rows = []
    for it in items:
        gold = db.query(it["gold"])
        t0 = time.time()
        ans = analyst.ask(it["question"], summarize=False)
        if it["category"] == "unanswerable":
            correct = is_unanswerable_reply(ans.data)
        else:
            correct = ans.ok and results_match(gold, ans.data)
        rows.append({"id": it["id"], "category": it["category"], "question": it["question"],
                     "correct": correct, "attempts": ans.attempts, "self_corrected": ans.ok and ans.attempts > 1,
                     "error": ans.error, "seconds": round(time.time() - t0, 2), "sql": ans.sql})
        print(f"{it['id']} {'PASS' if correct else 'FAIL'}  attempts={ans.attempts}  {it['question']}")

    df = pd.DataFrame(rows)
    df.to_csv(HERE / "results.csv", index=False)
    acc = df["correct"].mean()
    by_cat = df.groupby("category")["correct"].agg(["sum", "count"])
    md = [f"# Evaluation results — {label}", "",
          f"- **Execution accuracy: {acc:.0%}** ({df['correct'].sum()}/{len(df)})",
          f"- Answered on first attempt: {(df['attempts'] == 1).mean():.0%}",
          f"- Fixed by self-correction: {df['self_corrected'].sum()} questions",
          f"- Median time per question: {df['seconds'].median():.1f}s", "",
          "| Category | Correct |", "|---|---|"]
    md += [f"| {c} | {int(r['sum'])}/{int(r['count'])} |" for c, r in by_cat.iterrows()]
    md += ["", "| ID | Question | Result | Attempts |", "|---|---|---|---|"]
    md += [f"| {r.id} | {r.question} | {'✅' if r.correct else '❌'} | {r.attempts} |" for r in df.itertuples()]
    (HERE / "results.md").write_text("\n".join(md) + "\n")
    print(f"\nExecution accuracy: {acc:.0%}")


if __name__ == "__main__":
    main()
