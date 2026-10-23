import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import Message, User
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import config
import database as db

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

def user_label(user: User) -> str:
    name = " ".join(part for part in (user.first_name, user.last_name) if part)
    return f"{name} (@{user.username})" if user.username else (name or str(user.id))

def sticker_set_name(link: str):
    value = link.strip()
    for prefix in ("https://t.me/addstickers/", "http://t.me/addstickers/",
                   "https://telegram.me/addstickers/", "http://telegram.me/addstickers/"):
        if value.startswith(prefix):
            return value[len(prefix):].split("?", 1)[0].strip("/")
    if value.startswith("@"):
        return value[1:]
    return None

async def resolve_target(message: Message, argument: str = ""):
    argument = argument.strip()
    if not argument and message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        return u.id, u.username, user_label(u)
    if argument.isdigit():
        uid = int(argument)
        known = await db.get_user(uid)
        return uid, known[1] if known else None, known[2] if known else str(uid)
    if argument.startswith("@"):
        known = await db.find_user_by_username(argument)
        if known:
            return known[0], known[1], known[2]
    return None

async def require_inspector(message: Message):
    if message.from_user and await db.is_inspector(message.from_user.id):
        return True
    await message.reply("Эта команда доступна только инспекторам «Конфеты».")
    return False

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет! Я «Конфета» — чат-менеджер.\n"
        "Напиши !помощь, чтобы увидеть команды.\n"
        f"Поддержка: {config.SUPPORT_LINK}\n\n"
        "Внимание: некоторые функции находятся в разработке и могут работать некорректно."
    )

