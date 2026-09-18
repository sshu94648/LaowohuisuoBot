import os
import re
import sqlite3
import html
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# =========================================================
# 基础配置
# =========================================================

BOT_TOKEN = os.environ["BOT_TOKEN"]

# 主要资料频道
CHANNEL_USERNAME = "@Laohuisuo"

# 三个互通入口
MENU_TARGETS = [
    ("🏨 三江休闲会所", "@Laohuisuo", "https://t.me/Laohuisuo"),
    ("💬 万象同城交流群", "@LaoWoChatting", "https://t.me/LaoWoChatting"),
    ("🌏 老挝万象—华人社区", "@LaowoGroup", "https://t.me/LaowoGroup"),
]

# Railway 已经设置：
# DB_PATH=/data/bot.db
DB_PATH = os.getenv("DB_PATH", "bot.db")

# 只识别 T/A/C/F + 1～3 位数字
CODE_RE = re.compile(
    r"(?<![A-Z0-9])([TACF]\d{1,3})(?![A-Z0-9])",
    re.I,
)

CATEGORY_PAGE_SIZE = 20


# =========================================================
# 数据库
# =========================================================

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
            INSERT INTO users (
                user_id,
                username,
                first_seen,
                last_seen
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(user_id)
            DO UPDATE SET
                username=excluded.username,
                last_seen=excluded.last_seen
            """,
            (
                user.id,
                user.username,
                ts,
                ts,
            ),
        )

        conn.commit()


def save_code(
    code: str,
    post_url: str,
    message_id: int | None = None,
):
    code = code.upper()

    with db() as conn:

        conn.execute(
            """
            INSERT INTO codes (
                code,
                post_url,
                message_id,
                updated_at
            )
            VALUES (?, ?, ?, ?)

            ON CONFLICT(code)
            DO UPDATE SET
                post_url=excluded.post_url,
                message_id=excluded.message_id,
                updated_at=excluded.updated_at
            """,
            (
                code,
                post_url,
                message_id,
                now_iso(),
            ),
        )

        conn.commit()


def delete_code(code: str) -> bool:
    with db() as conn:

        cur = conn.execute(
            "DELETE FROM codes WHERE code=?",
            (code.upper(),),
        )

        conn.commit()

        return cur.rowcount > 0


def get_code(code: str):
    with db() as conn:

        return conn.execute(
            """
            SELECT *
            FROM codes
            WHERE code=?
            """,
            (code.upper(),),
        ).fetchone()


def natural_code_key(row):
    code = row["code"].upper()

    try:
        return (
            code[0],
            int(code[1:]),
        )
    except Exception:
        return (
            code[0],
            999999,
        )


def get_codes(prefix: str | None = None):
    with db() as conn:

        if prefix:

            rows = conn.execute(
                """
                SELECT *
                FROM codes
                WHERE code LIKE ?
                """,
                (prefix.upper() + "%",),
            ).fetchall()

        else:

            rows = conn.execute(
                """
                SELECT *
                FROM codes
                """
            ).fetchall()

    return sorted(
        rows,
        key=natural_code_key,
    )


def get_latest(limit=12):
    with db() as conn:

        return conn.execute(
            """
            SELECT *
            FROM codes
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


# =========================================================
# 通用工具
# =========================================================

def chunk(items, size=4):
    return [
        items[i:i + size]
        for i in range(
            0,
            len(items),
            size,
        )
    ]


def code_button(code, url):
    return InlineKeyboardButton(
        code,
        url=url,
    )


def main_menu_text():
    return (
        "🇱🇦 <b>万象互通 · 群内导航菜单</b>\n\n"
        "欢迎使用群内导航。\n"
        "点击下方按钮可查看佳丽、按牌字进入，"
        "并在三个群组/频道之间快速互通。\n\n"
        "✨ 万象相连 · 信息互通"
    )


def home_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🌸 T牌字",
                callback_data="cat:T:0",
            ),
            InlineKeyboardButton(
                "✨ A牌字",
                callback_data="cat:A:0",
            ),
        ],

        [
            InlineKeyboardButton(
                "🪷 C牌字",
                callback_data="cat:C:0",
            ),
            InlineKeyboardButton(
                "🦋 F牌字",
                callback_data="cat:F:0",
            ),
        ],

        [
            InlineKeyboardButton(
                "🆕 最新更新",
                callback_data="latest",
            ),
            InlineKeyboardButton(
                "🔎 查询佳丽",
                callback_data="query_help",
            ),
        ],

        [
            InlineKeyboardButton(
                "🏨 三江休闲会所",
                url="https://t.me/Laohuisuo",
            ),
            InlineKeyboardButton(
                "💬 万象同城交流群",
                url="https://t.me/LaoWoChatting",
            ),
        ],

        [
            InlineKeyboardButton(
                "🌏 老挝万象—华人社区",
                url="https://t.me/LaowoGroup",
            ),
            InlineKeyboardButton(
                "📜 使用说明",
                callback_data="guide",
            ),
        ],
    ])


