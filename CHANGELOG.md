## 1.0.1 (2026-08-31)

全量代码审计后的修复版本（四轮审计合并），共修复 49 个问题（3 Critical / 9 High / 22 Medium / 15 Low）+ 18 项硬编码配置化。

### 🐛 Bug 修复

#### 第四轮审计新增

- **`webui/server.py` aiohttp NameError**（Critical）：`_body()` 中 `ContentTypeError` 未通过 `web.` 前缀访问，非 JSON 请求触发 `NameError` → 500。改为 `web.ContentTypeError`。
- **`db.py` DELTA_FLOAT_COLUMNS 缺失三列**（Critical）：`deposit`/`fund`/`fund_savings` 未纳入增量写回的 delta 钳制范围，并发写入可能产生负值。三列加入 `DELTA_FLOAT_COLUMNS`。
- **`life.py` shopping 无余额校验**（High）：购物不检查现金是否足够，`max(0.0, cash - budget)` 钳制后零余额玩家可免费购物。增加前置余额校验，不足则拒绝下单。
- **`stock_cmds.py` sell ratio=0 静默清仓**（High）：`parse_int("0", default=100, lo=1)` 中 0 < lo=1 触发 default=100，用户输入 0% 时实际卖出 100%。改为 `default=None` + 独立 100 兜底。
- **`webui/server.py` secure cookie 在 LAN HTTP 下导致登录失效**（High）：`secure=self.host not in (...)` 对 LAN IP 设 `secure=True`，浏览器不回传 cookie。改为按 `request.scheme` / `X-Forwarded-Proto` 判断 HTTPS。
- **`webui/server.py` save_config 未包 try/except**（High）：配置保存失败时未捕获异常，导致 500 且无错误反馈。增加 `try/except` + 500 JSON 响应。
- **`career.py` checkin `logic.pick` 返回空串导致 `.get()` 崩溃**（Medium）：`checkin_events` 空列表时 `pick()` 返回 `""`，后续 `ev.get()` 崩溃。增加 `isinstance(ev, dict)` 守卫 + 兜底事件。
- **`career.py` overtime `logic.pick` 返回空串导致 `.get()` 崩溃**（Medium）：同上，`overtime_events` 空列表时崩溃。增加守卫。
- **`life.py` teambuild `logic.pick` 返回空串导致 `.get()` 崩溃**（Medium）：同上，`teambuild` 空列表时崩溃。增加守卫。
- **`social.py` rank_events `logic.pick` 返回空串导致 `["effect"]` 崩溃**（Medium）：排位赛事件池空时 `ev["effect"]` 崩溃。增加守卫 + 兜底事件。
- **`lottery.py` 奖池展示硬编码 60%/25%/15%**（Medium）：奖池面板写死比例，不随 `lottery_jackpot_pct` 等配置变化。改为从 `_tiers_from_cfg(cfg)` 动态读取。
- **`career.py` 通勤费不足时效果仍生效**（Medium）：余额不够付通勤费时只跳过扣费，但 `health`/`mind` 效果照加。改为余额不足时按步行处理（不扣费也不加效果）。
- **`stock_cmds.py` 手续费显示用重算值**（Medium）：买入面板手续费用 `fee_rate * r['amount']` 重算而非 `r['fee']`，与实际扣费可能不一致。改为读 `r['fee']`。
- **`webui/server.py` `_coerce` list 强制 str 破坏数值列表**（Medium）：`shopping_budgets`/`shopping_weights` 等数值列表经 WebUI 保存后被强制转成字符串。改为保留 `int`/`float` 原始类型。
- **`main.py` `terminate()` 未关闭 DB**（Medium）：卸载时不执行 WAL checkpoint，`-wal` 文件可能残留。新增 `db.close()` 方法 + `terminate()` 调用。
- **README 配置项数与 API 数过时**（Low）：配置项 215→237，WebUI 路由 26→33。
- **CHANGELOG 配置项类型标注错误**（Low）：`teambuild_cooldown_days`/`shopping_cooldown_hours` 标注 int 应为 float。
- **`metadata.yaml` author 与 repo 所有者不一致**（Low）：author `wbndm` 与 repo 所有者 `wbndmqaq` 不一致，统一为 `wbndmqaq`。

#### 前三轮审计修复

