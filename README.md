# 🏢 打工人 · 上班族物语

AstrBot 大型群聊职场生存模拟插件。以「上班族的现实」为主题：入职公司、每日打卡领薪
（通勤+五险一金+迟到判定）、摸鱼被抓、加班猝死住院攒调休券、写周报评绩效、和领导谈加薪、
被裁员拿补偿、挤地铁通勤、交房租、吃外卖、买基金绿到发光、买股票追涨杀跌，
团建购物两不误，攒够公积金全款买房安家；玩家之间方案评审式对线撕逼，
亲自出战卷王大赛冲击「打工皇帝」段位。

- 💾 用户数据：**SQLite**（标准库，WAL 模式 + 线程安全写锁）
- 📝 游戏文本：**JSON**（`resources/texts/`，包含 1280+ 条文案，可自行扩充）
- 🖼️ 全部输出：**独立 Playwright 渲染器**（Chromium 截图，失败自动回退纯文本）
- 🌐 独立端口 **WebUI** 面板（**aiohttp** 实现，支持密码登录与全量管理）
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
├── _conf_schema.json        # 40 项可视化配置 Schema
├── handlers/                # 【指令路由层】声明式路由表（共 78 条指令）
│   ├── base.py              #   Route + install() 动态安装器
│   ├── system_cmds.py       #   帮助 / 切换渲染 / 早报 / 四大排行
│   ├── career_cmds.py       #   职业：找工作→打卡→摸鱼→加班→晋升→跳槽→辞职
│   ├── company_cmds.py      #   加薪谈判 / 进修 / 同事录
│   ├── battle_cmds.py       #   对线 / 卷王大赛（亲自出战）
│   ├── life_cmds.py         #   吃饭/健身/租房/通勤/团建/购物/买房/工资条
│   ├── life2_cmds.py        #   办公室日常：开会/带饭/抢会议室/峰会/领养宠物
│   ├── finance_cmds.py      #   银行/利息/转账/基金买卖
│   ├── stock_cmds.py        #   股市行情/持仓/买入/卖出
│   ├── extra_cmds.py        #   年终奖/技能/社交/副业升级/年假/八卦
│   ├── extra2_cmds.py       #   年会抽奖/借钱/建议/工位升级/加班餐/体检
│   ├── market_cmds.py       #   跳槽市场（在招公司一览）
│   ├── review_cmds.py       #   年终考评 / 年终总结
│   ├── push_cmds.py         #   每日群推送开关与状态
│   └── backup_cmds.py       #   SQLite 在线数据备份系列（管理员）
├── core/                    # 【业务服务层】
│   ├── db.py                #   SQLite 核心数据（47列+8表，写锁安全）
│   ├── context.py           #   GameCtx（群昵称拉取+LRU缓存）
│   ├── result.py            #   R() 统一返回结构
│   ├── renderer.py          #   Playwright 渲染器（自动重试与内存释放）
│   ├── logic.py             #   业务通用纯函数
│   ├── gamedata.py          #   JSON 静态数据加载（带缓存与容错）
│   ├── backup.py            #   在线快照备份管理器
│   ├── stocks.py            #   100 支股票撮合与波动引擎
│   ├── career.py            #   职业核心服务
│   ├── life.py              #   生活消费服务
│   ├── life2.py             #   日常扩展服务
│   ├── social.py            #   社交互动与对战服务
│   ├── finance.py           #   金融理财服务
│   └── extra.py / extra2.py #   年终奖/技能/年会/体检/工位等扩展
├── webui/
│   ├── server.py            #   aiohttp 独立端口 + 密码认证 + 35 个管理 API
│   ├── index.html           #   响应式管理面板页面
│   ├── style.css            #   现代主题样式文件
│   └── app.js               #   前端交互与数据流控制
└── resources/
    ├── texts/*.json         #   游戏文案库（1280+ 条）
    ├── data/*.json          #   公司(116)/职级(12)/房产(12)/商品(25)/股票(100)/宠物(2)
    └── templates/*.html     #   Jinja2 渲染模板（8套全状态防爆模板）
```

---

## 📮 用户群

QQ 群（插件讨论）：[点击加入](https://qm.qq.com/q/8sOZdZTnaw)

---

## 🎮 完整指令一览

> 指令支持直接发送或带 `#` 前缀触发（例如 `打卡` 或 `#打卡`）。

| 分类 | 指令示例 | 说明 |
|---|---|---|
| ℹ️ **系统** | `上班族帮助` / `上班族版本` / `上班族切换渲染` | 帮助菜单 / 查看版本 / 切换卡片与纯文本模式 |
| 💼 **职业** | `找工作 [公司名]` / `我的公司` | 投简历入职指定或推荐公司 / 查看雇主详情 |
| 💼 **职业** | `上班` / `打卡` | 每日打卡领薪（自动扣通勤、五险一金、房租、触发随机事件） |
| 💼 **职业** | `摸鱼` / `加班` | 摸鱼回蓝（小心被抓罚款）/ 加班赚钱涨经验（概率拿调休券） |
| 💼 **职业** | `请假` / `请调休` / `写周报` | 请假回血 / 消耗调休券带薪休假 / 评绩效 S/A/B 拿奖金 |
| 💼 **职业** | `加薪谈判` / `进修` / `晋升` | 和老板谈涨薪 / 技能进修提高身价 / 职级提升 |
| 💼 **职业** | `跳槽` / `辞职` / `我的简历` | 换公司涨薪 / 裸辞成为无业游民 / 查看个人全景档案 |
| 👑 **创业** | `创建公司 [名称]` / `公司分红` | 身价/职级达标后自建企业成为大老板，提取企业利润分红 |
| 🏠 **生活** | `吃饭 [外卖/食堂/大餐]` / `午休` / `健身` | 恢复健康与精神值 |
| 🏠 **生活** | `租房 [房型]` / `买房 [房型]` / `通勤 [交通方式]` | 搬家 / 全款购房安家 / 设定地铁/公交/骑车/打车 |
| 🏠 **生活** | `商店` / `购买 [道具]` / `我的背包` / `使用 [道具]` | 查看商品列表 / 购买功能道具卡 / 查看背包 / 使用道具 |
| 🏠 **生活** | `工资条` / `摆摊` / `副业升级` | 查看收支流水明细 / 开启下班副业 / 升级副业档次提高收益 |
| 🐱 **宠物** | `领养宠物 [猫/狗]` / `喂宠物` / `遛宠物` / `我的宠物` | 领养宠物陪伴，每日互动增加精神与健康 |
| ⚔️ **对抗** | `对线 @群友` / `参加卷王大赛` / `卷王争霸赛战绩` | 与群友方案撕逼 / 挑战全群各段位卷王 |
| 🤝 **社交** | `发红包 [金额] [个数]` / `抢红包` | 群内塞拼手气红包，全群开抢 |
| 🤝 **社交** | `我的成就` / `佩戴称号 [名称]` / `卸下称号` | 查看职场里程碑并佩戴专属头衔展示 |
| 🤝 **社交** | `刮刮乐` / `下班刮刮乐` | 购买职场刮刮乐（小赌怡情，最高赢取5000元） |
| 🤝 **社交** | `夸夸 @群友` / `阴阳怪气 @群友` / `带饭 @群友` | 办公室社交互动 / 帮同事带饭赚小费 |
| 🤝 **社交** | `请客 @群友 [外卖/食堂/大餐]` / `借钱 @群友 [金额]` | 请同事吃大餐 / 向群友借钱周转 |
| 🏢 **办公室** | `开会` / `回消息` / `抢会议室` / `帮领导做事` | 职场日常操作与应酬 |
| 🏢 **办公室** | `行业峰会` / `考证书 [证书名]` / `旅游` | 参与高端峰会 / 考取资格证提升身价 |
| 🎁 **福利** | `年会抽奖` / `工位升级` / `加班餐` / `年度体检` | 年底抽现金大奖 / 工位升星 / 免费夜宵 / 体检回血 |
| 🎁 **福利** | `请年假` / `年终考评` / `年终总结` | 消耗年假带薪休息 / 评定年终奖档位（S/A/B/C/D） |
| 🪙 **理财** | `存款 [金额]` / `取款 [金额]` / `领取利息` | 银行定期存款，每小时按复利计息 |
| 🪙 **理财** | `升级信用` / `转账 @群友 [金额]` | 提升存款上限 / 个人间安全转账 |
| 📊 **基金** | `买基金 [金额]` / `卖基金 [金额]` | 申购基金，净值每日波动，按比例赎回 |
| 📈 **股票** | `股市` / `行情` / `大盘` / `我的股票` / `持仓` | 查看 100 支股票行情排行 / 查看持仓盈亏 |
| 📈 **股票** | `买股票 [代码/名称] [金额]` / `卖股票 [代码/名称] [比例]` | 股票撮合交易与止盈止损 |
| 🏆 **排行** | `富豪榜` / `卷王榜` / `身价榜` / `职级榜` | 群内四大维度排行榜单 |
| 📰 **资讯** | `职场早报` / `今日事件` / `职场建议` / `职场八卦` / `猎头推荐` | 每日职场要闻、全群每日突发公共Buff与吃瓜资讯 |
| 🏪 **市场** | `人才市场` / `同事录` / `跳槽市场` | 查看同事履历 / 在招公司岗位与薪资要求 |
| 🛠️ **管理** | `推送 [开/关]` / `推送状态` | 每日定时向本群推送早报与股市行情 |
| 🛠️ **管理** | `上班族备份` / `上班族备份列表` / `上班族恢复 [ID]` | 管理员在线创建、查看、回滚 SQLite 快照 |

---

## ⚙️ 核心配置项说明（`_conf_schema.json`）

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `use_image` | bool | `true` | 是否启用 Playwright HTML 图片卡片渲染（关闭则为纯文本） |
| `render_scale` | float | `2.0` | 截图渲染清晰度缩放倍率（推荐 2.0 超清） |
| `webui_enabled` | bool | `true` | 是否开启独立 WebUI 管理服务 |
| `webui_host` | string | `0.0.0.0` | WebUI 监听地址 |
| `webui_port` | int | `17817` | WebUI 访问端口 |
| `webui_password` | string | `""` | WebUI 访问密码（留空为免密访问，支持 Cookie 会话鉴权） |
| `start_cash` | float | `800.0` | 新玩家初始入职备用金（元） |
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

---

## 🌐 现代化 WebUI 管理面板

在浏览器打开 `http://<服务器IP>:<配置端口>`（支持 PC 与手机自适应布局）：

- 📡 **实时动态流**：群内打卡、加薪、跳槽、对线、大额交易实时事件播报；
- 🏆 **全群排行榜**：按群随时切换查看富豪、卷王、身价、职级榜；
- 🔍 **玩家全景档案**：可视化查询玩家属性、状态条、持仓、薪资与经历；
- 📈 **股市管理中心**：100 支股票行情展示、在线快速调价、全局波动触发与重置；
- 🗂️ **公司与文本编辑器**：116 家公司参数全字段表格编辑、9 大文本库在线配置热重载；
- 🧩 **在线参数配置**：40 项游戏规则与数值在线修改，即存即生效；
- 🗄️ **数据备份与回滚**：一键在线创建数据库安全快照，随时安全恢复。

---

## 🗂️ 自定义扩充文案（欢迎PR文案）

所有事件文案均位于 `resources/texts/*.json`：
- `work.json`：打卡、摸鱼、加班、辞职、周报文案；
- `life.json`：吃饭、午休、健身、租房、购物文案；
- `duel.json`：对线撕逼与卷王对决台词；
- `news.json`：每日职场头条新闻；
- `company.json` / `extra.json` / `extra2.json` / `extra3.json`：扩展事件文案。

直接编辑对应 JSON 后在 WebUI 点击保存或重载插件即可生效。

也可以PR文案，供其他用户使用

---

## 📄 许可证

本项目采用 [GNU General Public License v3.0](LICENSE) 开源。

---

<div align="center">

如果觉得这个插件对你带来快乐，欢迎 Star 或者PR一下哈哈

</div>