def category_keyboard(prefix, page):
    rows = get_codes(prefix)

    total = len(rows)

    if total == 0:
        return (
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        "🔙 返回菜单",
                        callback_data="home",
                    )
                ]
            ]),
            0,
            0,
        )

    start = page * CATEGORY_PAGE_SIZE

    if start >= total:
        page = 0
        start = 0

    end = min(
        start + CATEGORY_PAGE_SIZE,
        total,
    )

    page_rows = rows[start:end]

    buttons = [
        code_button(
            r["code"],
            r["post_url"],
        )
        for r in page_rows
    ]

    keyboard = chunk(
        buttons,
        4,
    )

    page_count = (
        total + CATEGORY_PAGE_SIZE - 1
    ) // CATEGORY_PAGE_SIZE

    nav = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "◀️ 上一页",
                callback_data=f"cat:{prefix}:{page - 1}",
            )
        )

    if page + 1 < page_count:
        nav.append(
            InlineKeyboardButton(
                "下一页 ▶️",
                callback_data=f"cat:{prefix}:{page + 1}",
            )
        )

    if nav:
        keyboard.append(nav)

    keyboard.append([
        InlineKeyboardButton(
            "🔙 返回菜单",
            callback_data="home",
        )
    ])

    return (
        InlineKeyboardMarkup(keyboard),
        total,
        page_count,
    )


def make_clickable_text(text: str):
    result = []
    missing = []

    last = 0

    for match in CODE_RE.finditer(text):

        start, end = match.span()

        code = match.group(1).upper()

        result.append(
            html.escape(
                text[last:start]
            )
        )

        row = get_code(code)

        if row:

            url = html.escape(
                row["post_url"],
                quote=True,
            )

            result.append(
                f'<a href="{url}">{code}</a>'
            )

        else:

            result.append(code)

            if code not in missing:
                missing.append(code)

        last = end

    result.append(
        html.escape(
            text[last:]
        )
    )

    return (
        "".join(result),
        missing,
    )


# =========================================================
# 管理员权限
# =========================================================

async def is_master_admin(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:

    user = update.effective_user

    if not user:
        return False

    try:

        member = await context.bot.get_chat_member(
            CHANNEL_USERNAME,
            user.id,
        )

        return member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
        }

    except Exception:
        return False


# =========================================================
# 菜单
# =========================================================

async def send_main_menu(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id,
):
    msg = await context.bot.copy_message(
        chat_id=chat_id,
        from_chat_id="@Laohuisuo",
        message_id=1097,
        reply_markup=home_keyboard(),
    )
    return msg


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    touch_user(update)

    await update.effective_message.reply_text(
        main_menu_text(),
        parse_mode="HTML",
        reply_markup=home_keyboard(),
        disable_web_page_preview=True,
    )


async def menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_master_admin(
        update,
        context,
    ):
        await update.effective_message.reply_text(
            "此命令仅限管理员使用。"
        )
        return

    await update.effective_message.reply_text(
        main_menu_text(),
        parse_mode="HTML",
        reply_markup=home_keyboard(),
        disable_web_page_preview=True,
    )