- **`stocks.py` 买入手续费双重收取**（Critical）：买入股票时先从现金扣除 `amount + fee`，再把 `shares = (amount - fee) / price`，导致手续费被扣两次（一次少买份额、一次多扣现金）。改为 fee-on-top 模式：现金扣 `amount + fee`，份额按全额本金 `shares = amount / price` 计算。
- **`career.py` take_leave 硬编码显示值**（High）：请假面板和文本中 `+15`/`+8` 写死，不随 `leave_mind_gain`/`leave_health_gain` 配置变化。改为从配置读取变量，面板与文本统一引用。
- **`career.py` my_company 工作强度硬编码**（High）：公司详情页 `comp['intensity'] * 0.4` 硬编码，与 `checkin` 使用的 `work_intensity_health_factor` 配置不一致。改为读取同一配置项。
- **`finance.py` 基金结算重摇利用**（High）：`bank_info`/`fund_buy`/`fund_sell` 三个函数在结算后不立即持久化，若后续输入校验失败则 stale `fund_day` 未更新，玩家可反复发非法指令只保留正收益结算、丢弃负收益。改为结算后立即 `save_player`，再执行后续逻辑。
- **`gamedata.py` 8 个函数浅拷贝导致缓存污染**（High）：`companies`/`company_by_id`/`positions`/`houses`/`shop_items`/`opponents`/`workstations`/`rank_events` 返回 `list()` 浅拷贝，调用方修改 dict 会回写缓存。改为 `[dict(x) for x in ...]` 深拷贝。
- **`gamedata.py` match_opponent 空池崩溃**（High）：对手池为空时 `random.choice([])` 触发 `IndexError`。改为返回兜底 dict。
- **`career.py` take_comp_leave 硬编码显示值**（Medium）：调休面板和逻辑中 `+15`/`+8` 写死，与 `take_leave` 相同问题。改为从配置读取。
- **`career.py` job_hop/promote 两次 pick 不一致**（Medium）：跳槽/晋升失败时面板 lines 和 text 各调一次 `logic.pick()`，随机结果可能不同。改为单次取值复用。
- **`career.py` company_dividend 冗余 DB 查询**（Medium）：`load_player` 加载的 `p` 从未使用，后续又重新 `get_player`。删除多余调用。
- **`logic.py` clamp 不处理 None 输入**（Medium）：`clamp(None)` 崩溃。增加 `if v is None: return lo` 守卫 + `float(v)` 转换。
- **`logic.py` interest_of `now=0` 被视为 falsy**（Medium）：`now or now_ts()` 在 `now=0` 时错误回退到当前时间。改为 `now_ts() if now is None else now`。
- **`db.py` last_review_payload 53 周年回退错误**（Medium）：53 周年份时硬编码回退到 week 52 而非 53。改为 `datetime.date(prev_year, 12, 31).isocalendar()` 动态计算。
- **`social.py` 决斗基础胜率硬编码**（Medium）：`0.5` 硬编码。新增 `duel_base_win_rate` 配置项。
- **`renderer.py` close() 非幂等**（Medium）：重复调用 `close()` 时第二次仍尝试获取信号量并关闭已关闭的 browser。增加早退守卫。
- **`context.py` amount_after 子串误删**（Medium）：`str.replace(uid, " ")` 会把 uid 子串从更长数字中误删（如 uid "123" 从 "123456" 中删出 "456"）。改为 `re.sub` 配合数字边界断言 `(?<!\d)...(?!\d)`。
- **`life2.py` logic.pick 返回空串导致 .get() 崩溃**（Medium）：`meeting`/`pet_interact` 中 `logic.pick()` 在空列表时返回 `""`，后续 `ev.get()` 崩溃。增加 `isinstance(ev, dict)` 守卫。
- **`life2.py` travel 空目的地列表崩溃**（Medium）：`random.choice(dests)` 在空列表时崩溃。增加前置守卫。
- **`backup.py` sqlite3.connect 失败时资源泄露**（Medium）：两个 `sqlite3.connect()` 在 try 块外，若第二个失败则第一个连接泄露。改为 None 守卫 + try/finally。
- **`career.py` 医疗费硬编码参数**（Low）：住院费用上限 3000、下限 200、比例 0.25 均硬编码。新增 `hospital_cost_max`/`hospital_cost_min`/`hospital_cost_rate` 配置项。
- **`career.py` 裁员安全事件概率硬编码**（Low）：打卡时 `0.05` 硬编码。新增 `layoff_safe_event_rate` 配置项。
- **`extra.py` 成就列表排序不确定**（Low）：`list(set)` 顺序不确定，同一成就集可能生成不同 JSON。改为 `sorted()` 保证确定性。
- **`extra.py` year_bonus 出勤上限硬编码**（Low）：`min(streak, 20)` 硬编码 20，不随 `attend_streak_bonus_days` 配置变化。改为从配置读取。
- **`extra2.py` party_lottery 空奖品列表崩溃**（Low）：奖品池为空时 `random.choice([])` 触发 `IndexError`。增加前置守卫返回友好提示。
- **`market_cmds.py` get_player 缺少 nickname**（Low）：跳槽市场查询未传 `nickname`，新建玩家昵称为空。补传 `event.get_sender_name()`。
- **`db.py` claim_redpacket json.loads 无异常守卫**（Low）：恶意或畸形 JSON 触发 `JSONDecodeError` 崩溃。增加 `try/except`。
- **`db.py` create_redpacket 死代码**（Low）：非原子版本无调用者，删除。
- **`extra2.py` 死参数 + 缺少 .get() 守卫**（Low）：`career_advice(ctx_db=None)` 死参数删除；年会奖品 `prize['rank']`/`prize['text']` 改为 `.get()`。
- **`web_auth.py` verify_password 异常覆盖不全**（Low）：仅捕获 `VerifyMismatchError`/`InvalidHashError`，遗漏 `Argon2Error` 基类。补充捕获。
- **`webui/server.py` _body 缺少 ContentTypeError**（Low）：`aiohttp.ContentTypeError` 未捕获，畸形 Content-Type 请求触发 500。补充捕获。
- **`gamedata.py` 死别名 opponent_pool**（Low）：`opponent_pool` 为 `opponents` 的旧别名，无调用者，删除。
- **`extra.py` gossip_texts 空列表崩溃**（Low）：`random.choice(gd.t("extra", "gossip_texts"))` 在数据缺失时崩溃。改用 `logic.pick()` + 兜底文案。

