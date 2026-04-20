import aiohttp
from app.core.config import settings
from app.core.logging import logger

async def send_telegram_message(
    text: str,
    company_name: str | None = None,
    include_admin: bool = True,
    explicit_chat_ids: list[str] | None = None,
) -> list[str]:
    token = settings.TELEGRAM_BOT_TOKEN
    recipients = explicit_chat_ids if explicit_chat_ids is not None else settings.get_telegram_recipients(company_name, include_admin=include_admin)
    if not token or not recipients:
        logger.warning("Telegram token or recipients not set. Skipping message.")
        return []
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    try:
        async with aiohttp.ClientSession() as session:
            delivered_chat_ids: list[str] = []
            for chat_id in recipients:
                payload = {
                    "chat_id": chat_id,
                    "text": text
                }
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        logger.error(f"Failed to send Telegram message to {chat_id}: {await response.text()}")
                    else:
                        delivered_chat_ids.append(chat_id)

            if delivered_chat_ids:
                logger.info(f"Telegram message sent successfully to {len(delivered_chat_ids)} recipient(s).")
            return delivered_chat_ids
    except Exception as e:
        logger.error(f"Exception while sending Telegram message: {e}")
        return []