async def menu_all(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_master_admin(
        update,
        context,
    ):
        await update.effective_message.reply_text(
            "此命令仅限管理员使用。"
        )
        return

    results = []

    for name, username, url in MENU_TARGETS:

        try:

            msg = await send_main_menu(
                context,
                username,
            )

            message_link = (
                f"{url}/{msg.message_id}"
            )

            results.append(
                f"✅ {name}\n{message_link}"
            )

        except Exception as e:

            results.append(
                f"❌ {name}\n"
                f"{html.escape(str(e))[:180]}"
            )

    await update.effective_message.reply_text(
        "📌 <b>菜单发布结果</b>\n\n"
        + "\n\n".join(results),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


# =========================================================
# 按钮路由
# =========================================================

async def button_router(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    q = update.callback_query

    await q.answer()

    touch_user(update)

    data = q.data or ""

    # -----------------------------------------------------
    # 返回菜单
    # -----------------------------------------------------

    if data == "home":

        try:

            await q.edit_message_text(
                main_menu_text(),
                parse_mode="HTML",
                reply_markup=home_keyboard(),
                disable_web_page_preview=True,
            )

        except Exception:
            pass

        return

    # -----------------------------------------------------
    # T / A / C / F 牌字
    # -----------------------------------------------------

    if data.startswith("cat:"):

        parts = data.split(":")

        prefix = parts[1].upper()

        try:
            page = int(parts[2])
        except Exception:
            page = 0

        if prefix not in {
            "T",
            "A",
            "C",
            "F",
        }:
            return

        markup, total, page_count = (
            category_keyboard(
                prefix,
                page,
            )
        )

        if total == 0:

            text = (
                f"🌸 <b>{prefix}牌字</b>\n\n"
                "暂时没有已收录佳丽。"
            )

        else:

            current_page = page + 1

            text = (
                f"🌸 <b>{prefix}牌字</b>\n\n"
                f"已收录：<b>{total}</b> 位\n"
                f"第 {current_page}/{page_count} 页\n\n"
                "点击牌字即可查看对应资料。"
            )

        chat_type = (
            q.message.chat.type
            if q.message
            else ""
        )

        # 频道里直接切换当前菜单
        if chat_type == "channel":

            try:

                await q.edit_message_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )

            except Exception:
                pass

        # 群里保留主菜单，另发一个分类面板
        else:

            await q.message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=markup,
                disable_web_page_preview=True,
            )

        return

    # -----------------------------------------------------
    # 最新更新
    # -----------------------------------------------------

    if data == "latest":

        rows = get_latest(12)

        keyboard = []

        if rows:

            buttons = [
                code_button(
                    r["code"],
                    r["post_url"],
                )
                for r in rows
            ]

            keyboard.extend(
                chunk(
                    buttons,
                    4,
                )
            )

        keyboard.append([
            InlineKeyboardButton(
                "🔙 返回菜单",
                callback_data="home",
            )
        ])

        text = (
            "🆕 <b>最新更新</b>\n\n"
            "点击牌字查看最新佳丽资料："
            if rows
            else
            "🆕 <b>最新更新</b>\n\n"
            "暂时没有已收录资料。"
        )

        chat_type = (
            q.message.chat.type
            if q.message
            else ""
        )

        if chat_type == "channel":

            try:

                await q.edit_message_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(
                        keyboard
                    ),
                )

            except Exception:
                pass

        else:

            await q.message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                ),
            )

        return

    # -----------------------------------------------------
    # 查询佳丽说明
    # -----------------------------------------------------

    if data == "query_help":

        text = (
            "🔎 <b>查询佳丽</b>\n\n"
            "直接在群内发送完整牌字即可查询。\n\n"
            "例如：\n"
            "<code>T77</code>\n"
            "<code>A26</code>\n"
            "<code>C89</code>\n"
            "<code>F128</code>\n\n"
            "机器人会返回对应资料入口。"
        )

        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 返回菜单",
                    callback_data="home",
                )
            ]
        ])

        chat_type = (
            q.message.chat.type
            if q.message
            else ""
        )

        if chat_type == "channel":

            try:

                await q.edit_message_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )

            except Exception:
                pass

        else:

            await q.message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=markup,
            )

        return

    # -----------------------------------------------------
    # 使用说明
    # -----------------------------------------------------

    if data == "guide":

        text = (
            "📜 <b>使用说明</b>\n\n"
            "🌸 T牌字：查看 T 分类\n"
            "✨ A牌字：查看 A 分类\n"
            "🪷 C牌字：查看 C 分类\n"
            "🦋 F牌字：查看 F 分类\n\n"
            "🆕 最新更新：查看最近新增资料\n"
            "🔎 查询佳丽：输入牌字直接查询\n\n"
            "下方三个入口可在三江休闲会所、"
            "万象同城交流群和老挝万象—华人社区"
            "之间快速跳转。"
        )

        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔙 返回菜单",
                    callback_data="home",
                )
            ]
        ])

        chat_type = (
            q.message.chat.type
            if q.message
            else ""
        )

        if chat_type == "channel":

            try:

                await q.edit_message_text(
                    text,
                    parse_mode="HTML",
                    reply_markup=markup,
                )

            except Exception:
                pass

        else:

            await q.message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=markup,
            )

        return


