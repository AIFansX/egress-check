#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# 家宽VPS分流一键自查检测 Egress-Check v2.13      鸣谢：https://ip.net.coffee
#
# 用 mtr 取每个域名的"第一个公网跳", 按 ASN 自动分组上色, 直接可视化线路分流.
# 不同 ASN = 不同出口线路 = 商家做了分流. 一眼看出分了几条线, 哪些域名走哪条.
#
# 默认行为 (无 -4/-6):
#   1. 检测默认出口 + IPv4/IPv6 真实对外 IP (含商家 SNAT 检测)
#   2. IPv4 线路分流检测 (按分类逐组并发 mtr → 第一公网跳 → ASN 分组)
#   3. IPv6 线路分流检测 (不可用则跳过)
#
# 以默认出口 ASN 为基准: 相同=未分流(绿), 不同=分流(高亮告警).
# 退出码: 0=成功  1=配置/依赖错误  2=有域名探测失败
#
# 环境变量: MTR_CONCURRENCY(组内并发数,默认6)  EGRESS_RULES  EGRESS_CACHE  IP_LOOKUP_CACHE_TTL
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

VERSION="2.13"
BRAND_URL="https://ip.net.coffee"

# ─── 颜色 ──────────────────────────────────────────────────────────────────
USE_COLOR=1
[[ -t 1 ]] || USE_COLOR=0
set_colors() {
    if [[ $USE_COLOR -eq 1 ]]; then
        R=$'\e[0m'; BOLD=$'\e[1m'; DIM=$'\e[2m'
        RED=$'\e[31m'; GREEN=$'\e[32m'; YELLOW=$'\e[33m'
        BLUE=$'\e[34m'; MAGENTA=$'\e[35m'; CYAN=$'\e[36m'; GRAY=$'\e[90m'; BROWN=$'\e[38;5;130m'
    else
        R=""; BOLD=""; DIM=""
        RED=""; GREEN=""; YELLOW=""; BLUE=""; MAGENTA=""; CYAN=""; GRAY=""; BROWN=""
    fi
}
set_colors
err() { printf "%s[!]%s %s\n" "$RED" "$R" "$*" >&2; }

SCRIPT_SOURCE="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" 2>/dev/null && pwd || pwd)"
RULES_FILE="${EGRESS_RULES:-$SCRIPT_DIR/rules.conf}"
if [[ -n "${EGRESS_CACHE:-}" ]]; then
    CACHE_DIR="$EGRESS_CACHE"
else
    if [[ -z "${HOME:-}" ]]; then
        err "HOME 未设置且未指定 EGRESS_CACHE."
        exit 1
    fi
    CACHE_DIR="$HOME/.cache/egress-check"
fi

PASS_MODE="auto"
OUTPUT_JSON=0
INTERACTIVE=0
ONLY_CAT=""
MTR_TIMEOUT=20
MTR_MAXTTL=30
MTR_COUNT=3
MTR_ATTEMPTS=4
PATH_SUMMARY_LIMIT="${PATH_SUMMARY_LIMIT:-8}"
MTR_BASE_DOMAIN="${MTR_BASE_DOMAIN:-google.com}"
EGRESS_BASE_MODE="${EGRESS_BASE_MODE:-auto}"
API_TIMEOUT=5
ENV_TIMEOUT=5
IP_LOOKUP_CACHE_TTL="${IP_LOOKUP_CACHE_TTL:-86400}"
UA="egress-check/${VERSION} (+${BRAND_URL})"

DEFAULT_RULES=$(cat <<'EOF'
# Built-in default rules. Format: Category | Domain | reserved | reserved | Note
AI|openai.com|||OpenAI
AI|chatgpt.com|||ChatGPT
AI|anthropic.com|||Anthropic
AI|claude.ai|||Claude
AI|gemini.google.com|||Google Gemini
AI|ai.google.dev|||Google AI Studio
AI|perplexity.ai|||Perplexity
AI|grok.com|||Grok
AI|x.ai|||xAI
AI|poe.com|||Poe
AI|copilot.microsoft.com|||Microsoft Copilot
AI|huggingface.co|||Hugging Face
Social|x.com|||X
Social|twitter.com|||Twitter legacy domain
Social|facebook.com|||Meta
Social|instagram.com|||Meta
Social|threads.net|||Meta
Social|whatsapp.com|||Meta
Social|tiktok.com|||TikTok
Social|telegram.org|||Telegram
Social|discord.com|||Discord
Social|reddit.com|||Reddit
Social|linkedin.com|||LinkedIn
Social|pinterest.com|||Pinterest
Streaming|netflix.com|||Netflix
Streaming|youtube.com|||YouTube
Streaming|disneyplus.com|||Disney+
Streaming|hulu.com|||Hulu
Streaming|primevideo.com|||Prime Video
Streaming|max.com|||Max
Streaming|spotify.com|||Spotify
Streaming|twitch.tv|||Twitch
Streaming|bilibili.com|||Bilibili
Streaming|iq.com|||iQIYI International
Streaming|crunchyroll.com|||Crunchyroll
Streaming|tv.apple.com|||Apple TV
Search|google.com|||Google Search
Search|bing.com|||Bing
Search|duckduckgo.com|||DuckDuckGo
Search|yahoo.com|||Yahoo
Search|baidu.com|||Baidu
Search|yandex.com|||Yandex
Search|brave.com|||Brave
Search|startpage.com|||Startpage
Developer|github.com|||GitHub
Developer|gitlab.com|||GitLab
Developer|npmjs.com|||npm
Developer|pypi.org|||PyPI
Developer|docker.com|||Docker
Developer|registry-1.docker.io|||Docker Registry
Developer|stackoverflow.com|||Stack Overflow
Developer|cloudflare.com|||Cloudflare
Developer|vercel.com|||Vercel
Developer|netlify.com|||Netlify
Cloud|aws.amazon.com|||AWS
Cloud|azure.microsoft.com|||Microsoft Azure
Cloud|cloud.google.com|||Google Cloud
Cloud|oraclecloud.com|||Oracle Cloud
Cloud|digitalocean.com|||DigitalOcean
Cloud|linode.com|||Linode
Cloud|vultr.com|||Vultr
Cloud|hetzner.com|||Hetzner
Crypto|binance.com|||Binance
Crypto|coinbase.com|||Coinbase
Crypto|okx.com|||OKX
Crypto|kraken.com|||Kraken
Crypto|bybit.com|||Bybit
Crypto|bitget.com|||Bitget
Crypto|coingecko.com|||CoinGecko
Crypto|etherscan.io|||Etherscan
Gaming|steampowered.com|||Steam Store
Gaming|steamcommunity.com|||Steam Community
Gaming|epicgames.com|||Epic Games
Gaming|battle.net|||Battle.net
Gaming|ea.com|||EA
Gaming|playstation.com|||PlayStation
Gaming|xbox.com|||Xbox
Gaming|nintendo.com|||Nintendo
Ecommerce|amazon.com|||Amazon
Ecommerce|ebay.com|||eBay
Ecommerce|aliexpress.com|||AliExpress
Ecommerce|taobao.com|||Taobao
Ecommerce|tmall.com|||Tmall
Ecommerce|jd.com|||JD
Ecommerce|temu.com|||Temu
Ecommerce|shein.com|||SHEIN
Ecommerce|walmart.com|||Walmart
Ecommerce|target.com|||Target
Ecommerce|etsy.com|||Etsy
Ecommerce|rakuten.co.jp|||Rakuten Japan
Ecommerce|coupang.com|||Coupang
Ecommerce|mercadolibre.com|||Mercado Libre
Ecommerce|shopee.com|||Shopee Global
Ecommerce|shopee.sg|||Shopee Singapore
Ecommerce|shopee.tw|||Shopee Taiwan
Ecommerce|shopee.co.id|||Shopee Indonesia
Ecommerce|shopee.co.th|||Shopee Thailand
Ecommerce|shopee.vn|||Shopee Vietnam
Ecommerce|shopee.com.my|||Shopee Malaysia
Ecommerce|shopee.ph|||Shopee Philippines
Ecommerce|shopee.com.br|||Shopee Brazil
Ecommerce|lazada.com|||Lazada Global
Ecommerce|lazada.sg|||Lazada Singapore
Ecommerce|lazada.co.id|||Lazada Indonesia
Ecommerce|lazada.com.my|||Lazada Malaysia
Ecommerce|lazada.co.th|||Lazada Thailand
Ecommerce|lazada.vn|||Lazada Vietnam
Ecommerce|lazada.com.ph|||Lazada Philippines
China|qq.com|||Tencent QQ
China|wechat.com|||WeChat
China|weibo.com|||Weibo
China|douyin.com|||Douyin
China|zhihu.com|||Zhihu
China|163.com|||NetEase
China|sina.com.cn|||Sina
China|aliyun.com|||Alibaba Cloud
EOF
)

