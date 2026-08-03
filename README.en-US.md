

# Home Broadband VPS Traffic Splitting One-Click Self-Check: Egress-Check

Run a single command to detect if your server or home broadband exit route has traffic splitting, and quickly see if traffic to platforms like Meta, streaming services, finance, and e-commerce actually takes the same route.

It's ideal for verifying services marketed as "Home Broadband VPS / Native Home Broadband / Non-Split Routes": no guessing, no asking customer support—just run it to get the exit routes, ASNs, and latency for 100+ common platforms.

## One-Click Check

Copy and paste the following line into your SSH terminal:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) -I
```

After running, enter `1-7` to select a check mode:

```text
1) Default Full Check       Network Environment + IPv4 + IPv6
2) IPv4 Only
3) IPv6 Only
4) Specific Category Only     AI / Social / Streaming / Search / Developer / Cloud / Crypto / Gaming
5) Low Concurrency / Low Pressure Mode   CPU-adaptive concurrency + reduced probe packets for smoother operation
6) JSON Output           Suitable for cron / monitoring
7) High Concurrency Log Mode  Concurrency 10 + disable colors
```

One-click full split check:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh)
```

Quick AI split check:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) --only AI
```

Quick social media split check:

```bash
bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) --only Social
```

## Key Features

- **One-Click Home Broadband Verification**: Copy the command to SSH, select from the menu, and run the check.
- **Directly Catches Split Evidence**: See at a glance which domains use the default exit route and which are diverted to other ASNs.
- **Covers Real-World Scenarios**: Checks 100+ domains across AI, social media, streaming, finance, e-commerce, developer platforms, cloud services, gaming, and more.
- **Latency Quality Check**: Not only detects splitting but also shows the average `mtr` latency from the VPS to the target domains.
- **Ideal for Account Risk Control Troubleshooting**: Quickly verify if the routing matches the provider's claims when social media, e-commerce, or finance accounts trigger risk controls.

![Egress-Check 分流检测效果图](assets/egress-check-preview.png)

## v2.18 Optimization

- Added LINE, LINE TV, and Zoom split checks
- Steam added CDN route checks, no longer limited to store and community pages
- Twitch added CDN route checks, no longer limited to the official homepage
- Default rules increased from 116 to 121 domains

## v2.17 Fixes

- Fixed `default_mtr_concurrency: command not found` error when selecting `5) Low Concurrency / Low Pressure Mode` in the interactive menu due to function definition order
- `--low-resource` non-interactive mode also fixed

## v2.16 Adjustments

- Restored fixed concurrency of 6 for the default full check to prioritize check speed
- Added "Low Concurrency / Low Pressure Mode" to the interactive menu for manual selection when server load needs to be reduced
- Low pressure mode enables CPU core-adaptive concurrency and reduces `MTR_COUNT` to 2
- Added `--low-resource` flag for easy one-click activation of resource-saving mode in non-interactive use

## v2.15 Optimization

- Added low-pressure concurrency strategy that adapts to CPU core count
- `mtr` processes now run with lower default priority to reduce resource contention with business processes
- `MTR_TIMEOUT`, `MTR_MAXTTL`, `MTR_COUNT`, `MTR_ATTEMPTS`, `MTR_NICE` now support environment variable overrides
- For very low-spec servers, use resource-saving mode: `MTR_CONCURRENCY=2 MTR_COUNT=2`

## v2.14 Fixes

- Fixed LXD / NAT home broadband merged scenarios where `mtr` only showed the local gateway and target hostname, causing all results to display "Probe Failed / No Public Hops"
- Target IP / target hostname no longer count as the "first public hop" for split judgment, preventing false positives where target ASNs (e.g., Google / Cloudflare / OpenAI) are mistaken for exit routes
- Added `hidden` status: displays "Path Hidden / Target Only Visible" when intermediate public paths are invisible, excluding them from split counts and standard probe failures
- JSON summary now includes a `hidden` count to distinguish between hidden paths and actual probe failures

## v2.13 Fixes

- Fixed NAT / tunnel / proxy topologies where the HTTP exit ASN is the home broadband ASN, but `mtr`'s first public hop is the upstream VPS ASN, causing all domains to be falsely flagged as "split"
- In auto mode, if the HTTP exit ASN and MTR main path ASN mismatch, it prompts for NAT/tunnel topology and uses the MTR main path ASN to judge splits between domains
- Network environment section now includes `IPv4 MTR` / `IPv6 MTR` baseline hop displays to help distinguish "real external IP" from "mtr routing path"
- Can force judgment by HTTP exit ASN with `EGRESS_BASE_MODE=echo`, or force judgment by MTR main path ASN with `EGRESS_BASE_MODE=mtr`

## v2.12 Fixes

- Fixed `mtr -r -n` report output being empty or differently formatted on some machines, causing interactive `mtr` to work normally but the script to still show "Probe Failed / No Public Hops"
- Parsing logic now identifies real hop lines containing `Loss%`, no longer relying on fixed hop number formats
- Falls back to non-numeric report mode automatically if numeric report parsing fails
- Added `EGRESS_DEBUG_MTR=1` debug switch to save the script's actual raw `mtr` output

## v2.11 Additions

- Added "Path ASN Summary": displays path changes grouped by the ASN chain before reaching the target, below the main table, to assist in observing mid-path handoffs
- Main table column width and layout remain unchanged; path summary displays independently to avoid table misalignment
- Path ASN summary is for auxiliary judgment only and does not directly equate to "split"

## v2.10 Fixes

- Enhanced `mtr` output parsing: strips ANSI control characters and carriage returns from interactive output before identifying hop lines
- Lines like `(waiting for reply)` no longer overwrite previously parsed latency results
- Cleans IP fields containing brackets, punctuation, or hidden control characters to reduce false "Probe Failed / No Public Hops" judgments

## v2.9 Fixes

- Fixed `mtr` output in `1. IP/hostname ...` format being misjudged as "Probe Failed / No Public Hops"
- Now supports both `1.|-- IP ...` and `1. IP ...` `mtr` line formats, and skips `(waiting for reply)`

## v2.8 Fixes

- Fixed minimal systems exiting directly on first run because only `mtr` was auto-installed while `jq` was missing
- The script now checks and auto-installs both `mtr` and `jq`, providing manual installation commands if auto-install fails

## v2.7 Additions

- Fixed split detail line color: the entire `⮜ Split` line now stays yellow-highlighted without being truncated by latency column color resets
- Fixed latency column meaning: latency now uses the `mtr` Avg of the last hop to the target domain, not the first public hop latency
- Default `MTR_MAXTTL` increased from 12 to 30 to prevent stopping at intermediate routers for distant targets
- Fixed sporadic display of different countries / ASNs / ISPs for the same first-hop IP: results are cached and reused within the same batch check
- Cleans abnormal ASN fields to prevent interface failure values from displaying as `AS?? Unknown`
- Added IP / ASN reverse lookup cache: same first-hop IP is not repeatedly queried; successful results cache for 24 hours by default
- Optimized ASN / ISP reverse lookup strategy: prioritizes interface results with more complete country, ASN, and ISP information
- Added `Latency` column: `<50ms` green, `50-200ms` yellow, `>200ms` brown
- Added multi-region e-commerce domains: Shopee, Lazada, Temu, SHEIN, Rakuten, Coupang, Mercado Libre, etc.
- Increased `mtr` probe retries from 2 to 4 to reduce sporadic "No Public Hops" failures

## Who Should Use This

Many providers claim their home broadband services do not use traffic splitting, or fail to explicitly label it. Users spend considerable money assuming they have a clean home broadband route, only to find their social media accounts still trigger risk controls, with no clear idea of the root cause.

In such cases, it's necessary to verify if the provider is performing "route optimization / traffic splitting" on specific traffic. This tool batches checks against 100+ mainstream services, helping you quickly verify if your server has traffic splitting.

Credits: [https://ip.net.coffee](https://ip.net.coffee)

## How to Read the Results

- Green: Same route as the default exit
- Yellow `⮜ Split`: Different exit route
- Gray `Path Hidden / Target Only Visible`: `mtr` cannot see intermediate public hops, cannot be used for split judgment
- Latency column: `mtr` Avg to the last hop of the target domain, `<50ms` green, `50-200ms` yellow, `>200ms` brown
- Bottom summary: Shows how many routes exist and which domains use each
- Path ASN summary: Assists in observing mid-path ASN changes before reaching the target, not a direct split judgment

![Egress-Check 路径 ASN 摘要效果图](assets/path-asn-summary-preview.png)

```text
Social
  ●  twitter.com               203.x.x.1        18.4ms     TW   AS4780 Digital United Inc.
  ●  facebook.com              104.28.0.0       86.7ms     US   AS13335 Cloudflare, Inc.    ⮜ Split
  ●  instagram.com             104.28.0.0       91.2ms     US   AS13335 Cloudflare, Inc.    ⮜ Split

