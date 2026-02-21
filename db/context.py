def is_private_chat(chat_id: int | str, user_id: int | str) -> bool:
    """Return True if the interaction is a private DM (chat_id == user telegram_id).

    Telegram private chats always have a chat_id equal to the user's own
    telegram_id. Group and supergroup chats have a different chat_id.

    Import and call this in every command handler before processing.
    """
    return str(chat_id) == str(user_id)