usage() {
    cat <<EOF
家宽VPS分流一键自查检测 Egress-Check v${VERSION}   鸣谢：${BRAND_URL}
Usage: $(basename "$0") [options]
  (no flag)      自动: 网络环境 + IPv4 线路分流 + IPv6 线路分流
  -I, --interactive
                 交互菜单: 输入 1-6 选择检测模式
  -4, --ipv4     只跑 IPv4
  -6, --ipv6     只跑 IPv6
  --json         JSON 输出
  --no-color     关闭颜色
  --only <CAT>   只跑指定分类
  --rules <path> 自定义 rules.conf
  -h, --help     帮助
EOF
}

interactive_menu() {
    cat <<EOF

家宽VPS分流一键自查检测 Egress-Check v${VERSION}
请选择检测模式:

  1) 默认完整检测      网络环境 + IPv4 + IPv6
  2) 只检测 IPv4
  3) 只检测 IPv6
  4) 只检测指定分类    AI / Social / Streaming / Search / Developer / Cloud / Crypto / Gaming
  5) JSON 输出         适合 cron / 监控
  6) 高并发日志模式    并发 10 + 关闭颜色

EOF
    local choice cat_name
    printf "请输入 1-6 [1]: "
    IFS= read -r choice
    choice="${choice:-1}"
    case "$choice" in
        1) PASS_MODE="auto" ;;
        2) PASS_MODE="v4-only" ;;
        3) PASS_MODE="v6-only" ;;
        4)
            printf "请输入分类名 [Social]: "
            IFS= read -r cat_name
            ONLY_CAT="${cat_name:-Social}"
            PASS_MODE="auto"
            ;;
        5) OUTPUT_JSON=1 ;;
        6)
            MTR_CONCURRENCY="${MTR_CONCURRENCY:-10}"
            USE_COLOR=0
            set_colors
            ;;
        *) err "无效选择: $choice"; exit 1 ;;
    esac
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -I|--interactive) INTERACTIVE=1 ;;
        -4|--ipv4)  PASS_MODE="v4-only" ;;
        -6|--ipv6)  PASS_MODE="v6-only" ;;
        --json)     OUTPUT_JSON=1 ;;
        --no-color) USE_COLOR=0; set_colors ;;
        --only)     ONLY_CAT="${2:-}"; shift ;;
        --rules)    RULES_FILE="${2:-}"; shift ;;
        -h|--help)  usage; exit 0 ;;
        *) err "未知参数: $1"; usage >&2; exit 1 ;;
    esac
    shift
done

[[ $INTERACTIVE -eq 1 ]] && interactive_menu

if [[ $USE_COLOR -eq 1 ]]; then
    SYM_DOWN="${RED}✗${R}"; SYM_SKIP="${GRAY}⊘${R}"; SYM_STAR="${YELLOW}★${R}"
    SYM_WARN="${RED}⚠${R}"; SYM_INFO="${BLUE}ℹ${R}"
else
    SYM_DOWN="[XX]"; SYM_SKIP="[--]"; SYM_STAR="*"; SYM_WARN="[!]"; SYM_INFO="[i]"
fi

