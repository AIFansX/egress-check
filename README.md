# 家宽VPS分流一键自查检测 Egress-Check

一条命令自查服务器 / 家宽的可见路由差异，快速对比访问 Meta、流媒体、金融、电商等平台时的首个公网跳、ASN 和目标延迟。

它适合用来验收“家宽 VPS / 原生家宽 / 不分流线路”这类服务：不用猜、不用问客服，直接把 100+ 个常见平台的出口线路、ASN 和延迟跑出来。

## 一键完成检测

复制下面这一行到 SSH 里运行：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) -I
```

运行后输入 `1-7` 选择检测模式：

```text
1) 默认完整检测      网络环境 + IPv4 + IPv6
2) 只检测 IPv4
3) 只检测 IPv6
4) 只检测指定分类    AI / Social / Streaming / Search / Developer / Cloud / Crypto / Gaming
5) 低并发低压力模式  根据CPU 自适应并发 + 减少探测包，更流畅
6) JSON 输出         适合 cron / 监控
7) 高并发日志模式    并发 10 + 关闭颜色
```

一键`完整分流`检测：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh)
```

快速`AI分流`查询：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) --only AI
```

快速`社交媒体分流`查询：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) --only Social
```

## 核心卖点

- **一键验收家宽线路**：复制命令到 SSH，按菜单选择即可检测。
- **直观发现分流线索**：哪些域名的可见首跳 ASN 与基准不同，一屏看清；隐藏路径明确标为无法判定。
- **覆盖真实使用场景**：AI、社交、流媒体、金融、电商、开发者平台、云服务、游戏等 100+ 域名。
- **同时看延迟质量**：不只判断有没有分流，还能看到 VPS 到目标域名的 mtr 平均延迟。
- **辅助排查网络问题**：账号或平台访问异常时，提供可见路由差异供进一步核查，不将路由结果直接等同于账号风控原因。

![Egress-Check 分流检测效果图](assets/egress-check-preview.png)

## 怎么看结果

- 绿色：可见首跳 ASN 与所选基准一致，不保证后续路径或应用出口一致
- 黄色 `⮜ 分流`：可见首跳 ASN 与基准不同，是需要进一步核查的分流线索
- 灰色 `路径隐藏 / 仅目标可见`：确认目标已回应，但没有可见的公网中间跳，无法判定分流
- `ASN 未知 / 无法判定`：首跳或基准 ASN 信息不足，不当作“未分流”
- DNS、解析、探测失败会显示各自原因，失败不再伪装成路径隐藏
- 延迟列：VPS 到本次选定目标 IP 的 MTR Avg，`<50ms` 绿色，`50–200ms` 黄色，`>200ms` 棕色；分流行整行黄色。目标未回应时显示 `-`，不以中途节点代替。达到 1000ms 时表格显示 `999+ms`，JSON 保留实际数值。TCP 回退测得的是 TCP 探测延迟，不是网页或应用响应时间
- 底部汇总：告诉你一共分了几条线，每条线走哪些域名
- 路径 ASN 摘要：辅助观察到达目标前的中途 ASN 变化，不直接等同于分流判断

![Egress-Check 路径 ASN 摘要效果图](assets/path-asn-summary-preview.png)

效果图为历史版本示例，状态含义以以上说明为准。MTR 能观察部分路由，无法证明 NAT / 代理后的目标实际看到哪个出口 IP，也不能仅凭 ASN 判定商家一定做了应用分流。

```text
Social
  ●  twitter.com               203.x.x.1        18.4ms     TW   AS4780 Digital United Inc.
  ●  facebook.com              104.28.0.0       86.7ms     US   AS13335 Cloudflare, Inc.    ⮜ 分流
  ●  instagram.com             104.28.0.0       91.2ms     US   AS13335 Cloudflare, Inc.    ⮜ 分流

IPv4 线路分流汇总 (基准 = 默认出口 AS4780)
────────────────────────────────────────────────────────────────────────
● Digital United Inc. (AS4780 · TW) 85 域名 ✓ 符合预期 (未分流)
● Cloudflare, Inc. (AS13335 · US) 8 域名 ⚠ 存在分流

IPv4 路径 ASN 摘要 (辅助观察, 不直接等同分流)
────────────────────────────────────────────────────────────────────────
AS22773 Cox Communications Inc. -> AS13335 Cloudflare, Inc.   12 域名
```

## 更新记录

### v2.19.1 修复

