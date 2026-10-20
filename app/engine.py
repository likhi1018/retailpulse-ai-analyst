"""Question -> SQL -> validated -> executed (with self-correction) -> plain-English answer."""
import re
import time
from dataclasses import dataclass, field

import pandas as pd

from app import prompts
from app.db import Database
from app.guard import UnsafeSQLError, validate
from app.schema import build_schema_context

MAX_ATTEMPTS = 3
SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.S | re.I)


def extract_sql(text: str) -> str:
    m = SQL_BLOCK.search(text)
    return (m.group(1) if m else text).strip().rstrip(";").strip()


@dataclass
class Answer:
    question: str
    sql: str = ""
    data: pd.DataFrame | None = None
    summary: str = ""
    attempts: int = 0
    error: str = ""
    seconds: float = 0.0
    trace: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.error


class Analyst:
    def __init__(self, llm, db: Database | None = None):
        self.llm = llm
        self.db = db or Database()
        self.system = prompts.SQL_SYSTEM.format(
            schema=build_schema_context(self.db), examples=prompts.examples_block())

    def ask(self, question: str, history: list[dict] | None = None, summarize: bool = True) -> Answer:
        start = time.time()
        ans = Answer(question=question)
        messages = [{"role": "system", "content": self.system}]
        messages += (history or [])[-6:]  # short memory for follow-up questions
        messages.append({"role": "user", "content": question})

        for attempt in range(1, MAX_ATTEMPTS + 1):
            ans.attempts = attempt
            reply = self.llm.complete(messages)
            raw_sql = extract_sql(reply)
            try:
                safe_sql = validate(raw_sql)
                ans.data = self.db.query(safe_sql)
                ans.sql, ans.error = safe_sql, ""
                ans.trace.append({"attempt": attempt, "sql": safe_sql, "error": None})
                break
            except UnsafeSQLError as e:
                err = str(e)
            except Exception as e:  # DuckDB binder/parser/runtime errors
                err = str(e).splitlines()[0][:400]
            ans.sql, ans.error = raw_sql, err
            ans.trace.append({"attempt": attempt, "sql": raw_sql, "error": err})
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": prompts.FIX_PROMPT.format(sql=raw_sql, error=err)}]

        if ans.ok and summarize:
            ans.summary = self.summarize(question, ans.sql, ans.data)
        ans.seconds = round(time.time() - start, 2)
        return ans

    def summarize(self, question: str, sql: str, df: pd.DataFrame) -> str:
        preview = df.head(25)
        msg = prompts.SUMMARY_USER.format(
            question=question, sql=sql, n_rows=len(df),
            truncated=", first 25 shown" if len(df) > 25 else "",
            table=preview.to_markdown(index=False) if len(preview) else "(no rows)")
        return self.llm.complete([{"role": "system", "content": prompts.SUMMARY_SYSTEM},
                                  {"role": "user", "content": msg}]).strip()