IPv4 Route Split Summary (Baseline = Default Exit AS4780)
────────────────────────────────────────────────────────────────────────
● Digital United Inc. (AS4780 · TW) 85 domains ✓ As expected (No split)
● Cloudflare, Inc. (AS13335 · US) 8 domains ⚠ Split detected

IPv4 Path ASN Summary (Auxiliary observation, not equivalent to split judgment)
────────────────────────────────────────────────────────────────────────
AS22773 Cox Communications Inc. -> AS13335 Cloudflare, Inc.   12 domains
```

<details>
<summary>Local Installation & Advanced Usage</summary>

```bash
git clone https://github.com/AIFansX/egress-check.git
cd egress-check
chmod +x ip.sh
cp rules.conf.example rules.conf
./ip.sh
```

```bash
./ip.sh -I              # Interactive menu
./ip.sh                 # Default full check
./ip.sh -4              # IPv4 only
./ip.sh -6              # IPv6 only
./ip.sh --only Social   # Specific category only
./ip.sh --json          # JSON output
./ip.sh --no-color      # Disable colors
./ip.sh --low-resource  # Low concurrency / low pressure mode

MTR_CONCURRENCY=10 ./ip.sh
IP_LOOKUP_CACHE_TTL=3600 ./ip.sh
EGRESS_BASE_MODE=mtr ./ip.sh
EGRESS_BASE_MODE=echo ./ip.sh

