"""Builds the schema + business-glossary context that is sent to the model."""
from pathlib import Path

import yaml

from app.db import TABLES, Database

GLOSSARY_PATH = Path(__file__).with_name("glossary.yaml")


def load_glossary() -> dict:
    return yaml.safe_load(GLOSSARY_PATH.read_text())


def build_schema_context(db: Database) -> str:
    g = load_glossary()
    lines = ["## Tables"]
    for t in TABLES:
        lines.append(f"\n### {t} ({db.row_count(t):,} rows)")
        lines.append(g["tables"].get(t, ""))
        for col, typ in db.columns(t):
            note = ""
            if typ == "VARCHAR" and not col.endswith("_id"):
                vals = db.distinct_values(t, col)
                if vals:
                    note = "  values: " + ", ".join(repr(v) for v in vals)
            lines.append(f"- {col} {typ}{note}")
    lines.append("\n## Joins")
    lines += [f"- {r}" for r in g["relationships"]]
    lines.append("\n## Metric definitions")
    lines += [f"- {k}: {v}" for k, v in g["metrics"].items()]
    lines.append("\n## Rules")
    lines += [f"- {r}" for r in g["rules"]]
    lines.append(f"- {g['currency']}")
    return "\n".join(lines)
