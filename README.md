# 分流检测 Egress-Check

一条命令检测服务器 / 家宽出口是否存在分流，快速看出访问 Meta、流媒体、金融、电商等平台时，实际走的是不是同一条线路。

## 一键完成检测

复制下面这一行到 SSH 里运行：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AI-Fans-X/egress-check/main/ip.sh) -I
```

运行后输入 `1-6` 选择检测模式：

```text
1) 默认完整检测      网络环境 + IPv4 + IPv6
2) 只检测 IPv4
3) 只检测 IPv6
4) 只检测指定分类    AI / Social / Streaming / Search / Developer / Cloud / Crypto / Gaming / Ecommerce / China
5) JSON 输出         适合 cron / 监控
6) 高并发日志模式    并发 10 + 关闭颜色
```

直接完整检测：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AI-Fans-X/egress-check/main/ip.sh)
```

## v2.3 新增

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
- 延迟列：`<50ms` 绿色，`50-200ms` 黄色，`>200ms` 棕色
- 底部汇总：告诉你一共分了几条线，每条线走哪些域名

```text
Social
      域名                       首个公网跳         延迟       国家  ASN / ISP
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
git clone https://github.com/AI-Fans-X/egress-check.git
cd egress-check
chmod +x egress-check.sh
cp rules.conf.example rules.conf
./egress-check.sh
```

```bash
./egress-check.sh -I              # 交互菜单
./egress-check.sh                 # 默认完整检测
./egress-check.sh -4              # 只跑 IPv4
./egress-check.sh -6              # 只跑 IPv6
./egress-check.sh --only Social   # 只跑某个分类
./egress-check.sh --json          # JSON 输出
./egress-check.sh --no-color      # 关闭颜色

MTR_CONCURRENCY=10 ./egress-check.sh
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
grep -oE 'https?://[a-z0-9./]+' egress-check.sh | sort -u
grep -nE 'crontab|authorized_keys|nohup|disown|/dev/tcp|bash -i|curl.*\|.*sh' egress-check.sh
```

不会写 crontab，不碰 SSH，无反向连接，无下载执行。临时文件写入 `~/.cache/egress-check/`，退出自动清理。

</details>

## License

MIT