- 修复 v2.19 的 MTR 解析回归：MTR 0.95 的完全丢包行可能输出 `100.0`，不带 `%`。之前会把含此行的正常报告整份判失败，并触发无效重试；现在同时兼容两种写法。
- 中间跳不回应不再导致整条路径失败；保留已获得的公网首跳。目标没有回应时，目标延迟仍显示 `-`，不会拿中间跳延迟代替。
- 兼容 MTR 高延迟时的 `1028.` 数值格式，不再因一条中间跳的高延迟把整份报告判失败；目标数值会规范化为有效 JSON 数字。
- 正确跳过同一跳的备用 IP 续行，不再把它误当成缺少统计数据的新一跳而导致整份报告解析失败。
- 最后一次重试超时时保留此前的具体解析错误，不再覆盖成笼统的“无有效报告”。
- 增加来自真实 MTR 输出格式的脱敏样本，同时覆盖解析器和完整脚本回归测试。默认 6 并发、121 个域名和表格排版不变。

### v2.19 修复

- 修复部分 awk 不支持区间正则时，所有域名误报“路径隐藏 / 仅目标可见”的问题（Issue #3）；Issue #2 的空心图标属于此状态，不能仅凭图标认定网络隐藏。
- 先解析并固定目标 IP，再执行 MTR；目标 IP 不参与首跳 ASN 归类，延迟只取已回应目标的 Avg。目标未回应时显示 `-`，不再显示虚假的 `0.0ms`。
- 分别提示 DNS 失败、报告解析失败、探测失败和无回应；只有确认目标回应且没有公网中间跳才显示“路径隐藏”。ICMP 结果不足时尝试 TCP 443，默认每个域名探测预算 45 秒（终止进程另有短暂宽限），可设置 `MTR_BUDGET`。
- JSON 结论与明细一致：`true` 表示发现相对基准的 ASN 差异，`false` 表示所有项目均可比较且未发现差异，`null` 表示证据不足；新增 `summary.unknown`，它可能与 `hidden`、`down` 重叠，不能累加到总数。
- 兼容旧 Bash 的并发控制，每次运行使用独立临时目录；中断会清理本次探测进程，不删除其他检测任务的数据。
- 同一轮检测统一域名列宽，IPv6 预留完整地址宽度，延迟固定 9 字符；异常状态和彩色、无色输出保持对齐。
- 菜单选择 JSON 模式不再混入提示文字；200ms 按说明保持黄色，超过 200ms 才显示棕色。
- 保留 121 条规则、默认 6 并发和 1–7 菜单。

### v2.18 优化

- 新增 LINE、LINE TV 和 Zoom 分流检测
- Steam 新增 CDN 线路检测，不再只检测商店与社区页面
- Twitch 新增 CDN 线路检测，不再只检测官网首页
- 默认规则由 116 个域名增加至 121 个域名

<details>
<summary>历史更多更新记录（点击展开）</summary>

### v2.17 修复

- 修复交互菜单选择 `5) 低并发低压力模式` 时，因函数定义顺序导致 `default_mtr_concurrency: command not found` 的问题
- `--low-resource` 非交互模式也同步修复

### v2.16 调整

- 默认完整检测恢复固定 6 并发，优先保证检测速度
- 交互菜单新增“低并发低压力模式”，需要降低服务器压力时手动选择
- 低压力模式启用 CPU 核数自适应并发，并将 `MTR_COUNT` 降为 2
- 新增 `--low-resource` 参数，方便非交互一键启用省资源模式

### v2.15 优化

- 增加按 CPU 核数自适应的低压力并发策略
- `mtr` 进程默认使用较低优先级运行，减少检测时对业务进程的抢占
- `MTR_TIMEOUT`、`MTR_MAXTTL`、`MTR_COUNT`、`MTR_ATTEMPTS`、`MTR_NICE` 现在支持环境变量覆盖
- 如果服务器配置很低，可以用省资源模式：`MTR_CONCURRENCY=2 MTR_COUNT=2`

### v2.14 修复

- 修复 LXD / NAT 家宽融合场景下，`mtr` 只显示本地网关和目标站点 hostname，导致全量显示“探测失败 / 无公网跳”的问题
- 目标 IP / 目标 hostname 不再作为“首个公网跳”参与分流判断，避免把 Google / Cloudflare / OpenAI 等目标 ASN 误当作出口线路
- 新增 `hidden` 状态：当中间公网路径不可见时，显示“路径隐藏 / 仅目标可见”，不计入分流，也不算普通探测失败
- JSON summary 新增 `hidden` 计数，方便区分路径隐藏和真正探测失败

