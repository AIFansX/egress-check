# 家宽VPS分流一键自查检测 Egress-Check

一条命令检测服务器 / 家宽出口是否存在分流，快速看出访问 Meta、流媒体、金融、电商等平台时，实际走的是不是同一条线路。

它适合用来验收“家宽 VPS / 原生家宽 / 不分流线路”这类服务：不用猜、不用问客服，直接把 100+ 个常见平台的出口线路、ASN 和延迟跑出来。

## 一键完成检测

复制下面这一行到 SSH 里运行：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) -I
```

运行后输入 `1-6` 选择检测模式：

```text
1) 默认完整检测      网络环境 + IPv4 + IPv6
2) 只检测 IPv4
3) 只检测 IPv6
4) 只检测指定分类    AI / Social / Streaming / Search / Developer / Cloud / Crypto / Gaming
5) JSON 输出         适合 cron / 监控
6) 高并发日志模式    并发 10 + 关闭颜色
```

直接完整检测：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh)
```

## 核心卖点

- **一键验收家宽线路**：复制命令到 SSH，按菜单选择即可检测。
- **直接抓分流证据**：哪些域名走默认出口、哪些域名被甩到其他 ASN，一屏看清。
- **覆盖真实使用场景**：AI、社交、流媒体、金融、电商、开发者平台、云服务、游戏等 100+ 域名。
- **同时看延迟质量**：不只判断有没有分流，还能看到 VPS 到目标域名的 mtr 平均延迟。
- **适合排查账号风控**：当社交媒体、电商、金融平台账号异常时，可以快速确认线路是否和商家承诺一致。

## v2.10 修复

- 增强 `mtr` 输出解析：会先清理交互输出中的 ANSI 控制符和回车符，再识别跳点行
- `(waiting for reply)` 这类无 IP 行不会再覆盖已解析到的延迟结果
- 对带括号、标点或隐藏控制字符的 IP 字段做清洗，降低误判“探测失败 / 无公网跳”的概率

## v2.9 修复

- 修复部分 `mtr` 输出为 `1. IP/hostname ...` 格式时，被误判为“探测失败 / 无公网跳”的问题
- 现在同时兼容 `1.|-- IP ...` 和 `1. IP ...` 两类 mtr 行格式，并会跳过 `(waiting for reply)`

## v2.8 修复

- 修复极简系统首次运行时只自动安装 `mtr`、缺少 `jq` 后直接退出的问题
- 现在脚本会同时检测并自动安装 `mtr` 和 `jq`，安装失败时再给出手动安装命令

## v2.7 新增

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

## 适合谁用

很多商家宣称自己的家宽服务没有做分流，或者并没有明确标记。用户花了大价钱，以为自己用了家宽，但社交媒体账号仍然被风控，并且完全不知道问题出在哪里。

这种情况下，需要确认商家是否对某些流量做了“线路优化 / 分流”。本工具会批量检测 100+ 个主流服务，帮助你快速验证服务器是否存在分流情况。

鸣谢：[https://ip.net.coffee](https://ip.net.coffee)

## 怎么看结果

- 绿色：和默认出口同一条线路
- 黄色 `⮜ 分流`：走了不同出口线路
- 延迟列：VPS 到目标域名最后一跳的 mtr Avg，`<50ms` 绿色，`50-200ms` 黄色，`>200ms` 棕色
- 底部汇总：告诉你一共分了几条线，每条线走哪些域名

```text
Social
  ●  twitter.com               203.x.x.1        18.4ms     TW   AS4780 Digital United Inc.
  ●  facebook.com              104.28.0.0       86.7ms     US   AS13335 Cloudflare, Inc.    ⮜ 分流
  ●  instagram.com             104.28.0.0       91.2ms     US   AS13335 Cloudflare, Inc.    ⮜ 分流

IPv4 线路分流汇总 (基准 = 默认出口 AS4780)
────────────────────────────────────────────────────────────────────────
● Digital United Inc. (AS4780 · TW) 85 域名 ✓ 符合预期 (未分流)
● Cloudflare, Inc. (AS13335 · US) 8 域名 ⚠ 存在分流
```

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

MTR_CONCURRENCY=10 ./ip.sh
IP_LOOKUP_CACHE_TTL=3600 ./ip.sh
```

`rules.conf` 语法：

```text
分类 | 域名 | (保留) | (保留) | 备注
```

仓库提供 `rules.conf.example`。如果使用一键命令远程运行，脚本会自动使用内置默认规则。

</details>

<details>
<summary>安全说明</summary>

纯 bash 明文，无混淆、无持久化、无提权后门。联网仅用于：

- `mtr` 探测公开域名
- `curl` 查询 ASN 和出口 IP

可自行审计：

```bash
grep -oE 'https?://[a-z0-9./]+' ip.sh | sort -u
grep -nE 'crontab|authorized_keys|nohup|disown|/dev/tcp|bash -i|curl.*\|.*sh' ip.sh
```

不会写 crontab，不碰 SSH，无反向连接，无下载执行。临时文件写入 `~/.cache/egress-check/`，退出自动清理；IP / ASN 反查成功结果会缓存到 `~/.cache/egress-check/ip-lookup/`，默认 24 小时，避免重复请求公开接口。

</details>

<details>
<summary>运行环境和依赖说明</summary>

当前脚本主要支持 Linux VPS / Linux 服务器，包括常见发行版：

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
```

大多数 VPS 默认已有 `curl`、`awk`、`grep`、`timeout`，极简系统如果缺失会按提示手动补装。

如果商家禁用了 ICMP / traceroute / mtr 所需能力，或者容器环境不允许 raw socket，即使依赖齐全也可能探测失败。这属于运行环境限制，不是脚本逻辑问题。

</details>

## License

MIT
