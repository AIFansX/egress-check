# 分流检测 Egress-Check

服务器出口线路分流自查工具。在 SSH 上跑一条命令，自动检测这台机器访问各大网站时实际走了几条出口线路，一眼看出商家有没有做分流、哪些域名走了不同的国际线路。

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AI-Fans-X/egress-check/main/main.sh) -I
```

`-I` 会打开交互菜单，输入 `1-6` 就能选择检测模式。以后如果你把短域名指向这个脚本，也可以做成类似 `bash <(curl -Ls https://check.place) -I` 这样的短命令。

鸣谢：[https://ip.net.coffee](https://ip.net.coffee)

## 它解决什么问题

很多 VPS 商家宣称对某些流量（如 Meta 系、流媒体）做了“线路优化/分流”，但用户无从验证。本工具用 `mtr` 取每个域名的第一个公网跳，反查其 ASN：

- 同一 ASN = 同一条出口线路
- 不同 ASN = 走了不同线路 = 存在分流

以你的默认出口 ASN 为基准：走基准线路的域名标绿，走其他线路的域名整行黄色高亮并带 `⮜ 分流` 标记。底部按线路分组汇总，明确告诉你分了几条线、每条线走哪些域名。

## 输出示例

```text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
分流检测 Egress-Check v2.2 https://ip.net.coffee
host: my-vps 2026-06-05T20:00:00+08:00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

网络环境 (真实对外 IP)
────────────────────────────────────
默认出口 IPv4 ★
IPv4 出口 203.x.x.x TW · AS4780 Digital United Inc.
IPv6 出口 不可用 / 已禁用

IPv4 线路分流检测 ──────────────────────────────

Social
  ●  twitter.com       203.x.x.1     TW   AS4780 Digital United Inc.
  ●  facebook.com      104.28.0.0    US   AS13335 Cloudflare, Inc.    ⮜ 分流
  ●  instagram.com     104.28.0.0    US   AS13335 Cloudflare, Inc.    ⮜ 分流

IPv4 线路分流汇总 (基准 = 默认出口 AS4780)
────────────────────────────────────────────
● Digital United Inc. (AS4780 · TW) 85 域名 ✓ 符合预期 (未分流)
● Cloudflare, Inc. (AS13335 · US) 8 域名 ⚠ 存在分流
facebook.com instagram.com threads.net whatsapp.com ...

⚠ 检测到分流: 1 条非默认线路, 8 个域名被分流到其他出口
```

## 功能

- 逐组渐进展示：按分类一组组检测，跑完一组立即出结果
- 组内并发：默认 6 并发（`MTR_CONCURRENCY` 可调），mtr `-c 1` + 双轮重试容错
- 基准对比高亮：默认出口=绿，分流=黄，一眼区分
- 商家 SNAT 检测：跑多个独立回声服务，若看到不同对外 IP，则提示商家可能在做源地址分流
- IPv4 / IPv6 双栈：自动检测，IPv6 不可用则跳过并说明
- JSON 输出：`--json` 供 cron 和监控消费
- 零配置数据源：HTTPS API 查 ASN，无需注册、token 或本地数据库

## 一键运行

交互菜单版，适合第一次使用：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AI-Fans-X/egress-check/main/main.sh) -I
```

菜单会显示：

```text
1) 默认完整检测      网络环境 + IPv4 + IPv6
2) 只检测 IPv4
3) 只检测 IPv6
4) 只检测指定分类    AI / Social / Streaming / Search / Developer / Cloud / Crypto / Gaming / Ecommerce / China
5) JSON 输出         适合 cron / 监控
6) 高并发日志模式    并发 10 + 关闭颜色
```

不进菜单，直接跑完整检测：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AI-Fans-X/egress-check/main/main.sh)
```

如果你的系统不支持 `<(...)` 进程替换，也可以用管道方式：

```bash
curl -Ls https://raw.githubusercontent.com/AI-Fans-X/egress-check/main/main.sh | bash -s -- -I
```

## 本地安装

```bash
git clone https://github.com/AI-Fans-X/egress-check.git
cd egress-check
chmod +x egress-check.sh
cp rules.conf.example rules.conf
./egress-check.sh
```

依赖：bash 4+、mtr、curl、jq、coreutils。脚本启动时自动检测依赖；缺 mtr 时会尝试用 apt/apk/yum/dnf/pacman 自动安装（需 root/sudo）。

## 命令行用法

```bash
./egress-check.sh -I              # 交互菜单: 输入 1-6 选择模式
./egress-check.sh                 # 默认: 网络环境 + IPv4 + IPv6 分流检测
./egress-check.sh -4              # 只跑 IPv4
./egress-check.sh -6              # 只跑 IPv6
./egress-check.sh --only Social   # 只跑某个分类
./egress-check.sh --json          # JSON 输出
./egress-check.sh --no-color      # 关闭颜色，适合写日志

MTR_CONCURRENCY=10 ./egress-check.sh   # 调高组内并发
```

## rules.conf 语法

```text
分类 | 域名 | (保留) | (保留) | 备注
```

只用前两个字段（分类、域名），第 3/4 字段保留兼容旧格式。`#` 开头为注释。仓库提供 `rules.conf.example`，`rules.conf` 被 `.gitignore` 忽略，本地改动不会和上游冲突。

## 工作原理与局限

```text
你的机器 -> 内网网关(私网,过滤) -> 第一个公网跳 <- 这跳的 ASN = 线路指纹
                                      |
                         不同域名走不同公网跳 = 商家做了线路分流
```

能检测：线路/路径分流（不同域名走不同国际出口线路，即使最终公网 IP 相同）。

同时检测：商家 SNAT 源地址分流（多个回声服务看到不同对外 IP）。

不检测：目标网站本身的 CDN 调度（那是对方的事，与你的出口无关）。

## 安全说明

纯 bash 明文，无混淆、无持久化、无提权后门。完整可审计：

```bash
# 所有联网目标（只读查询 ASN/出口 IP）
grep -oE 'https?://[a-z0-9./]+' egress-check.sh | sort -u

# 确认无常见后门痕迹（应无输出）
grep -nE 'crontab|authorized_keys|nohup|disown|/dev/tcp|bash -i|curl.*\|.*sh' egress-check.sh
```

联网仅用于：`mtr` 探测域名，`curl` 查询 ASN（ipinfo.io、ip.sb、ipwho.is）以及查询出口 IP 的回声服务。

不会写 crontab，不碰 SSH，无反向连接，无下载执行。临时文件写入 `~/.cache/egress-check/`，权限为 600/700，退出自动清理。

隐私提示：你查询的出口 IP 会被 ASN 查询服务看到；mtr 探测的域名会被沿途路由器看到。但这些是服务器公网 IP 和公开域名，不涉及个人隐私。

## License

MIT