### ⚙️ 新增配置项

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `hospital_cost_max` | float | 3000.0 | 住院医疗费上限 |
| `hospital_cost_min` | float | 200.0 | 住院医疗费下限 |
| `hospital_cost_rate` | float | 0.25 | 住院医疗费比例（按现金计算） |
| `layoff_safe_event_rate` | float | 0.05 | 打卡时裁员安全事件触发概率 |
| `lottery_jackpot_pct` | float | 0.6 | 一等奖奖金占奖池比例 |
| `lottery_second_pct` | float | 0.25 | 二等奖奖金占奖池比例 |
| `lottery_third_pct` | float | 0.15 | 三等奖奖金占奖池比例 |
| `review_score_rand_min` | float | 0.8 | 周报评分随机波动下限 |
| `review_score_rand_range` | float | 0.4 | 周报评分随机波动范围 |
| `report_s_bonus_multi` | float | 2.0 | 周报S级奖金乘数 |
| `shopping_refund_rate` | float | 0.15 | 购物退货折损比例 |
| `shopping_shipping_rate` | float | 0.1 | 购物运费比例 |
| `shopping_deal_rate` | float | 0.30 | 薅羊毛成功率 |
| `shopping_refund_mind` | int | 5 | 退货精神惩罚 |
| `coffee_pack_health_bonus` | float | 30.0 | 咖啡道具健康恢复值 |
| `coffee_pack_mind_bonus` | float | 30.0 | 咖啡道具精神恢复值 |
| `teambuild_cooldown_days` | float | 7.0 | 团建冷却天数 |
| `shopping_cooldown_hours` | float | 6.0 | 购物冷却小时数 |
| `duel_base_win_rate` | float | 0.5 | 对线基础胜率 |

---

## 1.0.0 (2026-08-31)

🏢 **打工人·上班族物语** —— AstrBot 大型群聊职场生存模拟游戏（首个公开版本）。

### 🌟 这是一款什么样的游戏？

- 以「上班族的现实」为主题：入职公司、每日打卡领薪（通勤+五险一金+迟到判定）、
  摸鱼被抓、加班住院攒调休券、写周报评绩效、和领导谈加薪、被裁员拿补偿、
  挤地铁通勤、交房租、吃外卖、买基金绿到发光、买股票追涨杀跌、团建购物两不误，
  攒够公积金全款买房安家。
- 玩家之间方案评审式对线撕逼、亲自出战卷王大赛冲击「传奇卷王」段位。

### 🎮 指令速查（93 条）

