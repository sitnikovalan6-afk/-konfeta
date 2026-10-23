import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.types import Message
from aiogram.exceptions import TelegramAPIError

import config
import database as db

dp = Dispatcher()


def parse_id(value):
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def sticker_name(value):
    value = value.strip().rstrip("/")
    if "t.me/addstickers/" in value:
        return value.split("t.me/addstickers/")[-1].split("?")[0]
    return value


async def save_context(message: Message):
    if message.from_user:
        await db.remember_user(message.from_user)

    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        await db.remember_group(message.chat)


async def ban_from_known_groups(bot: Bot, user_id: int):
    for chat_id in await db.get_groups():
        try:
            await bot.ban_chat_member(chat_id, user_id)
        except TelegramAPIError:
            # Бот может не иметь права блокировки в конкретной группе.
            continue


@dp.message(F.new_chat_members)
async def new_members(message: Message, bot: Bot):
    await save_context(message)

    for member in message.new_chat_members:
        if await db.get_antispam_user(member.id):
            try:
                await bot.ban_chat_member(message.chat.id, member.id)
            except TelegramAPIError:
                pass


@dp.message()
async def handle_message(message: Message, bot: Bot):
    await save_context(message)

    # Удаление стикеров только из наборов, добавленных инспекторами в список.
    if message.sticker and message.sticker.set_name:
        if message.sticker.set_name in await db.get_sticker_sets():
            try:
                await message.delete()
            except TelegramAPIError:
                pass
            return

    text = (message.text or "").strip()
    if not text or not message.from_user:
        return

    actor_id = message.from_user.id
    lower = text.lower()
    owner = actor_id == config.OWNER_ID
    staff = await db.is_inspector(actor_id)

    if lower in ("!помощь", "/help"):
        await message.answer(
            "🍬 Конфета — чат-менеджер\n\n"
            "!id — ID пользователя (ответом на сообщение)\n"
            "!чс — постоянный бан в текущем чате (ответом)\n"
            "+антиспам — добавить в общую базу (ответом)\n"
            "-антиспам — убрать из базы (ответом)\n"
            "!добавить 18+ <ссылка или имя набора>\n"
            "!список 18+\n"
            "!удалить 18+ <ссылка или имя набора>\n"
            ".конф <ID или @username> — статистика инспекторами\n"
            "+инспектор ID / -инспектор ID — только владелец\n\n"
            f"Поддержка: {config.SUPPORT_CHAT_URL}\n\n"
            "Проверка стикеров работает только для наборов из списка. "
            "Функции в разработке могут быть нестабильны."
        )
        return

    if lower == "!id":
        if message.reply_to_message and message.reply_to_message.from_user:
            await message.reply(
                f"ID пользователя: {message.reply_to_message.from_user.id}"
            )
        else:
            await message.reply("Используй !id ответом на сообщение.")
        return

    if lower.startswith("+инспектор "):
        if not owner:
            await message.reply("Команда доступна только владельцу.")
            return

        target_id = parse_id(text.split(maxsplit=1)[1])
        if not target_id:
            await message.reply("Формат: +инспектор ID")
            return

        await db.add_inspector(target_id, actor_id)
        await message.reply(f"Инспектор {target_id} добавлен.")
        return

    if lower.startswith("-инспектор "):
        if not owner:
            await message.reply("Команда доступна только владельцу.")
            return

        target_id = parse_id(text.split(maxsplit=1)[1])
        if not target_id:
            await message.reply("Формат: -инспектор ID")
            return

        await db.remove_inspector(target_id)
        await message.reply(f"Инспектор {target_id} удалён.")
        return

    if lower in ("+антиспам", "-антиспам", "!чс"):
        if not staff:
            await message.reply("Команда доступна только инспекторам.")
            return

        if not message.reply_to_message or not message.reply_to_message.from_user:
            await message.reply("Используй команду ответом на сообщение пользователя.")
            return

        target = message.reply_to_message.from_user

        if lower == "+антиспам":
            await db.add_antispam(
                target.id, actor_id, "", message.chat.id
            )
            await ban_from_known_groups(bot, target.id)
            await message.reply(
                f"Пользователь {target.id} добавлен в антиспам-базу. "
                "Бот попробовал заблокировать его в известных группах."
            )
            return

        if lower == "-антиспам":
            await db.remove_antispam(target.id, actor_id, message.chat.id)
            await message.reply(
                f"Пользователь {target.id} удалён из антиспам-базы. "
                "Ранее выданные баны автоматически не снимаются."
            )
            return

        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            await message.reply("Команда !чс работает только в группе.")
            return

        try:
            await bot.ban_chat_member(message.chat.id, target.id)
            await db.add_ban(target.id, actor_id, message.chat.id, "")
            await message.reply(
                f"Пользователь {target.id} заблокирован в этом чате навсегда."
            )
        except TelegramAPIError as error:
            await message.reply(
                f"Не удалось заблокировать пользователя. "
                f"Проверь права бота. Ошибка: {error}"
            )
        return

    if lower.startswith("!добавить 18+ "):
        if not staff:
            await message.reply("Команда доступна только инспекторам.")
            return

        name = sticker_name(text.split(maxsplit=2)[2])
        if not name:
            await message.reply("Укажи ссылку или имя стикерпака.")
            return

        await db.add_sticker_set(name, actor_id)
        await message.reply(f"Стикерпак добавлен: {name}")
        return

    if lower == "!список 18+":
        if not staff:
            await message.reply("Команда доступна только инспекторам.")
            return

        sets = await db.get_sticker_sets()
        await message.reply(
            "Список пуст." if not sets
            else "Стикерпаки в списке:\n" + "\n".join(sets)
        )
        return

    if lower.startswith("!удалить 18+ "):
        if not staff:
            await message.reply("Команда доступна только инспекторам.")
            return

        name = sticker_name(text.split(maxsplit=2)[2])
        await db.remove_sticker_set(name)
        await message.reply(f"Стикерпак удалён: {name}")
        return

    if lower.startswith(".конф"):
        if not staff:
            await message.reply("Команда доступна только инспекторам.")
            return

        parts = text.split(maxsplit=1)
        argument = parts[1].strip() if len(parts) > 1 else ""
        target_id = None

        if message.reply_to_message and message.reply_to_message.from_user:
            target_id = message.reply_to_message.from_user.id
        elif argument.startswith("@"):
            target_id = await db.find_user_by_username(argument)
        else:
            target_id = parse_id(argument)

        if not target_id:
            await message.reply(
                "Укажи ID, ранее замеченный @username или ответь на сообщение.\n"
                "Пример: .конф 123456789"
            )
            return

        added, removed, ban_count, bans, active, user = (
            await db.get_user_stats(target_id)
        )
        username, full_name = user if user else ("", "")
        status = "Находится в антиспам-базе" if active else "Не в антиспам-базе"

        lines = [
            "Профиль пользователя",
            f"ID: {target_id}",
            f"Имя: {full_name or 'неизвестно'}",
            f"Username: @{username}" if username else "Username: неизвестен",
            status,
            f"Добавлений в базу: {added}",
            f"Удалений из базы: {removed}",
            f"Записанных банов: {ban_count}",
        ]

        if active:
            lines.append(f"Причина в базе: {active[0] or 'не указана'}")

        if bans:
            lines.append("Последние баны:")
            for chat_id, reason, created_at in bans:
                lines.append(
                    f"• Чат {chat_id}; причина: {reason or 'не указана'}; "
                    f"{created_at}"
                )

        await message.reply("\n".join(lines))
        return


async def main():
    if not config.BOT_TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN. Добавь его в Environment Variables на хостинге."
        )

    await db.init_db()
    bot = Bot(token=config.BOT_TOKEN)

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