### v2.13 修复

- 修复 NAT / 隧道 / 代理拓扑下，HTTP 真实出口是家宽 ASN，但 `mtr` 首个公网跳是上游 VPS ASN，导致所有域名被误标为“分流”的问题
- 自动模式下如果 HTTP 出口 ASN 和 MTR 主路径 ASN 不一致，会提示 NAT/隧道拓扑，并按 MTR 主路径 ASN 判断域名之间是否分流
- 网络环境区新增 `IPv4 MTR` / `IPv6 MTR` 基准跳展示，方便区分“真实对外 IP”和“mtr 路由路径”
- 可用 `EGRESS_BASE_MODE=echo` 强制按 HTTP 出口 ASN 判断，或用 `EGRESS_BASE_MODE=mtr` 强制按 MTR 主路径 ASN 判断

### v2.12 修复

- 修复部分机器上 `mtr -r -n` report 输出为空或格式不同，导致交互 `mtr` 正常但脚本仍显示“探测失败 / 无公网跳”的问题
- 解析逻辑改为识别带 `Loss%` 的真实 hop 行，不再依赖固定跳点编号格式
- 数字 report 模式解析失败后，会自动回退到非数字 report 模式
- 新增 `EGRESS_DEBUG_MTR=1` 调试开关，可保存脚本实际执行的 mtr 原始输出

### v2.11 新增

- 新增“路径 ASN 摘要”：在主表下方按到达目标前的 ASN 链路分组展示路径变化，辅助观察是否存在中途转接
- 主表列宽和排版保持不变，路径摘要独立展示，避免新增信息导致表格错位
- 路径 ASN 摘要只做辅助判断，不直接等同于“分流”

### v2.10 修复

- 增强 `mtr` 输出解析：会先清理交互输出中的 ANSI 控制符和回车符，再识别跳点行
- `(waiting for reply)` 这类无 IP 行不会再覆盖已解析到的延迟结果
- 对带括号、标点或隐藏控制字符的 IP 字段做清洗，降低误判“探测失败 / 无公网跳”的概率

### v2.9 修复

- 修复部分 `mtr` 输出为 `1. IP/hostname ...` 格式时，被误判为“探测失败 / 无公网跳”的问题
- 现在同时兼容 `1.|-- IP ...` 和 `1. IP ...` 两类 mtr 行格式，并会跳过 `(waiting for reply)`

### v2.8 修复

- 修复极简系统首次运行时只自动安装 `mtr`、缺少 `jq` 后直接退出的问题
- 现在脚本会同时检测并自动安装 `mtr` 和 `jq`，安装失败时再给出手动安装命令

### v2.7 新增

- 修复分流明细行颜色：`⮜ 分流` 的整行内容保持黄色高亮，不会被延迟列颜色 reset 截断
- 修复延迟列含义：延迟现在取 `mtr` 到目标域名最后一跳的 Avg，不再取首个公网跳延迟
- 默认 `MTR_MAXTTL` 从 12 提高到 30，避免目标较远时只跑到中间路由
- 修复同一个首跳 IP 偶发显示不同国家 / ASN / ISP 的问题：同一批检测内按首跳 IP 直接复用已查到的完整结果
- 清洗异常 ASN 字段，避免把接口失败值显示成 `AS?? Unknown`
- 新增 IP / ASN 反查缓存：同一个首跳 IP 不重复请求接口，成功结果默认缓存 24 小时
- 优化 ASN / ISP 反查策略：优先选择国家、ASN、ISP 信息更完整的接口结果
- 新增 `延迟` 列：`<50ms` 绿色，`50-200ms` 黄色，`>200ms` 棕色
- 增加多地区电商域名：Shopee、Lazada、Temu、SHEIN、Rakuten、Coupang、Mercado Libre 等
- mtr 探测重试从 2 次增加到 4 次，降低偶发“无公网跳”失败

</details>

## 适合谁用

很多商家宣称自己的家宽服务没有做分流，或者并没有明确标记。用户花了大价钱，以为自己用了家宽，但社交媒体账号仍然被风控，并且完全不知道问题出在哪里。

这种情况下，需要确认商家是否对某些流量做了“线路优化 / 分流”。本工具会批量检测 100+ 个主流服务，帮助你快速验证服务器是否存在分流情况。