# =========================================================
# 用户输入牌字查询
# =========================================================

async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    msg = update.effective_message

    if not msg:
        return

    text = (
        msg.text or ""
    ).strip().upper()

    # -----------------------------------------------------
    # 单个牌字查询
    # -----------------------------------------------------

    match = CODE_RE.fullmatch(text)

    if match:

        touch_user(update)

        code = match.group(1).upper()

        row = get_code(code)

        if not row:

            await msg.reply_text(
                f"暂未收录 {code}。"
            )

            return

        await msg.reply_text(
            f"🌸 查询结果：<b>{code}</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        f"查看 {code} 资料",
                        url=row["post_url"],
                    )
                ]
            ]),
        )

        return

    # -----------------------------------------------------
    # 群里其他聊天不回复，避免刷屏
    # -----------------------------------------------------

    if update.effective_chat.type != "private":
        return

    # -----------------------------------------------------
    # 私聊批量牌字
    # -----------------------------------------------------

    found = CODE_RE.findall(text)

    if not found:
        return

    clickable_text, missing = (
        make_clickable_text(
            msg.text or ""
        )
    )

    await msg.reply_text(
        clickable_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    if missing:

        await msg.reply_text(
            "⚠️ 以下牌字尚未录入：\n"
            + "、".join(missing)
        )


# =========================================================
# 自动监听三江休闲会所频道
# =========================================================

async def index_channel_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    msg = (
        update.channel_post
        or update.edited_channel_post
    )

    if not msg:
        return

    chat_username = (
        msg.chat.username
        or ""
    ).lower()

    if (
        chat_username
        != CHANNEL_USERNAME
        .lstrip("@")
        .lower()
    ):
        return

    source_text = " ".join(
        part
        for part in [
            msg.caption,
            msg.text,
        ]
        if part
    ).upper()

    codes = sorted(
        set(
            m.upper()
            for m in
            CODE_RE.findall(
                source_text
            )
        )
    )

    if not codes:
        return

    post_url = (
        f"https://t.me/"
        f"{msg.chat.username}/"
        f"{msg.message_id}"
    )

    for code in codes:

        save_code(
            code,
            post_url,
            msg.message_id,
        )


# =========================================================
# 管理员：录入
# =========================================================

async def admin_set(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_master_admin(
        update,
        context,
    ):

        await update.effective_message.reply_text(
            "此命令仅限管理员使用。"
        )

        return

    if len(context.args) != 2:

        await update.effective_message.reply_text(
            "格式：\n"
            "/set T77 "
            "https://t.me/Laohuisuo/1084"
        )

        return

    code = context.args[0].upper()

    url = context.args[1]

    if not CODE_RE.fullmatch(code):

        await update.effective_message.reply_text(
            "牌字格式不正确。\n"
            "例如：T77、A26、C89、F128。"
        )

        return

    if not url.startswith(
        "https://t.me/"
    ):

        await update.effective_message.reply_text(
            "必须填写 Telegram 帖子链接。"
        )

        return

    save_code(
        code,
        url,
    )

    await update.effective_message.reply_text(
        f"✅ {code} 已保存/更新。"
    )


# =========================================================
# 管理员：删除
# =========================================================

async def admin_del(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_master_admin(
        update,
        context,
    ):

        await update.effective_message.reply_text(
            "此命令仅限管理员使用。"
        )

        return

    if len(context.args) != 1:

        await update.effective_message.reply_text(
            "格式：/del T77"
        )

        return

    code = context.args[0].upper()

    ok = delete_code(code)

    await update.effective_message.reply_text(
        (
            f"✅ {code} 已删除。"
            if ok
            else f"未找到 {code}。"
        )
    )


# =========================================================
# 管理员：统计
# =========================================================

async def admin_stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_master_admin(
        update,
        context,
    ):

        await update.effective_message.reply_text(
            "此命令仅限管理员使用。"
        )

        return

    with db() as conn:

        code_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM codes
            """
        ).fetchone()[0]

        user_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM users
            """
        ).fetchone()[0]

    await update.effective_message.reply_text(
        "📊 <b>机器人统计</b>\n\n"
        f"已收录佳丽：{code_count}\n"
        f"使用过查询：{user_count}",
        parse_mode="HTML",
    )


# =========================================================
# 管理员：发布可点击出勤名单
# =========================================================

async def admin_publish(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not await is_master_admin(
        update,
        context,
    ):

        await update.effective_message.reply_text(
            "此命令仅限管理员使用。"
        )

        return

    text = (
        update.effective_message.text
        or ""
    )

    parts = text.split(
        "\n",
        1,
    )

    if (
        len(parts) < 2
        or not parts[1].strip()
    ):

        await update.effective_message.reply_text(
            "使用方法：\n\n"
            "/publish\n"
            "今日出勤\n\n"
            "T77\n"
            "A26\n"
            "C89\n"
            "F128"
        )

        return

    body = parts[1].strip()

    clickable_text, missing = (
        make_clickable_text(
            body
        )
    )

    if missing:

        await update.effective_message.reply_text(
            "❌ 暂未发布。\n\n"
            "以下牌字还没有资料链接：\n"
            + "、".join(missing)
        )

        return

    sent = await context.bot.send_message(
        chat_id=CHANNEL_USERNAME,
        text=clickable_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    await update.effective_message.reply_text(
        "✅ 已发布到三江休闲会所。\n\n"
        f"https://t.me/"
        f"{CHANNEL_USERNAME.lstrip('@')}/"
        f"{sent.message_id}"
    )


# =========================================================
# 启动
# =========================================================

def main():

    init_db()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # 用户菜单
    app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    # 管理员发送当前群菜单
    app.add_handler(
        CommandHandler(
            "menu",
            menu,
        )
    )

    # 一次发送到两个群 + 一个频道
    app.add_handler(
        CommandHandler(
            "menuall",
            menu_all,
        )
    )

    # 管理员资料维护
    app.add_handler(
        CommandHandler(
            "set",
            admin_set,
        )
    )

    app.add_handler(
        CommandHandler(
            "del",
            admin_del,
        )
    )

    app.add_handler(
        CommandHandler(
            "stats",
            admin_stats,
        )
    )

    app.add_handler(
        CommandHandler(
            "publish",
            admin_publish,
        )
    )

    # 菜单按钮
    app.add_handler(
        CallbackQueryHandler(
            button_router
        )
    )

    # 监听频道新帖
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POSTS,
            index_channel_post,
        )
    )

    # 私聊和群聊牌字查询
    app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            handle_text,
        )
    )

    print(
        "LaowohuisuoBot is running..."
    )

    app.run_polling(
        allowed_updates=[
            "message",
            "callback_query",
            "channel_post",
            "edited_channel_post",
        ]
    )


if __name__ == "__main__":
    
