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
    return await social.rank_data(ctx.db, gid, RANK_KINDS[word])


ROUTES = [
    Route(
        r"^[#]?(打工人|上班族|上班)?(帮助|菜单|功能)$",
        "cmd_help",
        "查看打工人·上班族物语帮助",
        help_cmd,
        priority=5,
    ),
    Route(r"^[#](职场早报|早报|新闻)$", "cmd_news", "查看今日职场早报", news),
    Route(
        r"^[#]?(富豪榜|卷王榜|身价榜|职级榜)$",
        "cmd_rank_board",
        "查看四大职场排行榜",
        rank_board,
    ),
]
