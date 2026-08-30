# 🏢 打工人 · 上班族物语

AstrBot 大型群聊职场生存模拟插件。
AstrBot 大型群聊职场生存模拟插件。以「上班族的现实」为主题：入职公司、每日打卡领薪
（通勤+五险一金+迟到判定）、摸鱼被抓、加班住院攒调休券、写周报评绩效、和领导谈加薪、
被裁员拿补偿、挤地铁通勤、交房租、吃外卖、买基金绿到发光、买股票追涨杀跌，
团建购物两不误，攒够公积金全款买房安家；玩家之间方案评审式对线撕逼，
亲自出战卷王大赛冲击「传奇卷王」段位。

- 💾 用户数据：**SQLite**（标准库，WAL 模式 + 线程安全写锁 + 原子资金操作）
- 📝 游戏文本：**JSON**（`resources/texts/`，1136+ 条文案，可自行扩充）
- 🖼️ 全部输出：**独立 Playwright 渲染器**（Chromium 截图，失败自动回退纯文本）
- 🌐 独立端口 **WebUI** 面板（**aiohttp** 实现，支持密码登录与全量管理，桌面/手机自适应）
- 🔌 适配 **OneBot v11** 与 **QQ 官方机器人**（仅用文本/图片/@ 组件）

---

## 🚀 安装方式：WebUI 插件市场

AstrBot WebUI → 插件管理 → 搜索 `astrbot_plugin_shangbanzu` → 安装。

---

### 卡片渲染环境安装教程（可选，不影响文字回复）

卡片渲染基于本地 Playwright 截图实现。出于安全考虑，插件**绝不会**自动执行任何系统级安装——不修改 apt 源、不运行 apt-get、不自动 pip 装包、不自动下载浏览器内核。需要图片卡片时请按下面步骤手动安装（约 1~2 分钟）：

#### ① 安装 playwright Python 包

```bash
pip install playwright
# 国内网络可用清华镜像：
pip install playwright -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### ② 下载 Chromium 浏览器内核

```bash
python -m playwright install chromium
# 国内网络可用 npmmirror 加速：
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/ python -m playwright install chromium
```

Windows PowerShell 写法：

```powershell
$env:PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright/"
python -m playwright install chromium
```

#### ③（仅 Linux / Docker 容器）安装系统运行库

仅当启动渲染时报 `libnspr4` / `libnss3` / `error while loading shared libraries` 才需要，需 root：

```bash
python -m playwright install-deps chromium
```

或手动安装系统库：

```bash
apt-get update && apt-get install -y \
  libnspr4 libnss3 libgbm1 libasound2 \
  libatk-bridge2.0-0 libatk1.0-0 libcairo2 libcups2 libdrm2 \
  libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 libxfixes3 \
  libxkbcommon0 libxrandr2 libxext6 libpango-1.0-0
