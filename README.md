# @LaowohuisuoBot 第一版

功能：
- 自动监听 @Laohuisuo 新频道帖
- 从图片说明/文字中识别 T/A/C/F + 数字代码
- 自动建立“代码 → 频道帖子链接”
- 用户私聊输入 T55 / A15 / F128 即可查询
- T/A/C/F 分类浏览
- 最新更新
- 华人社区导航
- 管理员手工补录 `/set`
- 管理员删除 `/del`
- 简单统计 `/stats`

## 1. 安装 Python

建议 Python 3.11 或 3.12。

## 2. 安装依赖

```bash
pip install -r requirements.txt
```

## 3. 设置 Bot Token

Linux / macOS:

```bash
export BOT_TOKEN="你的BotFather Token"
```

Windows PowerShell:

```powershell
$env:BOT_TOKEN="你的BotFather Token"
```

不要把 Token 写进公开代码仓库。

## 4. 启动

```bash
python bot.py
```

## 5. 测试自动收录

在 @Laohuisuo 发一张新图片，并在图片说明中写：

```text
T55
```

机器人运行时会自动保存：

```text
T55 -> https://t.me/Laohuisuo/该消息ID
```

然后私聊 @LaowohuisuoBot，发送：

```text
T55
```

即可看到“查看 T55 图片”按钮。

同一条频道帖子里如果写：

```text
T55 A15 F128
```

机器人会把三个代码都指向这一条帖子。

## 6. 旧图片补录

因为机器人无法自动读取加入之前的全部历史消息，旧图片可手工补录：

```text
/set T55 https://t.me/Laohuisuo/123
```

删除：

```text
/del T55
```

统计：

```text
/stats
```

管理员身份通过“是否为 @Laohuisuo 管理员”自动判断，不需要在代码里写你的 Telegram ID。

## 7. 当前社区导航

- https://t.me/LaowoGroup
- https://t.me/LaoWoChatting
- https://t.me/ViantianeNews
- https://t.me/Laohuisuo

如果其中任何入口需要更换，直接修改 `COMMUNITY_LINKS` 即可。

## 8. 部署

本地测试通过后，可部署到 Railway / Render / VPS。
如果平台支持环境变量，只需要设置：

```text
BOT_TOKEN=你的Token
```

注意：SQLite 数据库如果部署到没有持久磁盘的平台，重启/重新部署后可能丢数据。
正式长期运行建议使用带持久磁盘的 VPS，或下一版改成 PostgreSQL。
