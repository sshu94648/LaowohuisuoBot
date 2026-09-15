import os
import re
import sqlite3
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]

CHANNEL_USERNAME = "@Laohuisuo"
CHANNEL_PUBLIC_NAME = "万象三江频道"

COMMUNITY_LINKS = [
    ("🔥 老挝万象—华人社区", "https://t.me/LaowoGroup"),
    ("💬 万象同城交流群", "https://t.me/LaoWoChatting"),
    ("📢 万象便民信息频道", "https://t.me/ViantianeNews"),
    ("🏨 万象三江频道", "https://t.me/Laohuisuo"),
]

DB_PATH = os.getenv("DB_PATH", "bot.db")
CODE_RE = re.compile(r"(?<![A-Z0-9])([TACF]\d{1,3})(?![A-Z0-9])", re.I)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS codes (
                code TEXT PRIMARY KEY,
                post_url TEXT NOT NULL,
                message_id INTEGER,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
            """
        )
        conn.commit()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def touch_user(update: Update):
    user = update.effective_user
    if not user:
        return
    ts = now_iso()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO users(user_id, username, first_seen, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                last_seen=excluded.last_seen
            """,
            (user.id, user.username, ts, ts),
        )
        conn.commit()


def save_code(code: str, post_url: str, message_id: int | None = None):
    code = code.upper()
    with db() as conn:
        conn.execute(
            """
            INSERT INTO codes(code, post_url, message_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                post_url=excluded.post_url,
                message_id=excluded.message_id,
                updated_at=excluded.updated_at
            """,
            (code, post_url, message_id, now_iso()),
        )
        conn.commit()


def delete_code(code: str) -> bool:
    with db() as conn:
        cur = conn.execute("DELETE FROM codes WHERE code=?", (code.upper(),))
        conn.commit()
        return cur.rowcount > 0


def get_code(code: str):
    with db() as conn:
        return conn.execute("SELECT * FROM codes WHERE code=?", (code.upper(),)).fetchone()


def get_codes(prefix: str | None = None):
    with db() as conn:
        if prefix:
            return conn.execute(
                "SELECT * FROM codes WHERE code LIKE ? ORDER BY code",
                (prefix.upper() + "%",),
            ).fetchall()
        return conn.execute("SELECT * FROM codes ORDER BY code").fetchall()


def get_latest(limit=12):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM codes ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()


def code_button(code, url):
    return InlineKeyboardButton(code, url=url)


def chunk(items, size=4):
    return [items[i:i+size] for i in range(0, len(items), size)]


def home_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("T 系列", callback_data="cat:T"),
            InlineKeyboardButton("A 系列", callback_data="cat:A"),
        ],
        [
            InlineKeyboardButton("C 系列", callback_data="cat:C"),
            InlineKeyboardButton("F 系列", callback_data="cat:F"),
        ],
        [
            InlineKeyboardButton("🆕 最新更新", callback_data="latest"),
            InlineKeyboardButton("🌏 华人社区导航", callback_data="nav"),
        ],
        [InlineKeyboardButton("🏨 打开频道", url="https://t.me/Laohuisuo")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    touch_user(update)
    text = (
        "🇱🇦 <b>万象三江 · 代码查询</b>\n\n"
        "请选择分类，或直接发送代码查询。\n"
        "例如：<code>T55</code>、<code>A15</code>、<code>F128</code>\n\n"
        "点击代码即可打开频道内对应图片。"
    )
    await update.effective_message.reply_text(
        text, reply_markup=home_keyboard(), parse_mode="HTML"
    )


async def handle_private_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    touch_user(update)
    text = (update.effective_message.text or "").strip().upper()
    match = CODE_RE.fullmatch(text)
    if not match:
        await update.effective_message.reply_text(
            "请输入完整代码，例如：T55、A15、C89、F128。",
            reply_markup=home_keyboard(),
        )
        return

    code = match.group(1).upper()
    row = get_code(code)
    if not row:
        await update.effective_message.reply_text(
            f"暂未收录 {code}。\n\n如果这是旧频道内容，需要管理员先补录。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 返回首页", callback_data="home")]
            ]),
        )
        return

    await update.effective_message.reply_text(
        f"🔎 查询结果：<b>{code}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🖼 查看 {code} 图片", url=row["post_url"])],
            [InlineKeyboardButton("🔙 返回首页", callback_data="home")],
        ]),
    )