| 模块 | 指令 | 说明 |
|---|---|---|
| 💼 职业 | `找工作 [公司名]` / `我的公司` | 投简历入职指定公司（自建公司也可投）/ 查看雇主详情 |
| 💼 职业 | `上班` | 每日打卡：扣通勤费 + 五险一金 + 绩效结算 |
| 💼 职业 | `摸鱼` / `加班` | 摸鱼加精神 / 加班拿钱（概率得调休券） |
| 💼 职业 | `请假` / `调休` / `写周报` / `晋升` / `加薪谈判` / `跳槽` / `辞职` | 周期玩法链 |
| 💼 职业 | `创建公司 <名称>` | 群内自建公司，员工打卡自动给老板分红 |
| 🌱 成长 | `进修` / `团建` / `购物` / `摆摊` / `技能 <名>` | 提升身价 / 社交经验 / 外快 |
| 🤝 对抗 | `对线 @群友` / `参加卷王大赛` | 对线赢钱涨身价 / 段位爬升 |
| 🏠 生活 | `吃饭 [外卖\|食堂\|大餐]` / `健身` / `租房` / `通勤 <方式>` / `午休` / `买房` / `工资条` | 日常起居 |
| 🏠 生活 | `开会` / `带饭 @群友` / `抢会议室` / `吃饭 @群友` / `峰会` / `互动 <宠物>` / `考证 PMP\|CPA\|法考\|CFA` / `旅游` | 办公室日常 |
| 💰 理财 | `存款 N` / `取款 N` / `领取利息` / `升级信用` / `转账 N @群友` / `买基金 N` / `卖出基金 50%` / `发红包 N <个数>` / `抢红包` | 钱生钱 |
| 📈 投资 | `股市` / `买股票 <代码> <金额>` / `卖出 [代码] [比例%]` / `持仓` | 100 支股票，每日自动波动 |
| 🎰 彩券 | `买彩票 3` / `买彩票 3 7 12 5` / `我的彩票` / `奖池` / `开奖结果` | 游戏化双色球·累积奖池 |
| 🛠 管理 | `创建备份` / `备份列表` / `恢复备份 <序号\|完整名称>` / `删除备份 <序号\|完整名称>` | 管理员在线创建/查看/回滚/删除 SQLite 快照 |
| 🏆 排行 | `富豪榜` / `卷王榜` / `身价榜` / `职级榜` / `职场建议` / `职场八卦` / `跳槽市场` | 群内四大维度榜单 + 资讯 |
| 📰 资讯 | `职场早报` / `年终考评` / `发年终奖` / `我的简历` / `我的技能` / `成就` / `佩戴称号` | 进度与反馈 |
| ⚙ 系统 | `帮助` / `推送` / `推送状态` | 群每日早报推送开关 + 帮助中心 |

> 完整说明、配置项与 WebUI 用法见 [README](README.md)。

### ✨ 首次发版包含的全部玩法

- **职业链**：求职 → 入职 → 每日打卡（绩效 + 通勤 + 迟到判定 + 强度换算）→ 摸鱼 → 请假 →
  周报 → 晋升 → 加薪谈判 → 跳槽 → 辞职 → 自建公司 → 派员打卡收分红
- **对抗线**：方案评审式「对线」（身价换算胜率 + 段位榜 + 加注对赌）+ 亲战卷王大赛（段位 / 阶位 / 出场费）
- **生活链**：三餐档位、健身、租房 / 通勤（4 种方式各有利弊）、午休、团建、购物、摆摊副业、
  公积金全款买房、5 张办公室日常卡（开会 / 带饭 / 抢会议室 / 与同事吃饭 / 帮领导做事）、
  行业峰会（14 天 CD）、年度体检、宠物互动、4 种证书考证（PMP / CPA / 法考 / CFA）、旅游
- **理财链**：存款利息（每小时结算 + 信用升级）、原子转账 / 借钱（含坏账概率）、
  基金（每日结算 + 漂移 / 波动可配）、100 支股票（涨跌停 + 持仓只数上限）、拼手气红包
- **彩券**：游戏化双色球（3 红 + 蓝，1/4480 头奖，累积奖池滚存）+ 下班刮刮乐（带冷却与返奖率）
- **人脉链**：职场社交（送奶茶 / 随机获得 0.5~2x 收益 + 对方入账原子更新）、
  成就称号 / 年度考评（A/B/C/D 四档 + 调薪 + 年终奖双轨）
- **管理端**：独立端口 WebUI（动态 / 排行 / 玩家搜索 / 股票 / 备份 / 插件配置 / 公司文案编辑，
  自定义公司、热重载、原子扣款守护）