from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import BaseModel

from semiconductor_timing.schemas import DailyResult


def ensure_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            create table if not exists daily_runs (
                id integer primary key autoincrement,
                run_at text not null,
                main_score real not null,
                jensen_score real not null,
                confidence_grade text not null,
                payload_json text not null
            )
            """
        )


def model_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2)


def save_daily_result(path: Path, result: DailyResult) -> None:
    ensure_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            insert into daily_runs (
                run_at, main_score, jensen_score, confidence_grade, payload_json
            ) values (?, ?, ?, ?, ?)
            """,
            (
                result.run_at.isoformat(),
                result.main_score.score,
                result.jensen_score.score,
                result.validation.grade,
                model_json(result),
            ),
        )


def latest_scores(path: Path, limit: int = 5) -> list[dict]:
    ensure_db(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            """
            select run_at, main_score, jensen_score, confidence_grade
            from daily_runs
            order by run_at desc
            limit ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "run_at": row[0],
            "main_score": row[1],
            "jensen_score": row[2],
            "confidence_grade": row[3],
        }
        for row in rows
    ]