async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    touch_user(update)

    data = q.data

    if data == "home":
        await q.edit_message_text(
            "🇱🇦 <b>万象三江 · 代码查询</b>\n\n请选择分类，或直接发送代码查询。",
            parse_mode="HTML",
            reply_markup=home_keyboard(),
        )
        return

    if data.startswith("cat:"):
        prefix = data.split(":", 1)[1]
        rows = get_codes(prefix)
        if rows:
            btns = [code_button(r["code"], r["post_url"]) for r in rows]
            keyboard = chunk(btns, 4)
            keyboard.append([InlineKeyboardButton("🔙 返回首页", callback_data="home")])
            markup = InlineKeyboardMarkup(keyboard)
            text = f"<b>{prefix} 系列</b> · 共 {len(rows)} 个代码\n\n点击代码查看对应图片："
        else:
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 返回首页", callback_data="home")]
            ])
            text = f"<b>{prefix} 系列</b>\n\n暂时没有已收录代码。"
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        return

    if data == "latest":
        rows = get_latest(12)
        keyboard = []
        if rows:
            btns = [code_button(r["code"], r["post_url"]) for r in rows]
            keyboard.extend(chunk(btns, 4))
        keyboard.append([InlineKeyboardButton("🔙 返回首页", callback_data="home")])
        await q.edit_message_text(
            "🆕 <b>最近更新</b>\n\n点击代码查看图片："
            if rows else "🆕 暂无已收录代码。",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data == "nav":
        keyboard = [[InlineKeyboardButton(name, url=url)] for name, url in COMMUNITY_LINKS]
        keyboard.append([InlineKeyboardButton("🔙 返回首页", callback_data="home")])
        await q.edit_message_text(
            "🌏 <b>老挝万象—华人社区导航</b>\n\n请选择入口：",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return


async def index_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post or update.edited_channel_post
    if not msg:
        return

    chat_username = (msg.chat.username or "").lower()
    if chat_username != CHANNEL_USERNAME.lstrip("@").lower():
        return

    source_text = " ".join(
        part for part in [msg.caption, msg.text] if part
    ).upper()

    codes = sorted(set(m.upper() for m in CODE_RE.findall(source_text)))
    if not codes:
        return

    post_url = f"https://t.me/{msg.chat.username}/{msg.message_id}"
    for code in codes:
        save_code(code, post_url, msg.message_id)


async def is_channel_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user.id)
        return member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }
    except Exception:
        return False


async def admin_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_channel_admin(update, context):
        await update.effective_message.reply_text("此命令仅限频道管理员使用。")
        return

    if len(context.args) != 2:
        await update.effective_message.reply_text(
            "格式：/set T55 https://t.me/Laohuisuo/123"
        )
        return

    code = context.args[0].upper()
    url = context.args[1]

    if not CODE_RE.fullmatch(code):
        await update.effective_message.reply_text("代码格式不正确，例如 T55。")
        return

    if not url.startswith("https://t.me/"):
        await update.effective_message.reply_text("链接必须是 Telegram 帖子链接。")
        return

    save_code(code, url)
    await update.effective_message.reply_text(f"✅ {code} 已保存/更新。")


async def admin_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_channel_admin(update, context):
        await update.effective_message.reply_text("此命令仅限频道管理员使用。")
        return

    if len(context.args) != 1:
        await update.effective_message.reply_text("格式：/del T55")
        return

    code = context.args[0].upper()
    ok = delete_code(code)
    await update.effective_message.reply_text(
        f"✅ {code} 已删除。" if ok else f"未找到 {code}。"
    )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_channel_admin(update, context):
        await update.effective_message.reply_text("此命令仅限频道管理员使用。")
        return

    with db() as conn:
        code_count = conn.execute("SELECT COUNT(*) FROM codes").fetchone()[0]
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    await update.effective_message.reply_text(
        f"📊 机器人统计\n\n已收录代码：{code_count}\n使用过机器人：{user_count}"
    )


def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("set", admin_set))
    app.add_handler(CommandHandler("del", admin_del))
    app.add_handler(CommandHandler("stats", admin_stats))

    app.add_handler(CallbackQueryHandler(button_router))

    # 频道新帖 + 编辑后的频道帖
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POSTS,
            index_channel_post,
        )
    )

    # 用户私聊输入代码
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            handle_private_text,
        )
    )

    print("LaowohuisuoBot is running...")
    app.run_polling(
        allowed_updates=[
            "message",
            "callback_query",
            "channel_post",
            "edited_channel_post",
        ]
    )


if __name__ == "__main__":
    main()
