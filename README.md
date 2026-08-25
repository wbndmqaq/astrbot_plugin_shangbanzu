# 🏢 打工人 · 上班族物语

AstrBot 大型群聊职场生存模拟插件。以「上班族的现实」为主题：入职公司、打卡领薪
（通勤+五险一金+迟到判定）、摸鱼被抓、加班住院攒调休券、写周报评绩效、和领导谈加薪、
被裁员拿补偿、挤地铁通勤、交房租、吃外卖、买基金绿到发光、买股票追涨杀跌，
团建购物两不误，攒够公积金全款买房安家；玩家之间方案评审式对线撕逼，
亲自出战卷王大赛。

- 💾 用户数据：**SQLite**（标准库，WAL 模式）
- 📝 游戏文本：**JSON**（`resources/texts/`，可自行扩充）
- 🖼️ 全部输出：**独立 Playwright 渲染器**（Chromium 截图，失败自动回退纯文本）
- 🌐 独立端口 **WebUI** 面板（**aiohttp** 实现，支持密码登录）
- 🔌 适配 **OneBot v11** 与 **QQ 官方机器人**（仅用文本/图片/@ 组件）

## 🚀 安装方式：WebUI 插件市场

AstrBot WebUI → 插件管理 → 搜索 `astrbot_plugin_neteasemusic` → 安装。

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

环境未就绪时，日志会输出一次上述完整教程，所有指令自动回退纯文本展示；安装完成后重载即可正常出图。

## 🧩 插件架构（模块化）

```
astrbot_plugin_shangbanzu/
├── main.py                  # 主入口：生命周期 + 输出渲染 + 路由安装
├── metadata.yaml
├── _conf_schema.json        # 40 项可视化配置
├── handlers/                # 【指令路由层】声明式路由表
│   ├── base.py              #   Route + install() 动态安装器
│   ├── system_cmds.py       #   帮助 / 早报 / 四大排行
│   ├── career_cmds.py       #   职业：找工作→打卡→晋升→跳槽→辞职
│   ├── company_cmds.py      #   加薪谈判 / 进修 / 同事录
│   ├── battle_cmds.py       #   对线 / 卷王大赛（亲自出战）
│   ├── life_cmds.py         #   吃饭/健身/租房/通勤/团建/购物/买房/工资条
│   ├── finance_cmds.py      #   银行/利息/转账/基金
│   ├── stock_cmds.py        #   股市/买入/卖出/持仓
│   ├── extra_cmds.py        #   年终奖/技能/社交/副业升级/年假/八卦
│   ├── extra2_cmds.py       #   年会抽奖/借钱/建议/工位升级/加班餐/体检
│   └── review_cmds.py       #   年终考评
├── core/                    # 【业务服务层】
│   ├── db.py                #   SQLite（39列+8表）
│   ├── context.py           #   GameCtx（群昵称拉取+缓存）
│   ├── result.py            #   R() 统一返回
│   ├── renderer.py          #   Playwright 渲染器
│   ├── logic.py             #   纯函数
│   ├── gamedata.py          #   JSON 数据加载
│   ├── backup.py            #   备份管理器
│   ├── stocks.py            #   股票市场
│   ├── career.py            #   职业服务
│   ├── life.py              #   生活服务
│   ├── social.py            #   社交服务
│   ├── finance.py           #   金融服务
│   └── extra.py             #   扩展玩法（年终奖/技能/社交/八卦等）
├── webui/
│   ├── server.py            #   aiohttp 独立端口 + 密码认证 + 管理API
│   ├── index.html           #   面板入口页
│   ├── style.css            #   WebUI 样式文件
│   └── app.js               #   WebUI 前端逻辑
└── resources/
    ├── texts/*.json         #   游戏文案（1270条）
    ├── data/*.json          #   公司/职级/房产/商品/对手/事件/股票/宠物
    └── templates/*.html     #   Jinja2 渲染模板（8个）
```

新增指令三步：core 写服务 → handlers 域文件写 run → 追加一条 Route。

## 🎮 指令一览（前缀 `#`）

| 分类 | 指令 | 说明 |
|---|---|---|
| 职业 | `找工作 [公司名]` / `我的公司` | 入职 / 雇主详情 |
| 职业 | `上班` / `打卡` | 每日打卡：通勤+五险一金+迟到+随机事件+早报 |
| 职业 | `摸鱼` / `加班` / `请假` / `请调休` | 日常操作 |
| 职业 | `写周报` / `晋升` / `跳槽` / `辞职` | 成长与变动 |
| 职业 | `加薪` / `谈薪` / `进修` / `我的简历` | 谈判/学习/档案 |
| 成长 | `学技能 [名称]` / `我的技能` / `工位升级` | 5种技能/工位 |
| 成长 | `副业升级` / `年会抽奖` / `年终考评` | 副业/年会/考评 |
| 成长 | `请年假` / `年度体检` / `加班餐` | 福利 |
| 对抗 | `对线 @群友` / `卷王大赛` / `参加卷王大赛` | 撕逼/冲段 |
| 生活 | `吃饭` / `午休` / `健身` / `团建` / `通勤` | 日常恢复 |
| 生活 | `租房` / `买房` / `摆摊` / `购物` | 住房与消费 |
| 生活 | `商店` / `购买` / `工资条` | 商品/流水 |
| 办公室 | `开会` / `带饭 @群友` / `回消息` / `抢会议室` | 打工日常 |
| 办公室 | `和同事吃饭 @群友` / `帮领导做事` / `行业峰会` | 职场事件 |
| 办公室 | `考证书 [名称]` / `旅游` / `养猫` / `遛狗` | 自我提升/宠物 |
| 社交 | `职场社交 @群友` / `借钱 @群友` / `职场八卦` | 人脉/周转/吃瓜 |
| 行情 | `人才市场` / `同事录` / `跳槽市场` | 同事状态/在招公司 |
| 理财 | `存款` / `取款` / `领取利息` / `升级信用` / `转账 @群友` | 银行 |
| 理财 | `买基金 N` / `卖出基金 [%]` | 基金 |
| 理财 | `股市` / `持仓` / `买股票 代码 N` / `卖股票 代码` | 股票 |
| 排行 | `富豪榜` / `卷王榜` / `身价榜` / `职级榜` | 四大榜单 |
| 信息 | `职场早报` / `职场建议` / `职场八卦` | 资讯 |
| 管理 | `推送` / `推送状态` / `备份` 系列 | 系统管理 |

## ⚙️ 常用配置

| 配置项 | 默认 | 说明 |
|---|---|---|
| `use_image` / `render_scale` | true / 2.0 | Playwright 渲染开关与清晰度 |
| `webui_enabled` / `webui_port` | true / 17817 | 独立 WebUI |
| `webui_password` | "" | WebUI 密码（空=免密） |
| `social_insurance_rate` | 0.10 | 五险一金比例 |
| `house_price` | 100000 | 自购小窝总价 |
| `layoff_scale` | 1.0 | 裁员概率倍率 |

## 🌐 WebUI

访问 `http://<host>:17817`：

- 📡 实时动态流（10秒自动刷新）
- 🏆 四大榜单按群查看
- 🔍 玩家档案查询
- 📈 股市管理
- 🗄️ 备份管理
- ⚙️ 玩家管理
- 🏢 公司管理

## 🙏 扩充文案

编辑 `resources/texts/*.json` 后热重载即可生效。
