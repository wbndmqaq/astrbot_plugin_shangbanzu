"""系统指令路由：帮助、职场早报、四大排行榜。"""

from ..core import gamedata as gd
from ..core import social
from ..core.result import R
from .base import Route

HELP_FALLBACK = (
    "🏢 打工人·上班族物语\n"
    "职业线：找工作/上班(通勤+五险一金)/摸鱼/加班(得调休券)/请假/请调休/写周报/晋升/加薪谈判/跳槽/辞职\n"
    "成长线：进修(提身价)/团建/购物/摆摊/对线 @群友/参加卷王大赛(亲自出战)\n"
    "生活线：吃饭/午休/健身/租房/通勤/买房/工资条/商店/购买/我的简历\n"
    "理财线：存款N/取款N/领取利息/升级信用/转账N@群友/买基金N/卖出基金\n"
    "排行：富豪榜/卷王榜/身价榜/职级榜/职场早报/人才市场(同事录)"
)

RANK_KINDS = {
    "富豪榜": "wealth",
    "卷王榜": "exp",
    "身价榜": "value",
    "职级榜": "level",
}


async def help_cmd(ctx, event):
    help_data = gd.t("help", "sections")
    total_cmds = sum(len(s.get("commands", [])) for s in help_data)
    webui_port = int(ctx.c("webui_port", 17817))

    img = await ctx.render(
        "help",
        {
            "sections": help_data,
            "total_cmds": total_cmds,
            "company_count": len(gd.companies()),
            "webui_port": webui_port,
        },
    )
    if img:
        return R(img=img)
    return R(text=HELP_FALLBACK)


async def news(ctx, event):
    headline = gd.news_of_day()
    return R(
        tmpl="panel",
        data={
            "icon": "📰",
            "title": "职场早报 · 今日份的离谱",
            "accent": "#ffd86f",
            "lines": [headline],
            "foot": "早报每日更新，全服共享同一份",
        },
        text=f"【职场早报】{headline}",
    )


async def rank_board(ctx, event):
    gid = event.get_group_id() or ""
    if not gid:
        return R(err="该游戏只能在群聊中使用")
    word = next((w for w in RANK_KINDS if w in (event.message_str or "")), None)
    if not word:
        return R(err="未知排行榜")
    return await social.rank_data(ctx.db, gid, RANK_KINDS[word], ctx.app_id)


async def today_event(ctx, event):
    from ..core import logic
    today = logic.today_str()
    import random
    events_pool = [
        ("🚀 行业风口来袭", "今日全员打卡收益与经验提升 +30%！站在风口上，猪都能飞！", "#6fe08c"),
        ("🚨 突击大检查", "今日各公司摸鱼被抓概率上升，各位打工人请务必留意领导动向！", "#fc6262"),
        ("☕ 全员下午茶日", "今日公司福利大放送，所有生活消费与吃饭精神恢复翻倍！", "#ffd86f"),
        ("⚡ 行业黑天鹅", "今日股市震荡加剧，裁员风险小幅波动，请系好安全带！", "#b48cff"),
        ("🏖️ 提早下班令", "今日加班获得的调休券掉率提升至 50%，打工人狂喜！", "#7fd1ff"),
    ]
    seed_val = int(today.replace("-", ""))
    rng = random.Random(seed_val)
    title, desc, accent = rng.choice(events_pool)

    return R(
        tmpl="panel",
        data={
            "icon": "📢",
            "title": f"今日突发群事件 · {today}",
            "accent": accent,
            "lines": [f"【{title}】", desc],
            "foot": "全群今日生效，次日 00:00 刷新",
        },
        text=f"📢 今日群突发事件【{title}】：{desc}",
    )


ROUTES = [
    Route(
        r"^[#]?(打工人|上班族|上班)?(帮助|菜单|功能)$",
        "cmd_help",
        "查看打工人·上班族物语帮助",
        help_cmd,
        priority=5,
    ),
    Route(r"^[#]?(职场早报|早报|新闻)$", "cmd_news", "查看今日职场早报", news),
    Route(r"^[#]?(今日事件|群事件|突发事件)$", "cmd_today_event", "查看今日全群突发公共事件与全员Buff", today_event),
    Route(
        r"^[#]?(富豪榜|卷王榜|身价榜|职级榜)$",
        "cmd_rank_board",
        "查看四大职场排行榜",
        rank_board,
    ),
]