# Resource-saving mode, suitable for 1-core VPS / NAT containers
./ip.sh --low-resource
MTR_CONCURRENCY=2 MTR_COUNT=2 ./ip.sh
```

If manual `mtr` works but the script shows "Probe Failed / No Public Hops", enable debug mode:

```bash
EGRESS_DEBUG_MTR=1 bash <(curl -Ls https://raw.githubusercontent.com/AIFansX/egress-check/main/ip.sh) --only AI
ls -la ~/.cache/egress-check/mtr-debug/
```

`rules.conf` syntax:

```text
Category | Domain | (Reserved) | (Reserved) | Notes
```

The repo provides `rules.conf.example`. If running remotely via the one-liner, the script will automatically use built-in default rules.

</details>

<details>
<summary>Security Notice</summary>

Pure Bash plaintext, no obfuscation, no persistence, no privilege escalation backdoors. Internet access is only used for:

- `mtr` probing public domains
- `curl` querying ASN and exit IP

You can audit it yourself:

```bash
grep -oE 'https?://[a-z0-9./]+' ip.sh | sort -u
grep -nE 'crontab|authorized_keys|nohup|disown|/dev/tcp|bash -i|curl.*\|.*sh' ip.sh
```

Does not write to crontab, does not touch SSH, no reverse connections, no download-and-execute. Temporary files are written to `~/.cache/egress-check/` and automatically cleaned upon exit; successful IP/ASN reverse lookup results are cached in `~/.cache/egress-check/ip-lookup/` for 24 hours by default to avoid repeated requests to public APIs.

</details>

<details>
<summary>Environment & Dependencies</summary>

This script primarily supports Linux VPS / Linux servers, including common distributions:

- Debian / Ubuntu: `apt-get`
- Alpine: `apk`
- CentOS / RHEL: `yum`
- Fedora / Rocky / AlmaLinux: `dnf`
- Arch Linux: `pacman`

Not suitable for direct execution in Windows CMD / PowerShell; if on Windows, a Linux environment like WSL is required.

The script will automatically detect and attempt to install `mtr` and `jq`:

```text
apt-get install mtr-tiny jq / mtr jq
apk add mtr jq
yum install mtr jq
dnf install mtr jq
pacman -Sy mtr jq
```

Auto-installation requires two conditions:

- The current user is `root`, or the system has `sudo`
- The server can normally access package repositories

If root/sudo is unavailable, the script will prompt for manual installation.

The following base commands are only checked, not auto-installed:

```text
curl
timeout
awk
grep
```

Most VPS come with `curl`, `awk`, `grep`, `timeout` by default. Minimal systems missing these will need manual installation as prompted.

If the provider has disabled ICMP / traceroute / mtr capabilities, or the container environment does not allow raw sockets, probes may fail even if dependencies are met. This is an environment limitation, not a script logic issue.

</details>

## License

MIT
