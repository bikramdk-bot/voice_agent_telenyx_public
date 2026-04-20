import sqlite3
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.agent.state import CallState
from app.core.config import settings
from app.core.logging import logger


def _metrics_db_path() -> Path:
    db_path = Path(settings.METRICS_DB_PATH)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_metrics_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def initialize_metrics_db() -> None:
    with closing(_connect()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS call_metrics (
                call_control_id TEXT PRIMARY KEY,
                company_name TEXT,
                receiver_phone_number TEXT,
                caller_phone_number TEXT,
                call_started_at TEXT NOT NULL,
                call_finished_at TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                lead_submitted INTEGER NOT NULL,
                task_description TEXT,
                openai_total_tokens INTEGER NOT NULL,
                openai_input_tokens INTEGER NOT NULL,
                openai_output_tokens INTEGER NOT NULL,
                openai_text_input_tokens INTEGER NOT NULL,
                openai_audio_input_tokens INTEGER NOT NULL,
                openai_text_output_tokens INTEGER NOT NULL,
                openai_audio_output_tokens INTEGER NOT NULL,
                telegram_messages_sent INTEGER NOT NULL,
                telegram_company_messages_sent INTEGER NOT NULL,
                telegram_admin_messages_sent INTEGER NOT NULL,
                openai_cost_estimate_usd REAL NOT NULL,
                telnyx_cost_estimate_usd REAL NOT NULL,
                telegram_cost_estimate_usd REAL NOT NULL,
                total_cost_estimate_usd REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS summary_runs (
                summary_date TEXT NOT NULL,
                summary_type TEXT NOT NULL,
                company_name TEXT,
                sent_at TEXT NOT NULL,
                PRIMARY KEY (summary_date, summary_type, company_name)
            );
            """
        )
        connection.commit()


def _estimate_openai_cost_usd(session: CallState) -> float:
    return (
        (session.openai_text_input_tokens / 1_000_000) * settings.OPENAI_TEXT_INPUT_COST_PER_1M_USD
        + (session.openai_text_output_tokens / 1_000_000) * settings.OPENAI_TEXT_OUTPUT_COST_PER_1M_USD
        + (session.openai_audio_input_tokens / 1_000_000) * settings.OPENAI_AUDIO_INPUT_COST_PER_1M_USD
        + (session.openai_audio_output_tokens / 1_000_000) * settings.OPENAI_AUDIO_OUTPUT_COST_PER_1M_USD
    )


def _estimate_telnyx_cost_usd(duration_seconds: float) -> float:
    return (duration_seconds / 60) * settings.TELNYX_COST_PER_MINUTE_USD


def _estimate_telegram_cost_usd(message_count: int) -> float:
    return message_count * settings.TELEGRAM_COST_PER_MESSAGE_USD


def record_call_metrics(session: CallState) -> None:
    finished_at = session.call_finished_at or datetime.now(timezone.utc)
    duration_seconds = max(0.0, (finished_at - session.call_started_at).total_seconds())
    openai_cost_estimate_usd = _estimate_openai_cost_usd(session)
    telnyx_cost_estimate_usd = _estimate_telnyx_cost_usd(duration_seconds)
    telegram_cost_estimate_usd = _estimate_telegram_cost_usd(session.telegram_messages_sent)
    total_cost_estimate_usd = openai_cost_estimate_usd + telnyx_cost_estimate_usd + telegram_cost_estimate_usd

    try:
        with closing(_connect()) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO call_metrics (
                    call_control_id,
                    company_name,
                    receiver_phone_number,
                    caller_phone_number,
                    call_started_at,
                    call_finished_at,
                    duration_seconds,
                    lead_submitted,
                    task_description,
                    openai_total_tokens,
                    openai_input_tokens,
                    openai_output_tokens,
                    openai_text_input_tokens,
                    openai_audio_input_tokens,
                    openai_text_output_tokens,
                    openai_audio_output_tokens,
                    telegram_messages_sent,
                    telegram_company_messages_sent,
                    telegram_admin_messages_sent,
                    openai_cost_estimate_usd,
                    telnyx_cost_estimate_usd,
                    telegram_cost_estimate_usd,
                    total_cost_estimate_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.call_control_id,
                    session.company_name,
                    session.receiver_phone_number,
                    session.caller_phone_number,
                    session.call_started_at.isoformat(),
                    finished_at.isoformat(),
                    duration_seconds,
                    int(session.lead_submitted),
                    session.task_description,
                    session.openai_total_tokens,
                    session.openai_input_tokens,
                    session.openai_output_tokens,
                    session.openai_text_input_tokens,
                    session.openai_audio_input_tokens,
                    session.openai_text_output_tokens,
                    session.openai_audio_output_tokens,
                    session.telegram_messages_sent,
                    session.telegram_company_messages_sent,
                    session.telegram_admin_messages_sent,
                    openai_cost_estimate_usd,
                    telnyx_cost_estimate_usd,
                    telegram_cost_estimate_usd,
                    total_cost_estimate_usd,
                ),
            )
            connection.commit()
    except Exception as exc:
        logger.error(f"Failed to record call metrics for {session.call_control_id}: {exc}")


def _day_window_utc(summary_date: date) -> tuple[str, str]:
    summary_timezone = ZoneInfo(settings.SUMMARY_TIMEZONE)
    day_start_local = datetime.combine(summary_date, time.min, tzinfo=summary_timezone)
    day_end_local = day_start_local + timedelta(days=1)
    return day_start_local.astimezone(timezone.utc).isoformat(), day_end_local.astimezone(timezone.utc).isoformat()


def get_admin_daily_summary(summary_date: date) -> dict[str, float | int | str]:
    day_start_utc, day_end_utc = _day_window_utc(summary_date)

    with closing(_connect()) as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(lead_submitted), 0) AS processed_calls,
                COALESCE(SUM(telegram_messages_sent), 0) AS telegram_messages_sent,
                COALESCE(SUM(telegram_company_messages_sent), 0) AS company_messages_sent,
                COALESCE(SUM(telegram_admin_messages_sent), 0) AS admin_messages_sent,
                COALESCE(SUM(duration_seconds), 0) AS total_duration_seconds,
                COALESCE(SUM(openai_total_tokens), 0) AS openai_total_tokens,
                COALESCE(SUM(openai_input_tokens), 0) AS openai_input_tokens,
                COALESCE(SUM(openai_output_tokens), 0) AS openai_output_tokens,
                COALESCE(SUM(openai_text_input_tokens), 0) AS openai_text_input_tokens,
                COALESCE(SUM(openai_audio_input_tokens), 0) AS openai_audio_input_tokens,
                COALESCE(SUM(openai_text_output_tokens), 0) AS openai_text_output_tokens,
                COALESCE(SUM(openai_audio_output_tokens), 0) AS openai_audio_output_tokens,
                COALESCE(SUM(openai_cost_estimate_usd), 0) AS openai_cost_estimate_usd,
                COALESCE(SUM(telnyx_cost_estimate_usd), 0) AS telnyx_cost_estimate_usd,
                COALESCE(SUM(telegram_cost_estimate_usd), 0) AS telegram_cost_estimate_usd,
                COALESCE(SUM(total_cost_estimate_usd), 0) AS total_cost_estimate_usd
            FROM call_metrics
            WHERE call_started_at >= ? AND call_started_at < ?
            """,
            (day_start_utc, day_end_utc),
        ).fetchone()

    total_calls = int(row["total_calls"])
    processed_calls = int(row["processed_calls"])
    gce_daily_cost_usd = float(settings.GCE_DAILY_COST_USD)
    total_cost_with_gce_usd = float(row["total_cost_estimate_usd"]) + gce_daily_cost_usd
    average_cost_per_processed_call_usd = total_cost_with_gce_usd / processed_calls if processed_calls else 0.0

    return {
        "summary_date": summary_date.isoformat(),
        "total_calls": total_calls,
        "processed_calls": processed_calls,
        "telegram_messages_sent": int(row["telegram_messages_sent"]),
        "company_messages_sent": int(row["company_messages_sent"]),
        "admin_messages_sent": int(row["admin_messages_sent"]),
        "total_duration_seconds": float(row["total_duration_seconds"]),
        "openai_total_tokens": int(row["openai_total_tokens"]),
        "openai_input_tokens": int(row["openai_input_tokens"]),
        "openai_output_tokens": int(row["openai_output_tokens"]),
        "openai_text_input_tokens": int(row["openai_text_input_tokens"]),
        "openai_audio_input_tokens": int(row["openai_audio_input_tokens"]),
        "openai_text_output_tokens": int(row["openai_text_output_tokens"]),
        "openai_audio_output_tokens": int(row["openai_audio_output_tokens"]),
        "openai_cost_estimate_usd": float(row["openai_cost_estimate_usd"]),
        "telnyx_cost_estimate_usd": float(row["telnyx_cost_estimate_usd"]),
        "telegram_cost_estimate_usd": float(row["telegram_cost_estimate_usd"]),
        "gce_daily_cost_usd": gce_daily_cost_usd,
        "total_cost_with_gce_usd": total_cost_with_gce_usd,
        "average_cost_per_processed_call_usd": average_cost_per_processed_call_usd,
    }


def get_company_daily_summary(summary_date: date, company_name: str) -> dict[str, int | str]:
    day_start_utc, day_end_utc = _day_window_utc(summary_date)

    with closing(_connect()) as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total_calls,
                COALESCE(SUM(lead_submitted), 0) AS processed_calls,
                COALESCE(SUM(telegram_company_messages_sent), 0) AS company_messages_sent
            FROM call_metrics
            WHERE call_started_at >= ? AND call_started_at < ? AND company_name = ?
            """,
            (day_start_utc, day_end_utc, company_name),
        ).fetchone()

    return {
        "summary_date": summary_date.isoformat(),
        "company_name": company_name,
        "total_calls": int(row["total_calls"]),
        "processed_calls": int(row["processed_calls"]),
        "company_messages_sent": int(row["company_messages_sent"]),
    }


def summary_already_sent(summary_date: date, summary_type: str, company_name: str | None = None) -> bool:
    with closing(_connect()) as connection:
        if company_name is None:
            row = connection.execute(
                """
                SELECT 1
                FROM summary_runs
                WHERE summary_date = ? AND summary_type = ? AND company_name IS NULL
                """,
                (summary_date.isoformat(), summary_type),
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT 1
                FROM summary_runs
                WHERE summary_date = ? AND summary_type = ? AND company_name = ?
                """,
                (summary_date.isoformat(), summary_type, company_name),
            ).fetchone()
    return row is not None


def mark_summary_sent(summary_date: date, summary_type: str, company_name: str | None = None) -> None:
    with closing(_connect()) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO summary_runs (summary_date, summary_type, company_name, sent_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                summary_date.isoformat(),
                summary_type,
                company_name,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