```

容器内 apt 官方源下载慢？可选换阿里镜像源后再装：

```bash
# Debian 12 (bookworm)
sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources
# Ubuntu 22.04
sed -i 's|archive.ubuntu.com|mirrors.aliyun.com|g' /etc/apt/sources.list
apt-get update
```

#### ④ 重载插件

WebUI → 插件管理 → 本插件 → 重载。

环境未就绪时，日志会输出一次完整指引，所有指令自动回退纯文本展示；安装完成后重载即可正常出图。

---

## 🧩 插件架构（模块化）

```text
astrbot_plugin_shangbanzu/
├── main.py                  # 主入口：生命周期 + 输出渲染 + 路由安装
├── metadata.yaml            # 插件元数据（版本规范 PEP 440）
├── _conf_schema.json        # 215 项配置 Schema（含 min/max，WebUI 在线调参即时生效）
├── handlers/                # 【指令路由层】声明式路由表（共 93 条指令，其中 4 条管理员）
│   ├── base.py              #   Route + install() 动态安装器 + 每用户指令锁
│   ├── system_cmds.py       #   帮助 / 早报 / 今日事件 / 四大排行
│   ├── career_cmds.py       #   职业：找工作→打卡→摸鱼→加班→晋升→跳槽→辞职 / 创业
│   ├── company_cmds.py      #   加薪谈判 / 进修 / 同事录
│   ├── battle_cmds.py       #   对线 / 卷王大赛（亲自出战）
│   ├── life_cmds.py         #   吃饭/健身/租房/通勤/团建/购物/买房/工资条/道具
│   ├── life2_cmds.py        #   办公室日常：开会/带饭/抢会议室/峰会/宠物/考证
│   ├── finance_cmds.py      #   银行/利息/转账/基金买卖
│   ├── stock_cmds.py        #   股市行情/持仓/买入/卖出
│   ├── extra_cmds.py        #   年终奖/技能/社交/成就称号/红包/刮刮乐
│   ├── lottery_cmds.py      #   游戏化双色球彩票（累积奖池，每日自动开奖）
│   ├── extra2_cmds.py       #   年会抽奖/借钱/建议/工位升级/加班餐/体检
│   ├── market_cmds.py       #   跳槽市场（在招公司一览）
│   ├── review_cmds.py       #   年终考评
│   ├── push_cmds.py         #   每日群推送开关与状态
│   └── backup_cmds.py       #   SQLite 在线数据备份系列（管理员）
├── core/                    # 【业务服务层】
│   ├── db.py                #   SQLite 核心（players 57 列 + 13 张表，原子资金操作 + 增量写回防丢失）
│   ├── context.py           #   GameCtx（群昵称拉取 + TTL 缓存）
│   ├── result.py            #   R() 统一返回结构
│   ├── renderer.py          #   Playwright 渲染器（driver 复用与回收）
│   ├── logic.py             #   业务通用纯函数（cooldown / 金额解析 / 安全钳制）
│   ├── gamedata.py          #   JSON 静态数据加载（含 values/t 副本保护）
│   ├── backup.py            #   在线快照备份管理器
│   ├── stocks.py            #   100 支股票波动与交易（原子买卖 + 持仓只数上限）
│   ├── career.py            #   职业核心服务
│   ├── life.py              #   生活消费服务
│   ├── life2.py             #   日常扩展服务
│   ├── social.py            #   对线与卷王大赛服务
│   ├── finance.py           #   金融理财服务
│   └── extra.py / extra2.py #   红包/成就/年会/体检/工位等扩展
├── webui/                #   独立端口管理面板（默认 127.0.0.1:17817）
│   ├── server.py            #   aiohttp + 鉴权中间件 + CSP/Origin 校验 + 登录限流 + 26 个管理 API
│   ├── index.html           #   响应式管理面板页面
│   ├── style.css            #   深浅色主题样式（含移动端适配层）
│   └── app.js               #   前端交互与数据流控制
└── resources/
    ├── texts/*.json         #   游戏文案库（1136+ 条）
    ├── data/*.json          #   公司 116 家 / 职级 12 阶 / 房产 12 档 / 股票 100 支 / 宠物 2 种
    │                       #   + 饭价 3 档 / 通勤 4 种 / 证书 4 种 / 刮刮乐 4 档 / 商店 29 件 / 对手 25 名 / 工位 5 档
    └── templates/*.html     #   Jinja2 渲染模板（8 套）
```

---

## 📮 用户群

QQ 群（插件讨论）：[点击加入](https://qm.qq.com/q/8sOZdZTnaw)

---

## 🎮 完整指令一览

> 指令支持直接发送或带 `#` 前缀触发（例如 `打卡` 或 `#打卡`）。下表为完整指令速查（共 93 条，含 4 条管理员指令）。

| 分类 | 指令示例 | 说明 |
|---|---|---|
| ℹ️ **系统** | `上班族帮助` / `职场早报` / `今日事件` | 帮助菜单 / 每日早报 / 全群突发公共事件 |
| 💼 **职业** | `找工作 [公司名]` / `我的公司` | 投简历入职指定或推荐公司（群友自建公司同样可投） / 查看雇主详情 |
| 💼 **职业** | `上班` / `打卡` | 每日打卡领薪（自动扣通勤、五险一金、房租，触发随机事件） |
| 💼 **职业** | `摸鱼` / `加班` | 摸鱼回蓝（小心被抓罚款）/ 加班赚钱涨经验（概率拿调休券） |
| 💼 **职业** | `请假` / `请调休` / `写周报` | 请假回血 / 消耗调休券带薪休假 / 评绩效拿奖金 |
| 💼 **职业** | `加薪` / `晋升` / `跳槽` / `辞职` | 谈涨薪 / 职级提升 / 换公司 / 裸辞 |
| 💼 **成长** | `学技能 [编程/设计/管理/演讲/外语]` / `进修` / `摆摊` / `副业升级` | 学硬技能（提升加班收益与晋升成功率）/ 自费进修班提升身价 / 下班摆摊赚外快 / 升级副业等级 |
| 👑 **创业** | `创建公司 [名称]` / `公司分红` | 身价/职级达标后自建企业当老板，提取企业利润分红 |
| 🏠 **生活** | `吃饭 [外卖/食堂/大餐]` / `午休` / `健身` | 恢复健康与精神值 |
| 🏠 **生活** | `租房 [房型]` / `买房` / `通勤 [交通方式]` | 搬家 / 全款购房安家 / 设定地铁/公交/骑车/打车 |
| 🏠 **生活** | `商店` / `购买 [道具]` / `我的背包` / `使用 [道具]` | 便利店购买功能道具卡并使用（护盾/拉屎卡/咖啡/雷达） |
| 🏠 **生活** | `工资条` / `购物` / `团建` | 查看收支流水明细 / 网购剁手 / 公司团建 |
| 🐱 **宠物** | `养猫` / `养狗` / `撸猫` / `遛狗` | 领养宠物陪伴，每日互动恢复精神 |
| ⚔️ **对抗** | `对线 @群友` / `卷王大赛` / `参加卷王大赛` | 与群友方案撕逼 / 查看段位（ELO 积分）/ 亲自出战冲击传奇卷王 |
| 🤝 **社交** | `发红包 [金额] [个数]` / `抢红包` | 群内塞拼手气红包，全群开抢 |
| 🤝 **社交** | `职场社交 @群友` / `带饭 @群友` / `和同事吃饭` | 喝奶茶建人脉 / 帮同事带饭 / 同事拼饭 |
| 🤝 **社交** | `我的成就` / `佩戴称号 [名称]` / `卸下称号` | 查看职场里程碑并佩戴专属头衔展示 |
| 🤝 **社交** | `刮刮乐` | 购买职场刮刮乐（小赌怡情，最高赢取 5000 元） |
| 🏢 **办公室** | `开会` / `回消息` / `抢会议室` / `帮领导做事` | 职场日常操作与应酬 |
| 🏢 **办公室** | `行业峰会` / `考证 [PMP/CPA/法考/CFA]` / `旅游` | 参与高端峰会 / 考取**证书**（与「学技能」不同：技能=编程/设计/管理/演讲/外语，按概率学习；证书=PMP/CPA/法考/CFA，按报名费+通过率考试）/ 度假散心 |
| 🎁 **福利** | `年会抽奖` / `工位升级` / `加班餐` / `年度体检` | 年底抽现金大奖 / 工位升星 / 免费夜宵 / 体检回血 |
| 🎁 **福利** | `请年假` / `年终奖` / `年终考评` | 消耗年假休息 / 每年年终奖 / 年度绩效评定（S/A/B/C/D） |
| 🪙 **理财** | `存款 [金额]` / `取款 [金额]` / `领取利息` | 银行存款，每小时单利计息（每日设上限） |
| 🎰 **彩票** | `买彩票 3` / `买彩票 3 7 12 5` / `我的彩票` / `奖池` / `开奖结果` | 游戏化双色球（红1~16选3+蓝1~8选1）：机选或自选，购票款全部进池，每晚自动开奖，无人中奖滚存下期 |
| 🪙 **理财** | `升级信用` / `一键存款` / `转账 [金额] @群友` | 提升存款上限 / 全部存入 / 个人间原子安全转账 |
| 📊 **基金** | `买基金 [金额]` / `卖出基金 [比例%]` | 申购基金，净值每日波动，按比例赎回 |
| 📈 **股票** | `股市` / `我的股票` / `持仓` | 查看 100 支股票行情 / 查看持仓盈亏 |
| 📈 **股票** | `买股票 [代码/名称] [金额]` / `卖出 [代码/名称] [比例%]` | 股票交易与止盈止损（比例可省略 %） |
| 🏆 **排行** | `富豪榜` / `卷王榜` / `身价榜` / `职级榜` | 群内四大维度排行榜单：**富豪榜=总资产、卷王榜=经验值 exp、身价榜=value、职级榜=lvl**。注意与「卷王大赛 ELO 积分」是两套独立数值——前者按经验，后者按段位分 |
| 📰 **资讯** | `职场建议` / `职场八卦` / `跳槽市场` | 毒鸡汤 / 群内吃瓜 / 在招公司一览（含群友自建公司） |
| 🛠️ **管理** | `推送` / `推送状态` | 切换本群每日早报推送开关 |
| 🛠️ **管理** | `创建备份` / `备份列表` / `恢复备份 <序号\|完整名称>` / `删除备份 <序号\|完整名称>` | 管理员在线创建、查看、回滚、删除 SQLite 快照。恢复/删除必须带参数且名称需完整（防误操作），恢复前会校验快照完整性与字段兼容性 |

---

## ⚙️ 核心配置项说明（`_conf_schema.json`，共 215 项，全部带 min/max）

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `use_image` | bool | `true` | 是否启用 Playwright HTML 图片卡片渲染（关闭则为纯文本） |
| `render_scale` | float | `2.0` | 截图渲染清晰度缩放倍率（推荐 2.0 超清） |
| `webui_enabled` | bool | `true` | 是否开启独立 WebUI 管理服务 |
| `webui_host` | string | `127.0.0.1` | WebUI 监听地址（默认仅本机；需局域网访问改 `0.0.0.0`。任何监听地址都必须先设 `webui_password`） |
| `webui_port` | int | `17817` | WebUI 访问端口 |
| `webui_password` | string | `""` | WebUI 访问密码。管理面板可删档/恢复备份/改配置，强烈建议设置。留空时 WebUI 首次启动会自动生成 18 位临时密码（明文一次性打印到启动日志），登录后必须立即改密。 |
| `webui_jwt_secret`| string | `""` | JWT(HS256) 签名密钥，首次启动自动生成并持久化；勿手动修改 |
| `start_cash` | int | `800` | 新玩家初始备用金（元） |
| `backup_max_keep` | int | `20` | 备份快照保留数量上限（超出自动删除最旧的） |
| `social_insurance_rate`| float | `0.10` | 打卡扣除的五险一金比例 |
| `stock_fee_rate` | float | `0.005` | 股票买卖交易手续费率 |
| `fund_fee_rate` | float | `0.005` | 基金申购/赎回手续费率 |
| `house_price` | int | `100000` | 自购小窝房产全款价格 |
| `push_hour` | int | `8` | 每日自动推送早报与股市行情的时间（0~23 点） |
| `create_company_cost` | float | `30000.0` | 创业注册验资资金门槛（元） |
| `create_company_min_value` | float | `50000.0` | 创业所需最低职场身价门槛（元） |
| `scratch_lottery_cost` | float | `20.0` | 职场刮刮乐单张彩票花费（元） |
| `redpacket_min_amount` | float | `10.0` | 群内塞红包允许的最低起始总金额（元） |
| `weekly_archive_enabled`| bool | `true` | 每周自动归档排行榜快照 |
| `cooldown_exempt_users` | list | `[]` | 豁免冷却时间的特权用户 ID 列表 |

> 余下约 175 项覆盖：冷却时长（求职/跳槽/调休/团建/帮领导/峰会…）、成功率（摸鱼被抓/学技能/对线/卷王/借钱有去无回/考证/年会/体检…）、金额（学费/健身/饭价/社交请奶茶/年终奖系数…）、上下限（年薪假/副业等级/医院阈值/对线身价负惩罚/股票涨跌停…）。所有数值在 WebUI「插件配置」页可即时在线修改。
>
> 三张数值表（饭价/通勤方式/证书/刮刮乐）在 `resources/data/` 下而非配置里：与 `companies.json` / `houses.json` 一致，调它们就是改文件并热加载。

---

## 🌐 现代化 WebUI 管理面板

在浏览器打开 `http://127.0.0.1:17817`（默认仅本机可访问；手机访问请将 `webui_host` 改为 `0.0.0.0` 并设置密码，面板自动适配移动端布局）：

- 📡 **实时动态流**：群内打卡、加薪、跳槽、对线实时事件播报，可一键清空；
- 🏆 **全群排行榜**：按群随时切换查看富豪、卷王、身价、职级榜；
- 🔍 **玩家全景档案**：可视化查询玩家属性、状态条与核心数值；
- ⚙️ **玩家管理**：档案数值在线编辑与玩家删除（高危操作带确认弹窗）；
- 📈 **股市管理中心**：100 支股票行情展示、在线快速调价、全局波动触发与重置；
- 🗂️ **公司与文案编辑器**：116 家公司参数全字段表格编辑、9 大文本库在线配置热重载；
- 🧩 **在线参数配置**：215 项游戏规则与数值在线修改（数值带 min/max 钳制，列表项可热更新 JSON），即存即生效。配置项在面板里显示为中文标签；
- 🛡️ **Argon2id 密码存储 + JWT 服务端会话**：密码用 Argon2id（m=64MiB, t=3, p=4，OWASP 推荐）哈希存盘，配置表单以明文文本框展示但存盘恒为哈希；登录令牌走 JWT(HS256)，服务端维护 webui_sessions 会话表（jti 绑定，12h TTL），可在「我的会话」面板单独撤销任意设备；改密立即下线全部会话。
- 🗄️ **数据备份与回滚**：一键在线创建数据库安全快照，随时安全恢复。

---

## 🗂️ 自定义扩充文案与数据（所有 JSON 详解）

插件的所有事件文案与数值数据均位于 `resources/` 目录下，分为 **`texts/`（剧情文案库）** 与 **`data/`（数值规则库）**。可直接编辑 JSON 文件，或在 WebUI「公司与文案」页在线编辑（保存即时热更新）：

### 1. 📖 剧情文案库（`resources/texts/`）

| 文件名 | 主要字段（真实键名） |
|---|---|
| **`work.json`** | `checkin_events`（打卡随机事件：text/cash/health/mind/exp）、`slack_ok` / `slack_caught`（摸鱼）、`overtime_events`（加班）、`hospital_texts`（住院）、`layoff_texts` / `layoff_safe`（裁员）、`leave_texts`（请假）、`promote_ok` / `promote_fail`（晋升）、`resign_texts`（辞职）、`job_offer` / `job_fail`（应聘）、`hop_ok` / `hop_fail`（跳槽）、`weeklyreport_ok` / `weeklyreport_fail`（周报）、`commute_late`（迟到） |
| **`life.json`** | `takeout` / `canteen` / `feast`（吃饭三档）、`gym`（健身）、`stall_income` / `stall_fail`（摆摊）、`house_move`（搬家）、`rent_paid` / `rent_failed`（房租）、`nap_ok` / `nap_caught`（午休）、`shopping`（购物）、`teambuild`（团建）、`house_owned_texts`（已购房） |
| **`company.json`** | `jinxiu_ok` / `jinxiu_fail`（进修成败）、`negotiation_ok` / `negotiation_fail`（加薪谈判） |
| **`duel.json`** | `actions`（对线回合招式，支持 `{a}`/`{b}` 昵称占位符）、`win_lines` / `lose_lines`（胜负台词） |
| **`news.json`** | `headlines`（每日职场早报头条，按日期种子全天固定） |
| **`extra.json`** | `yearbonus_ok` / `yearbonus_bad`（年终奖）、`skill_learn_ok` / `skill_learn_fail`（学技能）、`social_ok` / `social_fail`（职场社交）、`gossip_texts`（职场八卦，支持 `{a}`/`{b}`）、`side_hustle_up`（副业升级）、`annual_leave`（年假） |
| **`extra2.json`** | `party_prizes`（年会奖品：rank/text/amount）、`career_advice`（职场建议）、`lend_ok` / `lend_fail`（借钱）、`ot_meal`（加班餐）、`checkup_ok` / `checkup_bad`（体检） |
| **`extra3.json`** | `meeting`（开会）、`bring_food`（帮带饭）、`reply_msg`（回消息）、`meeting_room`（抢会议室）、`eat_with`（和同事吃饭）、`boss_task_ok` / `boss_task_fail`（帮领导做事）、`summit`（峰会）、`pet_interact`（宠物互动）、`cert_ok` / `cert_fail`（考证）、`travel`（旅游：text/cost/mind/health） |
| **`help.json`** | `sections`（帮助菜单：icon/title/commands[{usage, desc}]） |

### 2. 📊 核心数值与配置库（`resources/data/`）

> 三张生活数值表（`meals.json` / `commute.json` / `certs.json`）与 `scratch.json` 抽奖表——
> WebUI 在「插件配置」页里有对应配置键可调（`shopping_budgets` / `eat_with_costs` 等），
> 也可以直接编辑 JSON 后保存，插件会在下一次读到时自动加载新副本。

| 文件名 | 主要字段（真实键名） |
|---|---|
| **`companies.json`** | 116 家企业：`id`、`name`、`tag`（行业）、`salary`（底薪）、`intensity`（强度）、`risk`（日裁员率）、`min_exp`（门槛）、`desc`、`perks`（福利）。WebUI 保存时自动按薪资升序重排 ID |
| **`positions.json`** | 12 级职级：`i`（0~11）、`title`、`mult`（薪资系数）、`need`（晋升经验）、`cost`（打点费） |
| **`shop.json`** | 便利店道具：`id`、`name`、`price`、`health`/`mind`（恢复）、`desc`；`type:"card"` 的道具带 `card_key`（shield/poop/coffee_pack/radar）入背包 |
| **`houses.json`** | 12 档住房：`i`（0~11，7 为自购小窝）、`name`、`rent`（日租金）、`recover`（每日恢复）、`deposit`（押金）、`desc` |
| **`stocks.json`** | 100 支股票：`code`、`name`、`sector`、`price`（基准价） |
| **`opponents.json`** | 卷王大赛对手池：`name`、`score`（战力）、`effect`（特征描述） |
| **`rankevents.json`** | 卷王挑战事件 + 段位表：`events[25]`（`name`/`effect`/`desc`）+ `opponents[12]` + `tiers[5]` + `tier_scores[5]` |
| **`workstations.json`** | 5 档工位：`lv`（0~4）、`name`、`cost`、`bonus`、`desc` |
| **`pets.json`** | 宠物（猫/狗）：`type`、`cost`、`mind_bonus`、`desc` |
| **`meals.json`** | 吃饭三档（外卖 / 食堂 / 大餐）：`name`、`key`、`cost`、`health`、`mind` |
| **`commute.json`** | 4 种通勤方式：`name`、`cost`、`health`、`mind`、`late_rate`。配合配置项 `overtime_meal_start_hour`、`late_pay_penalty_rate` 等 |
| **`certs.json`** | 4 种证书（PMP / CPA / 法考 / CFA）：`name`、`cost`、`exp`。配合 `cert_pass_rate` / `cert_value_bonus_rate` 调难度与回报 |
| **`scratch.json`** | 下班刮刮乐：`prizes[4]`（`name`/`multiplier`/`prob`/`color`，金额按「相对售价的倍数」存储）+ `lose`（未中奖文案）。配合配置项 `scratch_lottery_cost` / `scratch_rtp` 调售价与返奖率（变更售价不会破坏返奖率） |

---

欢迎提交 PR 补充或丰富插件的创意文案与企业！

---

## 📄 许可证

本项目采用 [GNU General Public License v3.0](LICENSE) 开源。

---

<div align="center">

如果觉得这个插件对你带来快乐，欢迎 Star 或者 PR 一下哈哈

</div>
