# 家宽VPS分流一键自查检测 Egress-Check

一条命令自查服务器 / 家宽的可见路由差异，快速对比访问 Meta、流媒体、金融、电商等平台时的首个公网跳、ASN 和目标延迟。

它适合辅助验收“家宽 VPS / 原生家宽 / 不分流线路”这类服务：一键对比 100+ 个常见平台的可见路由、ASN 和目标延迟，发现值得进一步核查的差异。

## 一键完成检测

复制下面这一行到 SSH 里运行：

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) -I
```

运行后输入 `0-7` 选择检测模式，直接回车默认选择 `1`：

```text
0) 简洁模式          基于完整检测，展示更加简洁的排版效果
1) 【默认】完整检测  网络环境 + IPv4 + IPv6，完整结果
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

- 绿色：有效 ASN 与所选基准相同，即显示正常；不再要求同 IP、同跳数、同探测协议或前段完整回应。JSON 为 `split: false`、`comparison_scope: "asn"`。这是 ASN 层面的比较，不保证后续路径或应用出口一致
- 黄色 `⮜ 分流`：在首跳之前无缺失或多回应歧义、与稳定基准跳数及协议一致，并经同一目标 IP 复测后，仍存在首跳 ASN 差异。它是路由线索，不证明目标实际看到的出口已改变
- 灰色 `路径隐藏 / 仅目标可见`：确认目标已回应，但没有可见的公网中间跳，无法判定分流
- `ASN 未知 / 无法判定`：首跳或基准 ASN 信息不足，不当作“未分流”
- `首跳证据不足 / 无法判定`：ASN 与基准不同，但前段缺失、同一跳多个回应 IP、跳数或协议不一致，或基准、异常复测不稳定，无法确认差异。这些额外条件不再限制同 ASN 项目的正常显示
- DNS、解析、探测失败会显示各自原因，失败不再伪装成路径隐藏
- 延迟列：VPS 到本次选定目标 IP 的 MTR Avg，`<50ms` 绿色，`50–200ms` 黄色，`>200ms` 棕色；分流行整行黄色。目标未回应时显示 `-`，不以中途节点代替。达到 1000ms 时表格显示 `999+ms`，JSON 保留实际数值。TCP 回退测得的是 TCP 探测延迟，不是网页或应用响应时间
- 底部汇总：按可见 ASN 与判定状态分组。完整模式下，与基准一致的每组最多展开 10 个域名，超出时在第 10 个域名后直接接 `...`，不另起提示行；简洁模式下只显示这类组的数量和状态，不展开域名。两种模式均完整展示疑似分流和无法判定组的域名，统计数量、上方检测明细及 JSON 不受影响。不同 ASN 数量不等于不同真实出口数量
- 路径 ASN 摘要：辅助观察到达目标前的中途 ASN 变化，不直接等同于分流判断。忽略无效的 AS0，仅按前两个有效 ASN 合并展示，例如 `1→2→3` 和 `1→2→4` 合并为 `1→2`；只有一个有效 ASN 时单独展示。每个路径组最多展示 10 个域名，超出时在最后一行末尾加 `...`；统计总数和 JSON 完整路径保持不变

简洁模式执行与完整模式相同的检测：明细保留状态标记、域名、目标延迟、地区、ASN 编号及必要的分流标记或异常原因，隐藏首跳 IP 和运营商名称，颜色不变；不显示 IPv4 / IPv6 路径 ASN 摘要，正常组汇总只显示数量和状态。也可追加 `--compact` 直接运行；与 `--json` 同用时仍输出完整 JSON 数据。

![Egress-Check 路径 ASN 摘要效果图](assets/path-asn-summary-preview.png)

效果图为历史版本示例，状态含义以以上说明为准。MTR 能观察部分路由，无法证明 NAT / 代理后的目标实际看到哪个出口 IP，也不能仅凭 ASN 判定商家一定做了应用分流。

```text
Social
  ●  twitter.com               203.x.x.1        18.4ms     TW   AS4780 Digital United Inc.
  ●  facebook.com              104.28.0.0       86.7ms     US   AS13335 Cloudflare, Inc.    ⮜ 分流
  ●  instagram.com             104.28.0.0       91.2ms     US   AS13335 Cloudflare, Inc.    ⮜ 分流

IPv4 线路分流汇总 (基准 = 默认出口 AS4780)
────────────────────────────────────────────────────────────────────────
● Digital United Inc. (AS4780 · TW) 1 域名 ✓ 符合预期（未分流）
● Cloudflare, Inc. (AS13335 · US) 2 域名 ⚠ 首跳差异已复测（疑似分流）

检测到分流: 1 条非默认线路, 2 个域名被分流到其他出口

IPv4 路径 ASN 摘要 (辅助观察, 不直接等同分流)
────────────────────────────────────────────────────────────────────────
AS4780 Digital United Inc.    1 域名
  twitter.com
AS13335 Cloudflare, Inc.      2 域名
  facebook.com  instagram.com
```

## 更新记录

### v2.19.6 调整

- 同 ASN 显示正常，不同 ASN 继续复核；恢复清晰直观的分流结果提示。
- 简洁模式保留域名、延迟、地区和 ASN，优化列对齐、日期及服务器时区展示。
- 路径摘要按前两个有效 ASN 合并；正常组和路径组最多展示 10 个域名，超出以 `...` 结尾，分流组完整展示，JSON 数据保持完整。

### v2.19.5 修复

- 修复前段网关不回应导致基准丢失的问题，细化无法判定原因。
- 新增 JSON 比较范围标记；当时的同 IP、同跳数匹配已由 v2.19.6 的同 ASN 规则替代。

### v2.19.4 优化

- 新增简洁模式（`0` / `--compact`），默认仍为完整检测，优化汇总和列对齐。
- 当时隐藏的 ASN 编号已在 v2.19.6 恢复显示。

## 适合谁用

很多商家宣称自己的家宽服务没有做分流，或者并没有明确标记。用户花了大价钱，以为自己用了家宽，但社交媒体账号仍然被风控，并且完全不知道问题出在哪里。

这种情况下，需要核查商家是否对某些流量做了“线路优化 / 分流”。本工具批量检测 100+ 个主流服务，帮助发现可见路由差异；是否改变应用出口，还需要结合目标侧日志或针对应用的出口验证。

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
./ip.sh --compact       # 同样完整检测，报告更简洁
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
