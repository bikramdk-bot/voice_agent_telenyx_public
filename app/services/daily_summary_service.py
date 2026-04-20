import asyncio
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.logging import logger
from app.services.metrics_service import (
    get_admin_daily_summary,
    get_company_daily_summary,
    mark_summary_sent,
    summary_already_sent,
)
from app.services.telegram_service import send_telegram_message


def _summary_timezone() -> ZoneInfo:
    return ZoneInfo(settings.SUMMARY_TIMEZONE)


def _summary_time() -> time:
    hour_str, minute_str = settings.SUMMARY_TIME_LOCAL.split(":", 1)
    return time(hour=int(hour_str), minute=int(minute_str))


def _format_admin_summary(summary_date: date) -> str:
    summary = get_admin_daily_summary(summary_date)
    total_duration_seconds = float(summary["total_duration_seconds"])
    total_calls = int(summary["total_calls"])
    average_call_minutes = (total_duration_seconds / total_calls / 60) if total_calls else 0.0
    return (
        f"Daily Admin Summary ({summary['summary_date']})\n\n"
        f"Total calls: {summary['total_calls']}\n"
        f"Processed calls: {summary['processed_calls']}\n"
        f"Lead messages sent: {summary['company_messages_sent']}\n"
        f"Admin messages sent: {summary['admin_messages_sent']}\n"
        f"Average call length (min): {average_call_minutes:.2f}\n\n"
        f"OpenAI total tokens: {summary['openai_total_tokens']}\n"
        f"OpenAI input tokens: {summary['openai_input_tokens']}\n"
        f"OpenAI output tokens: {summary['openai_output_tokens']}\n"
        f"OpenAI text in/out: {summary['openai_text_input_tokens']}/{summary['openai_text_output_tokens']}\n"
        f"OpenAI audio in/out: {summary['openai_audio_input_tokens']}/{summary['openai_audio_output_tokens']}\n\n"
        f"Estimated OpenAI cost (USD): {summary['openai_cost_estimate_usd']:.4f}\n"
        f"Estimated Telnyx cost (USD): {summary['telnyx_cost_estimate_usd']:.4f}\n"
        f"Estimated Telegram cost (USD): {summary['telegram_cost_estimate_usd']:.4f}\n"
        f"Estimated GCE daily cost (USD): {summary['gce_daily_cost_usd']:.4f}\n"
        f"Estimated total cost incl. GCE (USD): {summary['total_cost_with_gce_usd']:.4f}\n"
        f"Average estimated cost per processed call (USD): {summary['average_cost_per_processed_call_usd']:.4f}"
    )


def _format_company_summary(summary_date: date, company_name: str) -> str:
    summary = get_company_daily_summary(summary_date, company_name)
    return (
        f"Daily Company Summary ({summary['summary_date']})\n\n"
        f"Company: {summary['company_name']}\n"
        f"Lead messages sent today: {summary['company_messages_sent']}\n"
        f"Processed calls today: {summary['processed_calls']}"
    )


def _due_summary_dates(now_local: datetime, scheduled_time: time, timezone_info: ZoneInfo) -> list[date]:
    today_target = datetime.combine(now_local.date(), scheduled_time, tzinfo=timezone_info)
    due_dates = [now_local.date() - timedelta(days=1)]

    if now_local >= today_target:
        due_dates.append(now_local.date())

    return due_dates