鸣谢：[https://ip.net.coffee](https://ip.net.coffee)

<details>
<summary>本地安装和高级用法</summary>

```bash
git clone https://github.com/AIFansX/egress-check.git
cd egress-check
chmod +x ip.sh
cp rules.conf.example rules.conf
./ip.sh
```

```bash
./ip.sh -I              # 交互菜单
./ip.sh                 # 默认完整检测
./ip.sh -4              # 只跑 IPv4
./ip.sh -6              # 只跑 IPv6
./ip.sh --only Social   # 只跑某个分类
./ip.sh --json          # JSON 输出
./ip.sh --no-color      # 关闭颜色
./ip.sh --low-resource  # 低并发低压力模式

MTR_CONCURRENCY=10 ./ip.sh
IP_LOOKUP_CACHE_TTL=3600 ./ip.sh
EGRESS_BASE_MODE=mtr ./ip.sh
EGRESS_BASE_MODE=echo ./ip.sh

# 省资源模式，适合 1 核小鸡 / NAT 容器
./ip.sh --low-resource
MTR_CONCURRENCY=2 MTR_COUNT=2 ./ip.sh
```

如果遇到手动 `mtr` 正常、脚本却显示“探测失败 / 无公网跳”，可以开启调试：

```bash
EGRESS_DEBUG_MTR=1 bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) --only AI
ls -la ~/.cache/egress-check/mtr-debug/
```

`rules.conf` 语法：

```text
分类 | 域名 | (保留) | (保留) | 备注
```

仓库提供 `rules.conf.example`。如果使用一键命令远程运行，脚本会自动使用内置默认规则。

</details>

<details>
<summary>安全说明</summary>

纯 bash 明文，无混淆，不安装后台服务。联网仅用于：

- `mtr` 探测公开域名
- `curl` 查询 ASN 和出口 IP

可自行审计：

```bash
grep -oE 'https?://[a-z0-9./]+' ip.sh | sort -u
grep -nE 'crontab|authorized_keys|nohup|disown|/dev/tcp|bash -i|curl.*\|.*sh' ip.sh
```

不会写 crontab，不碰 SSH，无反向连接。缺少依赖时会使用系统包管理器安装软件。临时文件写入 `~/.cache/egress-check/.run.*`，退出仅清理本次目录；IP / ASN 成功结果缓存到 `ip-lookup/`，默认 24 小时。`last.json` 保留最后完成的结果，多实例写入采用完整文件原子替换；开启调试时 `mtr-debug/` 的报告会保留。

</details>

<details>
<summary>运行环境和依赖说明</summary>

需要 Bash 4.0+，当前脚本主要面向 Linux VPS / Linux 服务器，包括常见发行版：

- Debian / Ubuntu：`apt-get`
- Alpine：`apk`
- CentOS / RHEL：`yum`
- Fedora / Rocky / AlmaLinux：`dnf`
- Arch Linux：`pacman`

不适合直接在 Windows CMD / PowerShell 里运行；如果是 Windows，需要 WSL 这类 Linux 环境。

脚本会自动检测并尝试安装 `mtr` 和 `jq`：

```text
apt-get install mtr-tiny jq / mtr jq
apk add mtr jq
yum install mtr jq
dnf install mtr jq
pacman -Sy mtr jq
```

自动安装需要满足两个条件：

- 当前用户是 `root`，或者系统有 `sudo`
- 服务器能正常访问软件源

如果没有 root/sudo，脚本会提示手动安装。

以下基础命令目前只检测，不自动安装：

```text
curl
timeout
awk
grep
ps
```

DNS 解析需要 `getent` 或 `nslookup`（优先系统解析器，遵循 hosts / 系统 DNS）。测试使用合成 MTR 报告覆盖 gawk、mawk、BusyBox awk 和旧 awk；每台服务器的防火墙、DNS、IPv6 和权限仍影响实际可达性。

开发者可运行 `python3 tests/test_regression.py` 重放回归测试，Linux 集成测试另需 `jq`，Python 只用于测试，运行 `ip.sh` 不需要 Python。

大多数 VPS 默认已有 `curl`、`awk`、`grep`、`timeout`，极简系统如果缺失会按提示手动补装。

如果商家禁用了 ICMP / traceroute / mtr 所需能力，或者容器环境不允许 raw socket，即使依赖齐全也可能探测失败。这属于运行环境限制，不是脚本逻辑问题。

</details>

## License

MIT