need() {
    local cmd="$1" hint="${2:-}"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        err "缺少依赖: $cmd"
        [[ -n "$hint" ]] && printf "    安装: %s\n" "$hint" >&2
        exit 1
    fi
}
ensure_runtime_deps() {
    local missing=()
    local need_mtr=0 need_jq=0
    command -v mtr >/dev/null 2>&1 || { missing+=(mtr); need_mtr=1; }
    command -v jq >/dev/null 2>&1 || { missing+=(jq); need_jq=1; }
    [[ ${#missing[@]} -eq 0 ]] && return 0

    local sudo=""
    if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
        if command -v sudo >/dev/null 2>&1; then sudo="sudo"
        else
            err "缺少依赖: ${missing[*]}, 当前非 root 且无 sudo, 无法自动安装"
            printf "    Debian/Ubuntu: apt install mtr-tiny jq\n" >&2
            printf "    Alpine: apk add mtr jq\n" >&2
            exit 1
        fi
    fi

    printf "%s[*]%s 未检测到依赖: %s, 正在自动安装...\n" "$BLUE" "$R" "${missing[*]}" >&2
    if command -v apt-get >/dev/null 2>&1; then
        $sudo apt-get update -qq >/dev/null 2>&1 || true
        local apt_pkgs=()
        [[ $need_mtr -eq 1 ]] && apt_pkgs+=(mtr-tiny)
        [[ $need_jq -eq 1 ]] && apt_pkgs+=(jq)
        $sudo apt-get install -y "${apt_pkgs[@]}" >/dev/null 2>&1 || {
            apt_pkgs=()
            [[ $need_mtr -eq 1 ]] && apt_pkgs+=(mtr)
            [[ $need_jq -eq 1 ]] && apt_pkgs+=(jq)
            $sudo apt-get install -y "${apt_pkgs[@]}" >/dev/null 2>&1 || true
        }
    elif command -v apk >/dev/null 2>&1; then
        local apk_pkgs=()
        [[ $need_mtr -eq 1 ]] && apk_pkgs+=(mtr)
        [[ $need_jq -eq 1 ]] && apk_pkgs+=(jq)
        $sudo apk add --no-cache "${apk_pkgs[@]}" >/dev/null 2>&1 || true
    elif command -v yum >/dev/null 2>&1; then
        local yum_pkgs=()
        [[ $need_mtr -eq 1 ]] && yum_pkgs+=(mtr)
        [[ $need_jq -eq 1 ]] && yum_pkgs+=(jq)
        $sudo yum install -y "${yum_pkgs[@]}" >/dev/null 2>&1 || true
    elif command -v dnf >/dev/null 2>&1; then
        local dnf_pkgs=()
        [[ $need_mtr -eq 1 ]] && dnf_pkgs+=(mtr)
        [[ $need_jq -eq 1 ]] && dnf_pkgs+=(jq)
        $sudo dnf install -y "${dnf_pkgs[@]}" >/dev/null 2>&1 || true
    elif command -v pacman >/dev/null 2>&1; then
        local pacman_pkgs=()
        [[ $need_mtr -eq 1 ]] && pacman_pkgs+=(mtr)
        [[ $need_jq -eq 1 ]] && pacman_pkgs+=(jq)
        $sudo pacman -Sy --noconfirm "${pacman_pkgs[@]}" >/dev/null 2>&1 || true
    fi

    local still_missing=()
    command -v mtr >/dev/null 2>&1 || still_missing+=(mtr)
    command -v jq >/dev/null 2>&1 || still_missing+=(jq)
    if [[ ${#still_missing[@]} -eq 0 ]]; then
        printf "%s[+]%s 依赖安装成功: %s\n" "$GREEN" "$R" "${missing[*]}" >&2
        { ${sudo} setcap cap_net_raw+ep "$(command -v mtr)" >/dev/null 2>&1 || true; }
        return 0
    fi

    err "依赖自动安装失败: ${still_missing[*]}"
    printf "    Debian/Ubuntu: apt install mtr-tiny jq\n" >&2
    printf "    Alpine: apk add mtr jq\n" >&2
    printf "    CentOS/RHEL: yum install mtr jq\n" >&2
    exit 1
}
ensure_runtime_deps
need curl    "apt install curl"
need timeout "coreutils"
need awk
need grep

USE_EMBEDDED_RULES=0
if [[ ! -f "$RULES_FILE" ]]; then
    if [[ -n "${EGRESS_RULES:-}" ]]; then
        err "规则文件不存在: $RULES_FILE"
        exit 1
    elif [[ -f "$SCRIPT_DIR/rules.conf.example" ]]; then
        RULES_FILE="$SCRIPT_DIR/rules.conf.example"
    else
        USE_EMBEDDED_RULES=1
    fi
fi
if ! install -d -m 700 "$CACHE_DIR" 2>/dev/null; then
    err "无法创建/访问 cache 目录: $CACHE_DIR"; exit 1
fi
[[ -O "$CACHE_DIR" ]] && chmod 700 "$CACHE_DIR" 2>/dev/null || true
IP_LOOKUP_CACHE_DIR="$CACHE_DIR/ip-lookup"
if ! install -d -m 700 "$IP_LOOKUP_CACHE_DIR" 2>/dev/null; then
    err "无法创建/访问 IP 反查缓存目录: $IP_LOOKUP_CACHE_DIR"; exit 1
fi
[[ -O "$IP_LOOKUP_CACHE_DIR" ]] && chmod 700 "$IP_LOOKUP_CACHE_DIR" 2>/dev/null || true

sanitize() { LC_ALL=C tr -d '\000-\037\177'; }
strip_bom() { local s="$1"; s="${s#$'\xef\xbb\xbf'}"; printf '%s' "$s"; }
is_valid_domain() { [[ "$1" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,253}[a-zA-Z0-9])?$ ]]; }
is_private_v4() {
    local ip="$1"
    [[ "$ip" =~ ^10\. ]] && return 0
    [[ "$ip" =~ ^192\.168\. ]] && return 0
    [[ "$ip" =~ ^172\.(1[6-9]|2[0-9]|3[0-1])\. ]] && return 0
    [[ "$ip" =~ ^127\. ]] && return 0
    [[ "$ip" =~ ^100\.(6[4-9]|[7-9][0-9]|1[0-1][0-9]|12[0-7])\. ]] && return 0
    [[ "$ip" =~ ^169\.254\. ]] && return 0
    [[ "$ip" =~ ^0\. ]] && return 0
    [[ "$ip" =~ ^22[4-9]\.|^2[3-5][0-9]\. ]] && return 0
    return 1
}
is_private_v6() {
    local ip="$1"
    [[ "$ip" =~ ^[Ff][Ee]80: ]] && return 0
    [[ "$ip" =~ ^[Ff][CcDd] ]] && return 0
    [[ "$ip" == "::1" ]] && return 0
    return 1
}

lookup_via_ipinfo() {
    local ip="$1" json
    json=$(curl -fsS --max-time "$API_TIMEOUT" --proto '=https' --tlsv1.2 -A "$UA" "https://ipinfo.io/${ip}/json" 2>/dev/null) || return 1
    [[ -z "$json" ]] && return 1
    local cc org
    IFS=$'\t' read -r cc org < <(printf '%s' "$json" | jq -r '[.country // "", .org // ""] | @tsv' 2>/dev/null) || return 1
    [[ -z "$cc" ]] && return 1
    local asn isp
    if [[ "$org" =~ ^AS([0-9]+)[[:space:]]+(.+)$ ]]; then asn="${BASH_REMATCH[1]}"; isp="${BASH_REMATCH[2]}"
    else asn=""; isp="$org"; fi
    printf '%s\t%s\t%s' "$(printf '%s' "$asn" | sanitize)" "$(printf '%s' "$isp" | sanitize | cut -c1-32)" "$(printf '%s' "$cc" | sanitize | cut -c1-3)"
}
lookup_via_ipsb() {
    local ip="$1" json
    json=$(curl -fsS --max-time "$API_TIMEOUT" --proto '=https' --tlsv1.2 -A "$UA" "https://api.ip.sb/geoip/${ip}" 2>/dev/null) || return 1
    [[ -z "$json" ]] && return 1
    local cc asn isp row
    row=$(printf '%s' "$json" | jq -r '[.country_code // "", (.asn // "" | tostring), .asn_organization // .organization // ""] | @tsv' 2>/dev/null) || return 1
    split_lookup_data "$row" cc asn isp
    [[ -z "$cc" || "$cc" == "null" ]] && return 1
    [[ "$asn" == "null" ]] && asn=""
    printf '%s\t%s\t%s' "$(printf '%s' "$asn" | sanitize)" "$(printf '%s' "$isp" | sanitize | cut -c1-32)" "$(printf '%s' "$cc" | sanitize | cut -c1-3)"
}
lookup_via_ipwhois() {
    local ip="$1" json
    json=$(curl -fsS --max-time "$API_TIMEOUT" --proto '=https' --tlsv1.2 -A "$UA" "https://ipwho.is/${ip}" 2>/dev/null) || return 1
    [[ -z "$json" ]] && return 1
    local ok cc asn isp row
    row=$(printf '%s' "$json" | jq -r '[(.success // false | tostring), .country_code // "", (.connection.asn // "" | tostring), .connection.isp // ""] | @tsv' 2>/dev/null) || return 1
    split_tsv4 "$row" ok cc asn isp
    [[ "$ok" != "true" ]] && return 1
    [[ -z "$cc" ]] && return 1
    [[ "$asn" == "null" ]] && asn=""
    printf '%s\t%s\t%s' "$(printf '%s' "$asn" | sanitize)" "$(printf '%s' "$isp" | sanitize | cut -c1-32)" "$(printf '%s' "$cc" | sanitize | cut -c1-3)"
}
declare -A IP_CACHE
ip_lookup_cache_path() {
    local key
    key="$(printf '%s' "$1" | sed 's/[^A-Za-z0-9_.-]/_/g')"
    printf '%s/%s.tsv' "$IP_LOOKUP_CACHE_DIR" "$key"
}
split_lookup_data() {
    local data="$1" asn_var="$2" isp_var="$3" cc_var="$4" rest part_asn part_isp part_cc
    rest="$data"
    if [[ "$rest" == *$'\t'* ]]; then
        part_asn="${rest%%$'\t'*}"
        rest="${rest#*$'\t'}"
    else
        part_asn="$rest"
        rest=""
    fi
    if [[ "$rest" == *$'\t'* ]]; then
        part_isp="${rest%%$'\t'*}"
        part_cc="${rest#*$'\t'}"
    else
        part_isp="$rest"
        part_cc=""
    fi
    printf -v "$asn_var" '%s' "$part_asn"
    printf -v "$isp_var" '%s' "$part_isp"
    printf -v "$cc_var" '%s' "$part_cc"
}
split_tsv4() {
    local data="$1" var1="$2" var2="$3" var3="$4" var4="$5" rest f1 f2 f3 f4
    rest="$data"
    if [[ "$rest" == *$'\t'* ]]; then f1="${rest%%$'\t'*}"; rest="${rest#*$'\t'}"; else f1="$rest"; rest=""; fi
    if [[ "$rest" == *$'\t'* ]]; then f2="${rest%%$'\t'*}"; rest="${rest#*$'\t'}"; else f2="$rest"; rest=""; fi
    if [[ "$rest" == *$'\t'* ]]; then f3="${rest%%$'\t'*}"; f4="${rest#*$'\t'}"; else f3="$rest"; f4=""; fi
    printf -v "$var1" '%s' "$f1"
    printf -v "$var2" '%s' "$f2"
    printf -v "$var3" '%s' "$f3"
    printf -v "$var4" '%s' "$f4"
}
lookup_score() {
    local data="$1" asn isp cc score=0
    split_lookup_data "$data" asn isp cc
    [[ -n "$cc" && "$cc" != "??" && "$cc" != "null" ]] && score=$((score+1))
    [[ -n "$asn" && "$asn" != "??" && "$asn" != "null" ]] && score=$((score+1))
    [[ -n "$isp" && "$isp" != "Unknown" && "$isp" != "null" ]] && score=$((score+1))
    printf '%s' "$score"
}
normalize_lookup_fields() {
    local asn_var="$1" isp_var="$2" cc_var="$3" asn_val isp_val cc_val
    asn_val="${!asn_var:-}"
    isp_val="${!isp_var:-}"
    cc_val="${!cc_var:-}"
    [[ "$asn_val" == "??" || "$asn_val" == "null" ]] && asn_val=""
    [[ "$isp_val" == "null" ]] && isp_val=""
    [[ "$cc_val" == "null" ]] && cc_val=""
    printf -v "$asn_var" '%s' "$asn_val"
    printf -v "$isp_var" '%s' "$isp_val"
    printf -v "$cc_var" '%s' "$cc_val"
}
read_ip_lookup_cache() {
    local ip="$1" path mtime now line
    path="$(ip_lookup_cache_path "$ip")"
    [[ -f "$path" ]] || return 1
    if mtime="$(stat -c %Y "$path" 2>/dev/null)"; then
        now="$(date +%s)"
        [[ "$mtime" =~ ^[0-9]+$ ]] && (( now - mtime > IP_LOOKUP_CACHE_TTL )) && return 1
    fi
    IFS= read -r line < "$path" || return 1
    [[ "$(lookup_score "$line")" -ge 3 ]] || return 1
    printf '%s' "$line"
}
write_ip_lookup_cache() {
    local ip="$1" result="$2" path tmp
    [[ "$(lookup_score "$result")" -ge 3 ]] || return 0
    path="$(ip_lookup_cache_path "$ip")"
    tmp="${path}.$$"
    printf '%s\n' "$result" > "$tmp" 2>/dev/null || return 0
    chmod 600 "$tmp" 2>/dev/null || true
    mv -f -- "$tmp" "$path" 2>/dev/null || rm -f -- "$tmp" 2>/dev/null || true
}
lookup_ip() {
    local ip="$1" result best_result="" score best_score=0 provider
    if [[ -n "${IP_CACHE[$ip]+set}" ]]; then printf '%s' "${IP_CACHE[$ip]}"; return 0; fi
    if result="$(read_ip_lookup_cache "$ip" 2>/dev/null)"; then
        IP_CACHE[$ip]="$result"; printf '%s' "$result"; return 0
    fi
    for provider in ipinfo ipsb ipwhois; do
        if result=$("lookup_via_${provider}" "$ip" 2>/dev/null); then
            score="$(lookup_score "$result")"
            if (( score > best_score )); then
                best_score="$score"
                best_result="$result"
            fi
            (( score >= 3 )) && break
        fi
    done
    if [[ -n "$best_result" ]]; then
        IP_CACHE[$ip]="$best_result"
        write_ip_lookup_cache "$ip" "$best_result"
        printf '%s' "$best_result"
        return 0
    fi
    IP_CACHE[$ip]=$'\t\t??'; printf '%s' "${IP_CACHE[$ip]}"; return 1
}

ENV_ENDPOINTS=(
    "https://api.ip.sb/ip" "https://ipinfo.io/ip" "https://icanhazip.com"
    "https://ifconfig.me/ip" "https://api.ipify.org" "https://checkip.amazonaws.com"
)
detect_default_egress_ip() {
    local ep ip
    for ep in "${ENV_ENDPOINTS[@]}"; do
        ip=$(curl -fsS --max-time "$ENV_TIMEOUT" --proto '=https' --tlsv1.2 -A "$UA" "$ep" 2>/dev/null | tr -d '[:space:]' || true)
        [[ -n "$ip" ]] && { printf '%s' "$ip"; return 0; }
    done
    return 1
}
detect_all_v4_egress_ips() {
    local ep ip
    for ep in "${ENV_ENDPOINTS[@]}"; do
        ip=$(curl -fsS -4 --max-time "$ENV_TIMEOUT" --proto '=https' --tlsv1.2 -A "$UA" "$ep" 2>/dev/null | tr -d '[:space:]' || true)
        [[ -n "$ip" && "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] && printf '%s|%s\n' "$ip" "$ep"
    done
}
detect_all_v6_egress_ips() {
    local ep ip
    for ep in "${ENV_ENDPOINTS[@]}"; do
        ip=$(curl -fsS -6 --max-time "$ENV_TIMEOUT" --proto '=https' --tlsv1.2 -A "$UA" "$ep" 2>/dev/null | tr -d '[:space:]' || true)
        [[ -n "$ip" && "$ip" == *:* ]] && printf '%s|%s\n' "$ip" "$ep"
    done
}
ip_family() {
    local ip="$1"
    if [[ "$ip" == *:* ]]; then printf 'ipv6'
    elif [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then printf 'ipv4'
    else printf 'unknown'; fi
}

first_public_hop() {
    local ip_flag="$1" domain="$2" output attempt parsed ip latency path_ips mode cmd_text
    is_valid_domain "$domain" || { printf ''; return; }
    for ((attempt=1; attempt<=MTR_ATTEMPTS; attempt++)); do
        for mode in numeric names; do
            if [[ "$mode" == "numeric" ]]; then
                cmd_text="mtr $ip_flag -r -n -c $MTR_COUNT -m $MTR_MAXTTL $domain"
                output=$(timeout "$MTR_TIMEOUT" mtr "$ip_flag" -r -n -c "$MTR_COUNT" -m "$MTR_MAXTTL" "$domain" 2>/dev/null || true)
            else
                cmd_text="mtr $ip_flag -r -c $MTR_COUNT -m $MTR_MAXTTL $domain"
                output=$(timeout "$MTR_TIMEOUT" mtr "$ip_flag" -r -c "$MTR_COUNT" -m "$MTR_MAXTTL" "$domain" 2>/dev/null || true)
            fi
            if [[ "${EGRESS_DEBUG_MTR:-0}" == "1" ]]; then
                local dbg_dir dbg_file safe_domain
                dbg_dir="$CACHE_DIR/mtr-debug"
                install -d -m 700 "$dbg_dir" 2>/dev/null || true
                safe_domain="$(printf '%s' "$domain" | sed 's/[^A-Za-z0-9_.-]/_/g')"
                dbg_file="$dbg_dir/${ip_flag#-}-${safe_domain}-${mode}.txt"
                {
                    printf 'command: %s\nattempt: %s\n--- output ---\n' "$cmd_text" "$attempt"
                    printf '%s\n' "$output"
                } > "$dbg_file" 2>/dev/null || true
            fi
            if [[ -z "$output" ]]; then
                continue
            fi
            if [[ "$ip_flag" == "-6" ]]; then
            parsed=$(printf '%s\n' "$output" | awk '
                function private_v6(ip) { return (ip ~ /^[Ff][Ee]80:/ || ip ~ /^[Ff][CcDd]/ || ip == "::1") }
                function valid_avg(v) { return (v ~ /^[0-9]+([.][0-9]+)?$/) }
                {
                    line=$0
                    gsub(/\r/, "", line)
                    gsub(/\033\[[0-9;?]*[ -\/]*[@-~]/, "", line)
                    if (line !~ /[0-9]+([.][0-9]+)?%/) next
                    $0=line
                    row_avg="-"
                    found_ip=0
                    for (i=1; i<=NF; i++) {
                        ip=$i
                        gsub(/^[^0-9a-fA-F:.]+/, "", ip)
                        gsub(/[^0-9a-fA-F:.]+$/, "", ip)
                        if (ip ~ /^([0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F:]+$/) {
                            avg=$(i+4)
                            if (!private_v6(ip)) {
                                if (first_hop == "") first_hop=ip
                                if (ip != last_public_ip) {
                                    path_ips = (path_ips == "" ? ip : path_ips " " ip)
                                    last_public_ip = ip
                                }
                            }
                            if (valid_avg(avg)) row_avg=avg
                            found_ip=1
                            break
                        }
                    }
                    if (found_ip) target_avg=row_avg
                }
                END {
                    if (first_hop != "") {
                        if (target_avg == "") target_avg="-"
                        print first_hop "\t" target_avg "\t" path_ips
                    }
                }')
            else
            parsed=$(printf '%s\n' "$output" | awk '
                function private_v4(ip) { return (ip ~ /^10\./ || ip ~ /^192\.168\./ || ip ~ /^172\.(1[6-9]|2[0-9]|3[0-1])\./ || ip ~ /^127\./ || ip ~ /^100\.(6[4-9]|[7-9][0-9]|1[0-1][0-9]|12[0-7])\./ || ip ~ /^169\.254\./ || ip ~ /^0\./ || ip ~ /^22[4-9]\./ || ip ~ /^2[3-5][0-9]\./) }
                function valid_avg(v) { return (v ~ /^[0-9]+([.][0-9]+)?$/) }
                {
                    line=$0
                    gsub(/\r/, "", line)
                    gsub(/\033\[[0-9;?]*[ -\/]*[@-~]/, "", line)
                    if (line !~ /[0-9]+([.][0-9]+)?%/) next
                    $0=line
                    row_avg="-"
                    found_ip=0
                    for (i=1; i<=NF; i++) {
                        ip=$i
                        gsub(/^[^0-9.]+/, "", ip)
                        gsub(/[^0-9.]+$/, "", ip)
                        if (ip ~ /^([0-9]{1,3}\.){3}[0-9]{1,3}$/) {
                            avg=$(i+4)
                            if (!private_v4(ip)) {
                                if (first_hop == "") first_hop=ip
                                if (ip != last_public_ip) {
                                    path_ips = (path_ips == "" ? ip : path_ips " " ip)
                                    last_public_ip = ip
                                }
                            }
                            if (valid_avg(avg)) row_avg=avg
                            found_ip=1
                            break
                        }
                    }
                    if (found_ip) target_avg=row_avg
                }
                END {
                    if (first_hop != "") {
                        if (target_avg == "") target_avg="-"
                        print first_hop "\t" target_avg "\t" path_ips
                    }
                }')
            fi
            if [[ -n "$parsed" ]]; then
                IFS=$'\t' read -r ip latency path_ips <<< "$parsed"
                [[ -n "$ip" ]] && { printf '%s\t%s\t%s' "$ip" "${latency:-"-"}" "$path_ips"; return; }
            fi
        done
        sleep "$attempt"
    done
}

detect_mtr_base_asn() {
    local ip_flag="$1" prefix="$2" hop_line hop latency path_ips data asn isp country info
    hop_line="$(first_public_hop "$ip_flag" "$MTR_BASE_DOMAIN" || true)"
    IFS=$'\t' read -r hop latency path_ips <<< "$hop_line"
    [[ -n "$hop" ]] || return 1
    data="$(lookup_ip "$hop" || true)"
    split_lookup_data "$data" asn isp country
    normalize_lookup_fields asn isp country
    [[ -n "$asn" ]] || return 1
    [[ -z "$country" ]] && country="??"
    [[ -z "$isp" ]] && isp="Unknown"
    info="$country · AS$asn $isp"
    printf -v "${prefix}_MTR_BASE_ASN" '%s' "$asn"
    printf -v "${prefix}_MTR_BASE_HOP" '%s' "$hop"
    printf -v "${prefix}_MTR_BASE_INFO" '%s' "$info"
}

declare -a CATS DOMAINS NOTES
parse_rules() {
local line source="$1"
LINENO_RULE=0; FIRST_LINE=1
while IFS= read -r line || [[ -n "$line" ]]; do
    LINENO_RULE=$((LINENO_RULE+1))
    if [[ $FIRST_LINE -eq 1 ]]; then line="$(strip_bom "$line")"; FIRST_LINE=0; fi
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    IFS='|' read -r f1 f2 f3 f4 f5 <<< "$line"
    cat_v="$(printf '%s' "${f1:-}" | sanitize | awk '{$1=$1;print}')"
    domain="$(printf '%s' "${f2:-}" | sanitize | awk '{$1=$1;print}')"
    note="$(printf '%s' "${f5:-}" | sanitize | awk '{$1=$1;print}')"
    [[ -z "$domain" ]] && continue
    if ! is_valid_domain "$domain"; then err "rules.conf:$LINENO_RULE 跳过非法域名: $domain"; continue; fi
    [[ -n "$ONLY_CAT" && "$cat_v" != "$ONLY_CAT" ]] && continue
    cat_v="${cat_v:0:16}"; note="${note:0:80}"
    CATS+=("$cat_v"); DOMAINS+=("$domain"); NOTES+=("$note")
done < "$source"
}
if [[ $USE_EMBEDDED_RULES -eq 1 ]]; then
    parse_rules <(printf '%s\n' "$DEFAULT_RULES")
else
    parse_rules "$RULES_FILE"
fi
TOTAL=${#DOMAINS[@]}
[[ $TOTAL -eq 0 ]] && { err "规则中没有可用域名 (或 --only 过滤后为空)"; exit 1; }

TMP_V4_RESULTS=""; TMP_V6_RESULTS=""; FINAL_JSON=""
cleanup_tmp() {
    [[ -n "$TMP_V4_RESULTS" ]] && rm -f -- "$TMP_V4_RESULTS"
    [[ -n "$TMP_V6_RESULTS" ]] && rm -f -- "$TMP_V6_RESULTS"
    [[ -n "$FINAL_JSON" ]] && rm -f -- "$FINAL_JSON"
    rm -rf "$CACHE_DIR"/.mtrout.* 2>/dev/null || true
}
trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP; trap cleanup_tmp EXIT

is_tty() { [[ -t 1 && $USE_COLOR -eq 1 ]]; }
repeat_char() { local c="$1" w="$2" r; printf -v r "%${w}s" ""; printf '%s' "${r// /$c}"; }
rule_double() { printf "%s%s%s\n" "$CYAN" "$(repeat_char "━" "${1:-72}")" "$R"; }
rule_single() { printf "%s%s%s" "$GRAY" "$(repeat_char "─" "${1:-60}")" "$R"; }
print_banner() {
    rule_double 72
    printf "  %s家宽VPS分流一键自查检测%s  %sEgress-Check v%s%s     %s鸣谢：%s%s\n" "$BOLD" "$R" "$CYAN" "$VERSION" "$R" "$GRAY" "$BRAND_URL" "$R"
    printf "  %shost%s: %s%s%s     %s%s%s\n" "$DIM" "$R" "$BOLD" "$1" "$R" "$GRAY" "$2" "$R"
    rule_double 72
}
print_env_section() {
    local def="$1" v4="$2" v6="$3" v4info="$4" v6info="$5"
    printf "\n  %s网络环境 (真实对外 IP)%s\n" "$BOLD" "$R"
    printf "  %s\n" "$(rule_single 36)"
    case "$def" in
        ipv4) printf "    默认出口     %sIPv4%s  %s\n" "$GREEN" "$R" "$SYM_STAR" ;;
        ipv6) printf "    默认出口     %sIPv6%s  %s\n" "$GREEN" "$R" "$SYM_STAR" ;;
        *)    printf "    默认出口     %s无网络出口%s\n" "$RED" "$R" ;;
    esac
    if [[ -n "$v4" ]]; then printf "    IPv4 出口    %s%s%s  %s%s%s\n" "$BOLD" "$v4" "$R" "$DIM" "$v4info" "$R"
    else printf "    IPv4 出口    %s不可用%s\n" "$RED" "$R"; fi
    if [[ -n "${V4_MTR_BASE_ASN:-}" ]]; then
        printf "    IPv4 MTR     %s%s%s  %s%s%s\n" "$BOLD" "$V4_MTR_BASE_HOP" "$R" "$DIM" "$V4_MTR_BASE_INFO" "$R"
    fi
    if [[ -n "$v6" ]]; then printf "    IPv6 出口    %s%s%s  %s%s%s\n" "$BOLD" "$v6" "$R" "$DIM" "$v6info" "$R"
    else printf "    IPv6 出口    %s不可用 / 已禁用%s\n" "$YELLOW" "$R"; fi
    if [[ -n "${V6_MTR_BASE_ASN:-}" ]]; then
        printf "    IPv6 MTR     %s%s%s  %s%s%s\n" "$BOLD" "$V6_MTR_BASE_HOP" "$R" "$DIM" "$V6_MTR_BASE_INFO" "$R"
    fi
    local item
    if [[ -n "$v4" && $V4_ECHO_UNIQUE -gt 1 ]]; then
        printf "\n    %s%s 商家 SNAT 嫌疑%s — %s%d 个回声服务看到不同对外 IP%s\n" "$RED" "$SYM_WARN" "$R" "$DIM" "$V4_ECHO_UNIQUE" "$R"
        local IFS_save="$IFS"; IFS=';'
        for item in $V4_ECHO_DETAIL; do item="${item# }"; printf "      %s· %s%s\n" "$DIM" "$item" "$R"; done
        IFS="$IFS_save"
    fi
}
print_pass_header() {
    [[ $OUTPUT_JSON -eq 1 ]] && return 0
    printf "\n  %s%s 线路分流检测%s  %s%s%s\n" "$BOLD" "$1" "$R" "$GRAY" "$(repeat_char "─" 44)" "$R"
}
print_category_header() {
    [[ $OUTPUT_JSON -eq 1 ]] && return 0
    printf "\n    %s%s%s\n" "$BOLD" "$1" "$R"
}
latency_color() {
    local latency="${1:-"-"}"
    if [[ "$latency" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
        if awk -v v="$latency" 'BEGIN { exit !(v < 50) }'; then printf '%s' "$GREEN"
        elif awk -v v="$latency" 'BEGIN { exit !(v < 200) }'; then printf '%s' "$YELLOW"
        else printf '%s' "$BROWN"; fi
    else
        printf '%s' "$GRAY"
    fi
}

format_latency_text() {
    local latency="${1:-"-"}"
    if [[ "$latency" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
        if awk -v v="$latency" 'BEGIN { exit !(v >= 1000) }'; then
            printf '%9s' "999+ms"
        else
            printf '%7.1fms' "$latency"
        fi
    else
        printf '%9s' "-"
    fi
}

format_latency() {
    local latency="${1:-"-"}" text color
    text="$(format_latency_text "$latency")"
    color="$(latency_color "$latency")"
    printf '%s%s%s' "$color" "$text" "$R"
}

short_text() {
    local text="$1" width="${2:-58}"
    if (( ${#text} > width )); then
        printf '%s...' "${text:0:$((width-3))}"
    else
        printf '%s' "$text"
    fi
}

path_asn_chain() {
    local path_ips="$1" ip data asn isp country prev_asn="" label chain=""
    for ip in $path_ips; do
        data="$(lookup_ip "$ip" || true)"
        split_lookup_data "$data" asn isp country
        normalize_lookup_fields asn isp country
        [[ -z "$asn" ]] && continue
        [[ "$asn" == "$prev_asn" ]] && continue
        prev_asn="$asn"
        label="AS$asn"
        if [[ -n "$isp" && "$isp" != "Unknown" ]]; then
            label+=" $(short_text "$isp" 22)"
        fi
        if [[ -z "$chain" ]]; then chain="$label"; else chain+=" -> $label"; fi
    done
    printf '%s' "$chain"
}

print_result_row() {
    [[ $OUTPUT_JSON -eq 1 ]] && return 0
    local marker="$1" domain="$2" ip="$3" latency="$4" cc="$5" asn="$6" isp="$7" is_split="${8:-0}" asn_isp latency_disp
    [[ "$asn" == "??" || "$asn" == "null" ]] && asn=""
    [[ "$isp" == "null" ]] && isp="Unknown"
    if [[ -z "$asn" ]]; then asn_isp="$isp"; else asn_isp="AS${asn} ${isp}"; fi
    if [[ "$is_split" == "1" ]]; then
        latency_disp="$(printf '%s%s%s' "$YELLOW" "$(format_latency_text "$latency")" "$R")"
        printf "      %b  %s%-24s  %-15s  %b  %s%-3s  %-34s  ⮜ 分流%s\n" "$marker" "$YELLOW" "$domain" "$ip" "$latency_disp" "$YELLOW" "$cc" "${asn_isp:0:34}" "$R"
    else
        latency_disp="$(format_latency "$latency")"
        printf "      %b  %-24s  %-15s  %b  %-3s  %s%s%s\n" "$marker" "$domain" "$ip" "$latency_disp" "$cc" "$DIM" "${asn_isp:0:34}" "$R"
    fi
}
format_elapsed() {
    local s="$1"
    if (( s < 60 )); then printf '%ds' "$s"
    elif (( s < 3600 )); then printf '%dm %ds' $((s/60)) $((s%60))
    else printf '%dh %dm' $((s/3600)) $(((s%3600)/60)); fi
}

run_mtr_group() {
    local ip_flag="$1" out_dir="$2" cat="$3"; shift 3
    local -a idxs=("$@")
    local total=${#idxs[@]} maxjobs="${MTR_CONCURRENCY:-6}" running=0 idx spin_pid=""
    local -a mtr_pids=()
    if [[ $OUTPUT_JSON -eq 0 ]] && is_tty; then
        ( k=0
          while :; do
              cnt=0; for ix in "${idxs[@]}"; do [[ -f "$out_dir/$ix" ]] && cnt=$((cnt+1)); done
              k=$(( (k % 5) + 1 )); d=$(printf '%*s' "$k" '' | tr ' ' '.')
              printf "\r    %s检测中%s %s%s 组%s%-6s %s(%s/%s)%s" "$CYAN" "$R" "$BOLD" "$cat" "$R" "$d" "$DIM" "$cnt" "$total" "$R"
              sleep 0.3
          done ) &
        spin_pid=$!
    fi
    for idx in "${idxs[@]}"; do
        {
            local hop; hop="$(first_public_hop "$ip_flag" "${DOMAINS[$idx]}")"
            printf '%s' "$hop" > "$out_dir/$idx"
        } &
        mtr_pids+=($!)
        running=$((running+1))
        sleep 0.1
        if (( running >= maxjobs )); then wait -n 2>/dev/null || true; running=$((running-1)); fi
    done
    wait "${mtr_pids[@]}" 2>/dev/null || true
    if [[ -n "$spin_pid" ]]; then kill "$spin_pid" 2>/dev/null || true; wait "$spin_pid" 2>/dev/null || true; printf "\r\033[K"; fi
}

run_check_pass() {
    local label="$1" ip_flag="$2" tmp_file="$3" prefix base_asn mtr_base_asn effective_base_asn base_desc topology_note
    case "$label" in
        IPv4) prefix=V4; base_asn="${V4_BASE_ASN:-}"; mtr_base_asn="${V4_MTR_BASE_ASN:-}" ;;
        IPv6) prefix=V6; base_asn="${V6_BASE_ASN:-}"; mtr_base_asn="${V6_MTR_BASE_ASN:-}" ;;
    esac
    effective_base_asn="$base_asn"
    base_desc="默认出口 ${base_asn:+AS$base_asn}"
    case "$EGRESS_BASE_MODE" in
        echo) ;;
        mtr)
            if [[ -n "$mtr_base_asn" ]]; then
                effective_base_asn="$mtr_base_asn"
                base_desc="MTR主路径 AS$mtr_base_asn"
            fi
            ;;
        auto|*)
            if [[ -n "$base_asn" && -n "$mtr_base_asn" && "$base_asn" != "$mtr_base_asn" ]]; then
                effective_base_asn="$mtr_base_asn"
                base_desc="MTR主路径 AS$mtr_base_asn"
                topology_note="检测到 NAT/隧道拓扑: HTTP出口 AS$base_asn, MTR主路径 AS$mtr_base_asn; 本轮按 MTR主路径判断分流"
            fi
            ;;
    esac
    eval "${prefix}_OK=0"; eval "${prefix}_DOWN=0"
    local SPLIT_COLORS=( "$YELLOW" "$MAGENTA" "$RED" "$CYAN" )
    local split_color_n=4
    print_pass_header "$label"
    if [[ $OUTPUT_JSON -eq 0 && -n "${topology_note:-}" ]]; then
        printf "    %s %s%s%s\n" "$SYM_INFO" "$CYAN" "$topology_note" "$R"
        printf "      %sHTTP出口仍用于展示真实对外 IP；MTR 用于比较不同域名的路由路径%s\n" "$DIM" "$R"
    fi
    local out_dir; out_dir="$(mktemp -d "$CACHE_DIR/.mtrout.XXXXXX")"
    local -A cat_idxs=(); local -a cat_order=()
    local gi
    for gi in "${!DOMAINS[@]}"; do
        local gc="${CATS[$gi]}"
        if [[ -z "${cat_idxs[$gc]+x}" ]]; then cat_order+=("$gc"); cat_idxs[$gc]=""; fi
        cat_idxs[$gc]+="$gi "
    done
    printf '[\n' > "$tmp_file"
    local first_json=1
    local -A route_isp=() route_cc=() route_domains=() route_split=() route_scidx=() hop_lookup=()
    local -A path_domains=() path_counts=()
    local -a path_order=()
    local split_idx=0 split_domain_count=0
    local cat
    for cat in "${cat_order[@]}"; do
        print_category_header "$cat"
        local -a gidxs=(${cat_idxs[$cat]})
        run_mtr_group "$ip_flag" "$out_dir" "$cat" "${gidxs[@]}"
        local idx
        for idx in "${gidxs[@]}"; do
        local cat_v="$cat" domain="${DOMAINS[$idx]}" note="${NOTES[$idx]}"
        local hop_line hop latency path_ips
        hop_line="$(cat "$out_dir/$idx" 2>/dev/null || true)"
        IFS=$'\t' read -r hop latency path_ips <<< "$hop_line"
        latency="${latency:-"-"}"
        if [[ -z "$hop" ]]; then
            eval "${prefix}_DOWN=\$((${prefix}_DOWN+1))"
            [[ $OUTPUT_JSON -eq 0 ]] && print_result_row "$SYM_DOWN" "$domain" "-" "-" "-" "" "探测失败 / 无公网跳" 0
            [[ $first_json -eq 0 ]] && printf ',\n' >> "$tmp_file"; first_json=0
            jq -n --arg c "$cat_v" --arg d "$domain" --arg note "$note" \
                '{category:$c, domain:$d, status:"down", first_hop:null, latency_ms:null, path_asn_chain:null, asn:null, isp:null, country:null, split:null, note:$note}' >> "$tmp_file"
            continue
        fi
        local data asn isp country
        if [[ -n "${hop_lookup[$hop]+set}" ]]; then
            data="${hop_lookup[$hop]}"
        else
            data="$(lookup_ip "$hop" || true)"
        fi
        split_lookup_data "$data" asn isp country
        normalize_lookup_fields asn isp country
        [[ -z "$country" ]] && country="??"; [[ -z "$isp" ]] && isp="Unknown"
        data="$(printf '%s\t%s\t%s' "$asn" "$isp" "$country")"
        [[ -z "${hop_lookup[$hop]+set}" && "$(lookup_score "$data")" -ge 3 ]] && hop_lookup[$hop]="$data"
        eval "${prefix}_OK=\$((${prefix}_OK+1))"
        local is_split=0
        [[ -n "$effective_base_asn" && -n "$asn" && "$asn" != "$effective_base_asn" ]] && is_split=1
        local key="$asn"; [[ -z "$key" ]] && key="ip:$hop"
        if [[ -z "${route_split[$key]+x}" ]]; then
            route_isp[$key]="$isp"; route_cc[$key]="$country"
            route_domains[$key]="$domain"; route_split[$key]="$is_split"
            if [[ $is_split -eq 1 ]]; then route_scidx[$key]=$split_idx; split_idx=$((split_idx+1)); else route_scidx[$key]=-1; fi
        else route_domains[$key]+=" $domain"; fi
        [[ $is_split -eq 1 ]] && split_domain_count=$((split_domain_count+1))
        local path_chain path_asn_ips
        path_asn_ips="$path_ips"
        [[ "$path_asn_ips" == *" "* ]] && path_asn_ips="${path_asn_ips% *}"
        path_chain="$(path_asn_chain "$path_asn_ips")"
        if [[ -n "$path_chain" ]]; then
            if [[ -z "${path_counts[$path_chain]+x}" ]]; then
                path_order+=("$path_chain")
                path_counts[$path_chain]=0
                path_domains[$path_chain]=""
            fi
            path_counts[$path_chain]=$((path_counts[$path_chain]+1))
            path_domains[$path_chain]+="$domain "
        fi
        local marker
        if [[ $is_split -eq 1 ]]; then marker="${SPLIT_COLORS[${route_scidx[$key]} % split_color_n]}●${R}"; else marker="${GREEN}●${R}"; fi
        [[ $OUTPUT_JSON -eq 0 ]] && print_result_row "$marker" "$domain" "$hop" "$latency" "$country" "$asn" "$isp" "$is_split"
        [[ $first_json -eq 0 ]] && printf ',\n' >> "$tmp_file"; first_json=0
        local split_json="false"; [[ $is_split -eq 1 ]] && split_json="true"
        local latency_json="null"; [[ "$latency" =~ ^[0-9]+([.][0-9]+)?$ ]] && latency_json="$latency"
        if [[ -z "$asn" ]]; then
            jq -n --arg c "$cat_v" --arg d "$domain" --arg h "$hop" --argjson lat "$latency_json" --arg chain "$path_chain" --arg isp "$isp" --arg cc "$country" --argjson sp "$split_json" --arg note "$note" \
                '{category:$c, domain:$d, status:"ok", first_hop:$h, latency_ms:$lat, path_asn_chain:($chain | if . == "" then null else . end), asn:null, isp:$isp, country:$cc, split:$sp, note:$note}' >> "$tmp_file"
        else
            jq -n --arg c "$cat_v" --arg d "$domain" --arg h "$hop" --argjson lat "$latency_json" --arg chain "$path_chain" --arg asn "$asn" --arg isp "$isp" --arg cc "$country" --argjson sp "$split_json" --arg note "$note" \
                '{category:$c, domain:$d, status:"ok", first_hop:$h, latency_ms:$lat, path_asn_chain:($chain | if . == "" then null else . end), asn:("AS"+$asn), isp:$isp, country:$cc, split:$sp, note:$note}' >> "$tmp_file"
        fi
        done
    done
    printf '\n]\n' >> "$tmp_file"
    rm -rf "$out_dir" 2>/dev/null || true
    local route_count=${#route_split[@]}
    eval "${prefix}_ROUTE_COUNT=$route_count"
    eval "${prefix}_SPLIT_DOMAINS=$split_domain_count"
    if [[ $OUTPUT_JSON -eq 0 && $route_count -gt 0 ]]; then
        printf "\n  %s\n" "$(rule_single 72)"
        printf "  %s%s 线路分流汇总%s  %s(基准 = %s)%s\n" "$BOLD" "$label" "$R" "$DIM" "$base_desc" "$R"
        printf "  %s\n" "$(rule_single 72)"
        local key round
        for round in base split; do
            for key in "${!route_split[@]}"; do
                if [[ "$round" == "base" ]]; then [[ "${route_split[$key]}" == "0" ]] || continue
                else [[ "${route_split[$key]}" == "1" ]] || continue; fi
                local dlist="${route_domains[$key]}"
                local dcount; dcount=$(printf '%s\n' $dlist | wc -l | tr -d ' ')
                local asn_disp="$key"
                [[ "$key" == ip:* ]] && asn_disp="${key#ip:}" || asn_disp="AS$key"
                local marker tag tagcol
                if [[ "${route_split[$key]}" == "1" ]]; then
                    marker="${SPLIT_COLORS[${route_scidx[$key]} % split_color_n]}●${R}"; tag="⚠ 存在分流"; tagcol="$YELLOW"
                else
                    marker="${GREEN}●${R}"; tag="✓ 符合预期 (未分流)"; tagcol="$GREEN"
                fi
                printf "    %b  %s%-26s%s %s(%s · %s)%s  %s%d 域名%s  %s%s%s\n" \
                    "$marker" "$BOLD" "${route_isp[$key]}" "$R" "$DIM" "$asn_disp" "${route_cc[$key]}" "$R" "$BOLD" "$dcount" "$R" "$tagcol" "$tag" "$R"
                local linecol="$DIM"; [[ "${route_split[$key]}" == "1" ]] && linecol="$YELLOW"
                local d cnt=0 lineout="      "
                for d in $dlist; do
                    lineout+="$d  "; cnt=$((cnt+1))
                    if [[ $cnt -eq 4 ]]; then printf "%s%s%s\n" "$linecol" "$lineout" "$R"; lineout="      "; cnt=0; fi
                done
                [[ $cnt -gt 0 ]] && printf "%s%s%s\n" "$linecol" "$lineout" "$R"
                printf "\n"
            done
        done
        if [[ $split_idx -ge 1 ]]; then
            printf "  %s%s %s检测到分流: %d 条非默认线路, %d 个域名被分流到其他出口%s\n" "$BOLD" "$SYM_WARN" "$YELLOW" "$split_idx" "$split_domain_count" "$R"
        else
            printf "  %s%s %s所有域名走同一出口 (AS%s) — 未检测到分流%s\n" "$BOLD" "$SYM_INFO" "$GREEN" "${effective_base_asn:-?}" "$R"
        fi

        if [[ ${#path_order[@]} -gt 0 ]]; then
            local max_paths="$PATH_SUMMARY_LIMIT"
            [[ "$max_paths" =~ ^[0-9]+$ ]] || max_paths=8
            (( max_paths < 1 )) && max_paths=1
            printf "\n  %s%s 路径 ASN 摘要%s  %s(辅助观察, 不直接等同分流)%s\n" "$BOLD" "$label" "$R" "$DIM" "$R"
            printf "  %s\n" "$(rule_single 72)"
            local chain shown=0
            for chain in "${path_order[@]}"; do
                (( shown >= max_paths )) && break
                shown=$((shown+1))
                local chain_disp dlist d cnt=0 lineout="      "
                chain_disp="$(short_text "$chain" 58)"
                dlist="${path_domains[$chain]}"
                printf "    %s%-58s%s  %s%2d 域名%s\n" "$CYAN" "$chain_disp" "$R" "$BOLD" "${path_counts[$chain]}" "$R"
                for d in $dlist; do
                    lineout+="$d  "; cnt=$((cnt+1))
                    if [[ $cnt -eq 4 ]]; then printf "%s%s%s\n" "$DIM" "$lineout" "$R"; lineout="      "; cnt=0; fi
                done
                [[ $cnt -gt 0 ]] && printf "%s%s%s\n" "$DIM" "$lineout" "$R"
            done
            if (( ${#path_order[@]} > shown )); then
                printf "      %s另有 %d 条路径模式未展开，可设置 PATH_SUMMARY_LIMIT 调整显示数量%s\n" "$DIM" "$((${#path_order[@]}-shown))" "$R"
            fi
        fi
    fi
}

START_EPOCH=$(date +%s)
START_TS="$(date -Iseconds 2>/dev/null || date '+%Y-%m-%dT%H:%M:%S%z')"
_raw_host="$(hostname 2>/dev/null || printf 'unknown')"
HOST_NAME="$(printf '%s' "$_raw_host" | LC_ALL=C tr -d '\000-\037\177')"; unset _raw_host
V4_OK=0; V4_DOWN=0; V4_ROUTE_COUNT=0; V6_OK=0; V6_DOWN=0; V6_ROUTE_COUNT=0
V4_PASS_RAN=0; V6_PASS_RAN=0; V4_ECHO_UNIQUE=0; V6_ECHO_UNIQUE=0
V4_ECHO_DETAIL=""; V6_ECHO_DETAIL=""; DEFAULT_EGRESS="none"
V4_IP=""; V6_IP=""; V4_INFO="—"; V6_INFO="—"
V4_BASE_ASN=""; V6_BASE_ASN=""; V4_SPLIT_DOMAINS=0; V6_SPLIT_DOMAINS=0
V4_MTR_BASE_ASN=""; V4_MTR_BASE_HOP=""; V4_MTR_BASE_INFO="—"
V6_MTR_BASE_ASN=""; V6_MTR_BASE_HOP=""; V6_MTR_BASE_INFO="—"
[[ $OUTPUT_JSON -eq 0 ]] && print_banner "$HOST_NAME" "$START_TS"
do_env_detect() {
    local a c d i def_ip line ip ep
    local -a v4_lines=() v6_lines=()
    local -A v4_seen=() v6_seen=()
    if [[ "$PASS_MODE" == "auto" || "$PASS_MODE" == "v4-only" ]]; then
        while IFS= read -r line; do [[ -z "$line" ]] && continue; v4_lines+=("$line"); v4_seen["${line%%|*}"]=1; done < <(detect_all_v4_egress_ips)
        V4_ECHO_UNIQUE=${#v4_seen[@]}
        if [[ ${#v4_lines[@]} -gt 0 ]]; then
            V4_IP="${v4_lines[0]%%|*}"; local detail=""
            for line in "${v4_lines[@]}"; do ip="${line%%|*}"; ep="${line##*|}"; ep="${ep#https://}"; ep="${ep%%/*}"; detail+="${detail:+ ; }${ip}@${ep}"; done
            V4_ECHO_DETAIL="$detail"
            d="$(lookup_ip "$V4_IP" || true)"; split_lookup_data "$d" a i c; normalize_lookup_fields a i c
            [[ -z "$c" ]] && c="??"; [[ -z "$i" ]] && i="Unknown"; V4_BASE_ASN="$a"
            if [[ -n "$a" ]]; then V4_INFO="$c · AS${a} ${i}"; else V4_INFO="$c · ${i}"; fi
        fi
    fi
    if [[ "$PASS_MODE" == "auto" || "$PASS_MODE" == "v6-only" ]]; then
        while IFS= read -r line; do [[ -z "$line" ]] && continue; v6_lines+=("$line"); v6_seen["${line%%|*}"]=1; done < <(detect_all_v6_egress_ips)
        V6_ECHO_UNIQUE=${#v6_seen[@]}
        if [[ ${#v6_lines[@]} -gt 0 ]]; then
            V6_IP="${v6_lines[0]%%|*}"; local detail=""
            for line in "${v6_lines[@]}"; do ip="${line%%|*}"; ep="${line##*|}"; ep="${ep#https://}"; ep="${ep%%/*}"; detail+="${detail:+ ; }${ip}@${ep}"; done
            V6_ECHO_DETAIL="$detail"
            d="$(lookup_ip "$V6_IP" || true)"; split_lookup_data "$d" a i c; normalize_lookup_fields a i c
            [[ -z "$c" ]] && c="??"; [[ -z "$i" ]] && i="Unknown"; V6_BASE_ASN="$a"
            if [[ -n "$a" ]]; then V6_INFO="$c · AS${a} ${i}"; else V6_INFO="$c · ${i}"; fi
        fi
    fi
    if [[ "$PASS_MODE" == "auto" ]]; then
        def_ip="$(detect_default_egress_ip || true)"; [[ -n "$def_ip" ]] && DEFAULT_EGRESS="$(ip_family "$def_ip")"
    elif [[ "$PASS_MODE" == "v4-only" ]]; then DEFAULT_EGRESS="ipv4"
    elif [[ "$PASS_MODE" == "v6-only" ]]; then DEFAULT_EGRESS="ipv6"; fi
}
do_env_detect
if [[ -n "$V4_IP" && ( "$PASS_MODE" == "auto" || "$PASS_MODE" == "v4-only" ) ]]; then
    detect_mtr_base_asn "-4" "V4" || true
fi
if [[ -n "$V6_IP" && ( "$PASS_MODE" == "auto" || "$PASS_MODE" == "v6-only" ) ]]; then
    detect_mtr_base_asn "-6" "V6" || true
fi
[[ $OUTPUT_JSON -eq 0 && "$PASS_MODE" == "auto" ]] && print_env_section "$DEFAULT_EGRESS" "$V4_IP" "$V6_IP" "$V4_INFO" "$V6_INFO"
[[ $OUTPUT_JSON -eq 0 ]] && printf "\n  %s共 %d 个域名, 按分类逐组检测 (绿●=默认出口, 彩色●=分流)%s\n" "$DIM" "$TOTAL" "$R"
TMP_V4_RESULTS="$(mktemp "$CACHE_DIR/.tmp-v4.XXXXXXXX")"
TMP_V6_RESULTS="$(mktemp "$CACHE_DIR/.tmp-v6.XXXXXXXX")"
chmod 600 "$TMP_V4_RESULTS" "$TMP_V6_RESULTS"
V6_SKIP_REASON=""
case "$PASS_MODE" in
    auto)
        if [[ -n "$V4_IP" ]]; then run_check_pass "IPv4" "-4" "$TMP_V4_RESULTS"; V4_PASS_RAN=1
        else print_pass_header "IPv4"; [[ $OUTPUT_JSON -eq 0 ]] && printf "    %s  IPv4 出口不可用 — 跳过\n" "$SYM_SKIP"; fi
        if [[ -n "$V6_IP" ]]; then run_check_pass "IPv6" "-6" "$TMP_V6_RESULTS"; V6_PASS_RAN=1
        else V6_SKIP_REASON="IPv6 出口不可用或已禁用"; print_pass_header "IPv6"; [[ $OUTPUT_JSON -eq 0 ]] && printf "    %s  %s — 跳过\n" "$SYM_SKIP" "$V6_SKIP_REASON"; fi ;;
    v4-only) if [[ -n "$V4_IP" ]]; then run_check_pass "IPv4" "-4" "$TMP_V4_RESULTS"; V4_PASS_RAN=1; else err "IPv4 出口不可用"; exit 2; fi ;;
    v6-only) if [[ -n "$V6_IP" ]]; then run_check_pass "IPv6" "-6" "$TMP_V6_RESULTS"; V6_PASS_RAN=1; else err "IPv6 出口不可用"; exit 2; fi ;;
esac
END_EPOCH=$(date +%s); ELAPSED=$((END_EPOCH - START_EPOCH)); ELAPSED_STR="$(format_elapsed "$ELAPSED")"
if [[ $OUTPUT_JSON -eq 0 ]]; then
    printf "\n"; rule_double 72
    if [[ $V4_PASS_RAN -eq 1 ]]; then
        printf "  IPv4:  %s%d 域名%s   %s%d 条线路%s   %s%d 域名分流%s   %s%d 探测失败%s\n" "$GREEN" "$V4_OK" "$R" "$CYAN" "$V4_ROUTE_COUNT" "$R" "$YELLOW" "$V4_SPLIT_DOMAINS" "$R" "$RED" "$V4_DOWN" "$R"
    else printf "  IPv4:  %s skipped\n" "$SYM_SKIP"; fi
    if [[ $V6_PASS_RAN -eq 1 ]]; then
        printf "  IPv6:  %s%d 域名%s   %s%d 条线路%s   %s%d 域名分流%s   %s%d 探测失败%s\n" "$GREEN" "$V6_OK" "$R" "$CYAN" "$V6_ROUTE_COUNT" "$R" "$YELLOW" "$V6_SPLIT_DOMAINS" "$R" "$RED" "$V6_DOWN" "$R"
    else printf "  IPv6:  %s skipped  %s%s%s\n" "$SYM_SKIP" "$DIM" "${V6_SKIP_REASON:-}" "$R"; fi
    printf "  %selapsed:%s %s\n" "$DIM" "$R" "$ELAPSED_STR"; rule_double 72
fi
FINAL_JSON="$(mktemp "$CACHE_DIR/.tmp-final.XXXXXXXX")"; chmod 600 "$FINAL_JSON"
build_pass_obj() {
    local prefix="$1" ran="$2" tmp_file="$3" skip_reason="$4"
    if [[ "$ran" == "1" ]]; then
        local ok down routes
        eval "ok=\${${prefix}_OK}"; eval "down=\${${prefix}_DOWN}"; eval "routes=\${${prefix}_ROUTE_COUNT}"
        local split="false"; [[ $routes -ge 2 ]] && split="true"
        jq -n --argjson ok "$ok" --argjson dn "$down" --argjson rc "$routes" --argjson split "$split" --slurpfile r "$tmp_file" \
            '{available:true, summary:{total:($ok+$dn), ok:$ok, down:$dn}, route_count:$rc, split_routing_detected:$split, results:$r[0]}'
    else
        jq -n --arg reason "$skip_reason" '{available:false, summary:null, route_count:0, split_routing_detected:false, results:null, reason:$reason}'
    fi
}
V4_PASS_JSON="$(build_pass_obj V4 "$V4_PASS_RAN" "$TMP_V4_RESULTS" "IPv4 出口不可用")"
V6_PASS_JSON="$(build_pass_obj V6 "$V6_PASS_RAN" "$TMP_V6_RESULTS" "${V6_SKIP_REASON:-IPv6 出口不可用或已禁用}")"
jq -n --arg ts "$START_TS" --arg host "$HOST_NAME" --arg ver "$VERSION" --arg defegr "$DEFAULT_EGRESS" \
    --arg v4ip "$V4_IP" --arg v4info "$V4_INFO" --arg v6ip "$V6_IP" --arg v6info "$V6_INFO" \
    --arg v4echo "$V4_ECHO_DETAIL" --arg v6echo "$V6_ECHO_DETAIL" \
    --argjson v4uniq "$V4_ECHO_UNIQUE" --argjson v6uniq "$V6_ECHO_UNIQUE" \
    --argjson elapsed "$ELAPSED" --argjson v4 "$V4_PASS_JSON" --argjson v6 "$V6_PASS_JSON" \
    '{ timestamp:$ts, host:$host, version:$ver, elapsed_seconds:$elapsed,
       env:{ default_egress:$defegr,
         ipv4:{ip:(if $v4ip=="" then null else $v4ip end), info:$v4info, echo_unique_count:$v4uniq, echo_detail:(if $v4echo=="" then null else $v4echo end), snat_suspected:($v4uniq>1)},
         ipv6:{ip:(if $v6ip=="" then null else $v6ip end), info:$v6info, echo_unique_count:$v6uniq, echo_detail:(if $v6echo=="" then null else $v6echo end), snat_suspected:($v6uniq>1)} },
       ipv4:$v4, ipv6:$v6 }' > "$FINAL_JSON"
[[ $OUTPUT_JSON -eq 1 ]] && cat "$FINAL_JSON"
LAST_JSON="$CACHE_DIR/last.json"
if mv -f -- "$FINAL_JSON" "$LAST_JSON" 2>/dev/null; then chmod 600 "$LAST_JSON" 2>/dev/null || true; FINAL_JSON=""
else err "保存 last.json 失败"; fi
TOTAL_DOWN=$((V4_DOWN + V6_DOWN))
[[ $V4_PASS_RAN -eq 0 && $V6_PASS_RAN -eq 0 ]] && exit 2
[[ $TOTAL_DOWN -gt 0 ]] && exit 2
exit 0