@dp.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def group_handler(message: Message, bot: Bot):
    if message.from_user:
        await db.save_user(message.from_user.id, message.from_user.username, user_label(message.from_user))
    await db.save_group(message.chat.id, message.chat.title or "Без названия", str(message.chat.type))

    # Автобан участников, уже внесённых в общую антиспам-базу.
    if message.from_user and message.from_user.id != config.OWNER_ID:
        entry = await db.get_antispam_entry(message.from_user.id)
        if entry:
            try:
                await bot.ban_chat_member(message.chat.id, message.from_user.id)
                await db.add_ban(message.from_user.id, message.chat.id, message.chat.title or "Без названия",
                                 bot.id, f"Автобан по антиспам-базе: {entry[0]}")
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
            return

    if message.sticker and message.sticker.set_name:
        if await db.is_banned_sticker_set(message.sticker.set_name):
            try:
                await message.delete()
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
            if message.from_user:
                try:
                    await bot.ban_chat_member(message.chat.id, message.from_user.id)
                    await db.add_ban(message.from_user.id, message.chat.id, message.chat.title or "Без названия",
                                     bot.id, f"Стикер из набора 18+: {message.sticker.set_name}")
                except (TelegramBadRequest, TelegramForbiddenError):
                    pass
            return

    text = (message.text or "").strip()
    if not text:
        return
    low = text.lower()

    if low == "!помощь":
        await message.reply(
            "Команды «Конфеты»\n\n"
            "Все участники:\n"
            "• !помощь\n"
            "• !id — ответом на сообщение\n\n"
            "Инспекторы:\n"
            "• +антиспам ID или ответом — добавить в общую базу\n"
            "• -антиспам ID или ответом — убрать из базы\n"
            "• !бан — ответом на сообщение; причина на следующей строке\n"
            "• .конф ID, .конф @username или ответом — досье\n"
            "• !добавить 18+ ссылка\n"
            "• !список 18+\n"
            "• !удалить 18+ ссылка\n\n"
            "Только владелец:\n"
            "• +инспектор ID\n"
            "• -инспектор ID\n\n"
            f"Поддержка: {config.SUPPORT_LINK}\n"
            "Предупреждение: функции в разработке могут работать некорректно."
        )
        return

    if low == "!id":
        target = await resolve_target(message)
        await message.reply(f"ID пользователя: {target[0]}" if target else
                            "Ответь командой !id на сообщение пользователя.")
        return

    if low.startswith("+инспектор") or low.startswith("-инспектор"):
        if not message.from_user or message.from_user.id != config.OWNER_ID:
            await message.reply("Только владелец может управлять инспекторами.")
            return
        adding = low.startswith("+инспектор")
        prefix = "+инспектор" if adding else "-инспектор"
        arg = text[len(prefix):].strip()
        if not arg.isdigit():
            await message.reply(f"Формат: {prefix} ID")
            return
        target_id = int(arg)
        if target_id == config.OWNER_ID:
            await message.reply("Владелец уже имеет полный доступ.")
            return
        if adding:
            await db.add_inspector(target_id, message.from_user.id)
            await message.reply(f"ID {target_id} добавлен в инспекцию.")
        else:
            await db.remove_inspector(target_id)
            await message.reply(f"Доступ инспектора для ID {target_id} снят.")
        return

    if low.startswith(".конф"):
        if not await require_inspector(message):
            return
        arg = text[len(".конф"):].strip()
        target = await resolve_target(message, arg)
        if not target:
            await message.reply("Не удалось найти пользователя. Используй ID, ответ на сообщение или @username, которого бот уже видел.")
            return
        uid, username, name = target
        entry = await db.get_antispam_entry(uid)
        adds, removes = await db.get_antispam_counts(uid)
        ban_count = await db.get_ban_count(uid)
        history = await db.get_ban_history(uid)
        report = (
            "Досье «Конфеты»\n\n"
            f"Имя: {name}\nID: {uid}\n"
            f"Username: @{username if username else 'не известен'}\n\n"
            f"Антиспам: {'ЕСТЬ' if entry else 'НЕТ'}\n"
            f"Добавляли в базу: {adds} раз\n"
            f"Убирали из базы: {removes} раз\n"
            f"Баны, записанные ботом: {ban_count} раз"
        )
        if entry:
            report += f"\nПричина в текущей записи: {entry[0]}"
        if history:
            report += "\n\nПоследние баны:"
            for title, chat_id, reason, actor_id, date in history:
                report += f"\n• {date} — {title} (чат {chat_id})\n  Причина: {reason}"
        else:
            report += "\n\nЗаписанных банов нет."
        await message.reply(report)
        return

    if low.startswith("+антиспам"):
        if not await require_inspector(message):
            return
        arg = text[len("+антиспам"):].strip()
        target = await resolve_target(message, arg.splitlines()[0] if arg else "")
        if not target:
            await message.reply("Формат: +антиспам ID или ответом на сообщение.")
            return
        reason = "\n".join(text.splitlines()[1:]).strip() or "Причина не указана"
        await db.add_to_antispam(target[0], message.from_user.id, reason)
        await message.reply(f"{target[2]} добавлен(а) в общую антиспам-базу.")
        chats = await db.get_groups()
        success = 0
        for chat_id, title in chats:
            try:
                await bot.ban_chat_member(chat_id, target[0])
                await db.add_ban(target[0], chat_id, title or "Без названия",
                                 message.from_user.id, f"Добавление в антиспам-базу: {reason}")
                success += 1
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
        await message.reply(f"Попытки блокировки в известных чатах завершены. Успешно: {success}.")
        return

    if low.startswith("-антиспам"):
        if not await require_inspector(message):
            return
        arg = text[len("-антиспам"):].strip()
        target = await resolve_target(message, arg.splitlines()[0] if arg else "")
        if not target:
            await message.reply("Формат: -антиспам ID или ответом на сообщение.")
            return
        reason = "\n".join(text.splitlines()[1:]).strip()
        await db.remove_from_antispam(target[0], message.from_user.id, reason)
        await message.reply(f"{target[2]} удалён(а) из антиспам-базы. Баны в чатах автоматически не снимаются.")
        return

    if low.startswith("!бан"):
        if not await require_inspector(message):
            return
        target = await resolve_target(message)
        if not target:
            await message.reply("Ответь командой !бан на сообщение пользователя.")
            return
        lines = text.splitlines()
        reason = lines[1].strip() if len(lines) > 1 and lines[1].strip() else "Причина не указана"
        try:
            await bot.ban_chat_member(message.chat.id, target[0])
            await db.add_ban(target[0], message.chat.id, message.chat.title or "Без названия",
                             message.from_user.id, reason)
            await message.reply(f"{target[2]} заблокирован(а) только в этом чате.\nПричина: {reason}")
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            await message.reply(f"Не удалось выполнить бан. Проверь права бота.\n{exc}")
        return

    if low.startswith("!добавить 18+"):
        if not await require_inspector(message):
            return
        name = sticker_set_name(text[len("!добавить 18+"):].strip())
        if not name:
            await message.reply("Укажи ссылку вида https://t.me/addstickers/НазваниеНабора")
            return
        await db.add_sticker_set(name, message.from_user.id)
        await message.reply(f"Набор {name} добавлен в список блокировки.")
        return

    if low == "!список 18+":
        if not await require_inspector(message):
            return
        sets = await db.list_sticker_sets()
        await message.reply("Список пуст." if not sets else
                            "Наборы в списке:\n" + "\n".join(
                                f"• https://t.me/addstickers/{row[0]}" for row in sets))
        return

    if low.startswith("!удалить 18+"):
        if not await require_inspector(message):
            return
        name = sticker_set_name(text[len("!удалить 18+"):].strip())
        if not name:
            await message.reply("Укажи ссылку вида https://t.me/addstickers/НазваниеНабора")
            return
        await db.remove_sticker_set(name)
        await message.reply(f"Набор {name} удалён из списка блокировки.")

async def main():
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_BOT_TOKEN":
        raise RuntimeError("Заполни BOT_TOKEN в файле .env (скопируй .env.example).")
    await db.init_db()
    bot = Bot(token=config.BOT_TOKEN)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
