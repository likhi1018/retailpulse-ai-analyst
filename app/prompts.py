"""Prompt templates for SQL generation, self-correction and answer summaries."""

SQL_SYSTEM = """You are a senior data analyst writing DuckDB SQL for the RetailPulse \
e-commerce star schema (Olist, Brazil, 2016-2018).

Write ONE read-only SELECT query (CTEs allowed) that answers the user's question.
- Use only the tables and columns listed below. Never invent columns.
- Follow the metric definitions and rules exactly.
- Use readable column aliases (e.g. revenue, orders, late_rate_pct).
- Order results in the most useful way and limit long lists to the top 10 unless asked otherwise.
- If the question cannot be answered from this data, return:
  SELECT 'Not answerable with this data: <short reason>' AS message
Return only the SQL inside a ```sql code block.

{schema}

## Examples
{examples}
"""

FEW_SHOT = [
    ("What was total revenue in 2017?",
     """SELECT ROUND(SUM(s.price), 2) AS revenue
FROM fact_sales s
JOIN dim_date d ON d.date_key = s.date_key
WHERE d.year = 2017;"""),
    ("Which 5 states have the highest late delivery rate?",
     """SELECT o.state_code, g.state_name,
       ROUND(100 * AVG(o.is_late), 1) AS late_rate_pct,
       COUNT(*) AS delivered_orders
FROM fact_orders o
JOIN dim_geography g ON g.state_code = o.state_code
WHERE o.is_delivered = 1
GROUP BY o.state_code, g.state_name
ORDER BY late_rate_pct DESC
LIMIT 5;"""),
    ("Show monthly revenue and month-over-month growth for 2018.",
     """WITH monthly AS (
    SELECT d.year_month, SUM(s.price) AS revenue
    FROM fact_sales s
    JOIN dim_date d ON d.date_key = s.date_key
    WHERE d.year_month BETWEEN '2018-01' AND '2018-08'
    GROUP BY d.year_month
)
SELECT year_month,
       ROUND(revenue, 2) AS revenue,
       ROUND(100 * (revenue / LAG(revenue) OVER (ORDER BY year_month) - 1), 1) AS mom_growth_pct
FROM monthly
ORDER BY year_month;"""),
]

FIX_PROMPT = """That query failed.

SQL:
```sql
{sql}
```
Error: {error}

Fix the query. Return only the corrected SQL in a ```sql code block."""

SUMMARY_SYSTEM = """You explain query results to a business stakeholder.
Answer the question in 2-3 sentences using ONLY numbers that appear in the result.
Money is in Brazilian reais (R$). Do not speculate about causes the data does not show.
If the result is empty, say so plainly."""

SUMMARY_USER = """Question: {question}

SQL used:
```sql
{sql}
```

Result ({n_rows} rows{truncated}):
{table}"""


def examples_block() -> str:
    return "\n\n".join(f"Q: {q}\n```sql\n{sql}\n```" for q, sql in FEW_SHOT)