async def _send_due_summaries(summary_date: date, trigger: str = "scheduled") -> bool:
    all_summaries_sent = True

    logger.info("Daily summary dispatch started. trigger=%s summary_date=%s", trigger, summary_date.isoformat())

    admin_chat_id = settings.get_admin_chat_id()
    if admin_chat_id and not summary_already_sent(summary_date, "admin"):
        logger.info("Sending admin daily summary. trigger=%s summary_date=%s", trigger, summary_date.isoformat())
        delivered_chat_ids = await send_telegram_message(
            _format_admin_summary(summary_date),
            include_admin=False,
            explicit_chat_ids=[admin_chat_id],
        )
        if delivered_chat_ids:
            mark_summary_sent(summary_date, "admin")
            logger.info(
                "Admin daily summary sent. trigger=%s summary_date=%s delivered_chat_ids=%s",
                trigger,
                summary_date.isoformat(),
                delivered_chat_ids,
            )
        else:
            logger.warning("Admin daily summary delivery failed. trigger=%s summary_date=%s", trigger, summary_date.isoformat())
            all_summaries_sent = False
    elif admin_chat_id:
        logger.info("Skipping admin daily summary because it was already sent. trigger=%s summary_date=%s", trigger, summary_date.isoformat())
    else:
        logger.warning("Skipping admin daily summary because no admin chat id is configured. trigger=%s summary_date=%s", trigger, summary_date.isoformat())

    for company_name in settings.telegram_companies.keys():
        company_chat_id = settings.get_company_chat_id(company_name)
        if not company_chat_id:
            logger.warning(
                "Skipping company daily summary because no Telegram chat id is configured. trigger=%s company=%s summary_date=%s",
                trigger,
                company_name,
                summary_date.isoformat(),
            )
            continue

        if summary_already_sent(summary_date, "company", company_name):
            logger.info(
                "Skipping company daily summary because it was already sent. trigger=%s company=%s summary_date=%s",
                trigger,
                company_name,
                summary_date.isoformat(),
            )
            continue

        logger.info("Sending company daily summary. trigger=%s company=%s summary_date=%s", trigger, company_name, summary_date.isoformat())
        delivered_chat_ids = await send_telegram_message(
            _format_company_summary(summary_date, company_name),
            include_admin=False,
            explicit_chat_ids=[company_chat_id],
        )
        if delivered_chat_ids:
            mark_summary_sent(summary_date, "company", company_name)
            logger.info(
                "Company daily summary sent. trigger=%s company=%s summary_date=%s delivered_chat_ids=%s",
                trigger,
                company_name,
                summary_date.isoformat(),
                delivered_chat_ids,
            )
        else:
            logger.warning(
                "Company daily summary delivery failed. trigger=%s company=%s summary_date=%s",
                trigger,
                company_name,
                summary_date.isoformat(),
            )
            all_summaries_sent = False

    logger.info("Daily summary dispatch finished. trigger=%s summary_date=%s all_summaries_sent=%s", trigger, summary_date.isoformat(), all_summaries_sent)
    return all_summaries_sent


async def send_daily_summary(summary_date: date, trigger: str = "manual") -> bool:
    return await _send_due_summaries(summary_date, trigger=trigger)


async def _daily_summary_loop() -> None:
    logger.info(
        "Daily summary scheduler started for %s at %s",
        settings.SUMMARY_TIMEZONE,
        settings.SUMMARY_TIME_LOCAL,
    )

    while True:
        try:
            timezone_info = _summary_timezone()
            scheduled_time = _summary_time()
            now_local = datetime.now(timezone_info)
            today_target = datetime.combine(now_local.date(), scheduled_time, tzinfo=timezone_info)

            for summary_date in _due_summary_dates(now_local, scheduled_time, timezone_info):
                all_summaries_sent = await _send_due_summaries(summary_date, trigger="scheduled")
                if not all_summaries_sent:
                    logger.warning("Daily summary delivery incomplete for %s. Retrying in 60 seconds.", summary_date.isoformat())
                    await asyncio.sleep(60)
                    break
            else:
                next_target = today_target if now_local < today_target else today_target + timedelta(days=1)
                sleep_seconds = max(1.0, (next_target - now_local).total_seconds())
                await asyncio.sleep(sleep_seconds)
                continue

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Daily summary scheduler error: {exc}")
            await asyncio.sleep(60)


def run_daily_summary_scheduler() -> asyncio.Task:
    return asyncio.create_task(_daily_summary_loop())