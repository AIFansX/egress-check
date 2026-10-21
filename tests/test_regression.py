"""Offline regression tests: real script functions, deterministic network fixtures."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'ip.sh').read_text(encoding='utf-8')
BASH = os.environ.get('TEST_BASH', shutil.which('bash') or 'bash')


def function(name):
    start = SOURCE.index(name + '() {')
    first_line = SOURCE[start:SOURCE.index('\n', start)]
    if first_line.endswith('}'):
        return first_line + '\n'
    end = SOURCE.index('\n}', start) + 2
    return SOURCE[start:end] + '\n'


IP_CODE = SOURCE[SOURCE.index("IP_AWK='"):SOURCE.index('resolve_target() {')]
PROBE_CODE = IP_CODE + ''.join(function(n) for n in
    ('is_valid_domain', 'resolve_target', 'parse_mtr_report', 'run_mtr_report', 'first_public_hop'))


def shell(code, data=None, env=None, timeout=15):
    return subprocess.run([BASH, '-c', code], input=data, text=True,
        encoding='utf-8', stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ, **(env or {})}, timeout=timeout)


def row(ip, avg='9.0', loss='0.0', number=1):
    return f'{number}.|-- {ip} {loss}% 3 1.0 {avg} 1.0 10.0 0.0\n'


def report(*rows):
    return 'Start: 2026-10-21\nHOST: test Loss% Snt Last Avg Best Wrst StDev\n' + ''.join(rows)


class ParserTests(unittest.TestCase):
    def test_route_evidence_retains_hop_depth_and_early_gaps(self):
        cases=[
            (report(row('10.0.0.1',number=1),row('1.1.1.1',number=2),row('104.18.33.45',number=3)),'2,0,0'),
            (report(row('???',loss='100',number=1),row('1.1.1.1',number=2),row('104.18.33.45',number=3)),'2,1,0'),
            (report(row('1.1.1.1',number=5),row('104.18.33.45',number=6)),'5,1,0'),
            (report(row('1.1.1.1',number=1),'    8.8.8.8\n',row('104.18.33.45',number=2)),'1,0,1'),
            (report(row('10.0.0.1',number=1),'    8.8.8.8\n',row('1.1.1.1',number=2),row('104.18.33.45',number=3)),'2,0,1'),
            (report(row('1.1.1.1',number=1),row('???',loss='100',number=2),row('104.18.33.45',number=3)),'1,0,0'),
        ]
        for data,expected in cases:
            result=shell(PROBE_CODE+'parse_mtr_report 104.18.33.45 1',data)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.rstrip('\n').split('\t')[3],expected)

    def test_evidence_comparison_requires_depth_protocol_and_complete_prefix(self):
        code=function('route_evidence_clean')+function('route_evidence_comparable')
        for candidate,valid in [('2,0,0,icmp,1.1.1.1',True),('3,0,0,icmp,1.1.1.1',False),
            ('2,1,0,icmp,1.1.1.1',False),('2,0,1,icmp,1.1.1.1',False),
            ('2,0,0,tcp,1.1.1.1',False),('',False)]:
            result=shell(code+f"route_evidence_comparable '2,0,0,icmp,8.8.8.8' '{candidate}'")
            self.assertEqual(result.returncode==0,valid,candidate)

    def test_repeat_filter_keeps_useful_checks_and_skips_protocol_mismatch(self):
        code=''.join(function(n) for n in ('route_evidence_clean','route_evidence_usable','route_visible_node_matches','route_evidence_comparable','route_repeat_needed'))
        for evidence,asn,needed in [('2,0,0,icmp,1.1.1.1','4780',False),
            ('2,0,0,icmp,1.1.1.1','13335',True),('3,1,0,icmp,1.1.1.1','4780',False),
            ('2,0,1,icmp,1.1.1.1','13335',True),('2,0,0,tcp,1.1.1.1','13335',False),
            ('2,0,0,icmp,1.1.1.1','',False)]:
            result=shell(code+f"route_repeat_needed '2,0,0,icmp,8.8.8.8' '{evidence}' 4780 '{asn}'")
            self.assertEqual(result.returncode==0,needed,(evidence,asn))

    def test_visible_match_requires_exact_node_depth_and_unambiguous_evidence(self):
        code=''.join(function(n) for n in ('route_evidence_usable','route_visible_node_matches'))
        for evidence,hop,expected in [
            ('2,1,0,icmp,1.1.1.1','139.175.240.84',True),
            ('2,0,0,tcp,1.1.1.1','139.175.240.84',True),
            ('3,1,0,icmp,1.1.1.1','139.175.240.84',False),
            ('2,1,1,icmp,1.1.1.1','139.175.240.84',False),
            ('2,1,0,icmp,1.1.1.1','192.72.221.37',False),
            ('2,1,0,udp,1.1.1.1','139.175.240.84',False),
        ]:
            result=shell(code+f"route_visible_node_matches '2,1,0,icmp,8.8.8.8' '{evidence}' '139.175.240.84' '{hop}'")
            self.assertEqual(result.returncode==0,expected,(evidence,hop))

    def test_partial_private_gateway_loss_does_not_create_gap(self):
        data=report(row('192.168.11.1',loss='71.4',number=1),
                    row('139.175.240.84',number=2),row('104.18.33.45',number=3))
        result=shell(PROBE_CODE+'parse_mtr_report 104.18.33.45 1',data)
        self.assertEqual(result.stdout.rstrip().split('\t')[3],'2,0,0')

    def test_multipath_continuation_is_not_a_numbered_hop(self):
        data=report(row('10.0.0.1'), '        10.0.0.2\n',
                    row('1.1.1.1'), '        8.8.8.8\n',
                    row('104.18.33.45','1.9'))
        self.assertEqual(self.parse(data),['1.1.1.1','1.9','1.1.1.1'])
        self.assertEqual(self.parse('        8.8.8.8\n')[0], '__PARSE_ERROR__')
        self.assertEqual(self.parse(report('1. 1.1.1.1 0.0% 3 1.0 2.0 1.0 3.0 0.0\n',
                    row('104.18.33.45','1.9'))),['1.1.1.1','1.9','1.1.1.1'])

    def test_mtr_large_values_with_trailing_decimal_point(self):
        data=report(row('192.168.43.1','4457.'),row('1.1.1.1','1028.'),
                    row('104.18.33.45','230.4'))
        self.assertEqual(self.parse(data),['1.1.1.1','230.4','1.1.1.1'])
        self.assertEqual(self.parse(report(row('104.18.33.45','1234.'))),
                         ['__HIDDEN__','1234.0',''])

    def test_mtr_095_real_loss_column_shape(self):
        # Captured MTR 0.95 report layout; host and addresses are anonymized.
        data=(ROOT/'tests/fixtures/mtr-095-loss-report.txt').read_text()
        self.assertEqual(self.parse(data),['1.1.1.1','1.5','1.1.1.1'])
        data=data.rsplit(' 10.|--',1)[0]
        self.assertEqual(self.parse(data),['1.1.1.1','-','1.1.1.1'])
        self.assertEqual(self.parse(report('1.|-- ??? 100.0 3 0.0 0.0 0.0 0.0 0.0\n')),
                         ['__NO_REPLY__','-',''])

    def parse(self, data, target='104.18.33.45', awk=None):
        wrapper = ''
        if awk:
            wrapper = 'awk() { command ' + awk + ' "$@"; }\n'
        result = shell(PROBE_CODE + wrapper + f'parse_mtr_report {target}', data)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout.strip('\n').split('\t')

    def test_public_hops_and_target_exclusion(self):
        data = report(row('172.16.0.1'), row('168.95.98.254'),
                      row('220.128.20.86'), row('104.18.33.45', '9.1'))
        self.assertEqual(self.parse(data), ['168.95.98.254', '9.1', '168.95.98.254 220.128.20.86'])

    def test_private_and_target_only(self):
        self.assertEqual(self.parse(report(row('10.0.0.1'), row('104.18.33.45'))),
                         ['__HIDDEN__', '9.0', ''])

    def test_no_response_is_not_hidden_or_zero_latency(self):
        self.assertEqual(self.parse(report(row('10.0.0.1'), row('???', '0.0', '100.0'))),
                         ['__NO_REPLY__', '-', ''])

    def test_transit_latency_not_target_latency(self):
        self.assertEqual(self.parse(report(row('168.95.98.254', '5.0'), row('???', '0.0', '100.0'))),
                         ['168.95.98.254', '-', '168.95.98.254'])

    def test_target_latency_not_overwritten(self):
        self.assertEqual(self.parse(report(row('104.18.33.45', '7.3'), row('???', '0.0', '100.0')))[1], '7.3')

    def test_gaps_and_ansi(self):
        data = report('2. (waiting for reply)\n', '\x1b[32m' + row('168.95.98.254') + '\x1b[0m', row('104.18.33.45'))
        self.assertEqual(self.parse(data)[0], '168.95.98.254')

    def test_invalid_or_hostname_rows_are_parser_errors(self):
        for data in ('', 'mtr: permission denied', report(row('999.1.1.1')),
                     report(row('gateway.example.org')), report(row('104.18.33.45', 'invalid'))):
            with self.subTest(data=data):
                self.assertEqual(self.parse(data)[0], '__PARSE_ERROR__')

    def test_ipv6_compression_and_nonpublic_addresses(self):
        target='2607:6bc0::10'
        data=report(row('::1'), row('fea0::1'), row('fd00::1'), row('2001:4860::1'),
                    row('2607:6BC0:0:0:0:0:0:10', '12.4'))
        self.assertEqual(self.parse(data,target), ['2001:4860::1','12.4','2001:4860::1'])
        self.assertEqual(self.parse(report(row('fe80::1%eth0'),row(target)),target)[0], '__HIDDEN__')

    def test_ipv6_mapped_and_invalid(self):
        self.assertEqual(self.parse(report(row('::ffff:192.168.1.1'),row('2607:6bc0::10')), '2607:6bc0::10')[0], '__HIDDEN__')
        self.assertEqual(self.parse(report(row('2001:::1')), '2607:6bc0::10')[0], '__PARSE_ERROR__')

    def test_awk_implementations(self):
        variants = ['awk']
        for name in ('gawk', 'mawk', 'old-mawk'):
            if shutil.which(name): variants.append(name)
        if shutil.which('mawk'):
            # Older mawk is already interval-free and may not know this option.
            option = subprocess.run(['mawk','-W','traditional','BEGIN {exit}'],capture_output=True)
            if option.returncode == 0 and not option.stderr:
                variants.append('mawk -W traditional')
        if shutil.which('busybox'): variants.append('busybox awk')
        data=report(row('10.0.0.1'),row('168.95.98.254'),row('104.18.33.45'))
        for variant in variants:
            with self.subTest(awk=variant):
                self.assertEqual(self.parse(data,awk=variant)[0], '168.95.98.254')
                self.assertEqual(self.parse(report(row('fe80::1'),row('2001:4860::1'),
                    row('2607:6bc0:0:0:0:0:0:10')), '2607:6bc0::10', variant)[0], '2001:4860::1')
                self.assertEqual(self.parse(report(row('???','0.0','100.0')),awk=variant)[0], '__NO_REPLY__')
                fixture=(ROOT/'tests/fixtures/mtr-095-loss-report.txt').read_text()
                self.assertEqual(self.parse(fixture,awk=variant),['1.1.1.1','1.5','1.1.1.1'])
                self.assertEqual(self.parse(report(row('1.1.1.1','1028.'),
                    row('104.18.33.45','1234.')),awk=variant),['1.1.1.1','1234.0','1.1.1.1'])
                self.assertEqual(self.parse(report(row('1.1.1.1'), '        8.8.8.8\n',
                    row('104.18.33.45','1.9')),awk=variant),['1.1.1.1','1.9','1.1.1.1'])

    def test_retry_reuses_target_and_tcp_fallback(self):
        code=PROBE_CODE + '''
MTR_BUDGET=5 MTR_ATTEMPTS=2 MTR_TIMEOUT=2 MTR_COUNT=3 MTR_MAXTTL=30 MTR_NICE=10
resolve_target() { printf '104.18.33.45'; }
run_mtr_report() {
    [[ "$3" == '104.18.33.45' ]] || exit 10
    if [[ "$2" == tcp ]]; then
        printf '%s\n' '1.|-- 10.0.0.1 0.0% 3 1.0 1.0 1.0 1.0 0.0' '2.|-- 104.18.33.45 0.0% 3 1.0 7.0 1.0 10.0 0.0'
    else printf 'bad report'; fi
}
first_public_hop -4 example.com
'''
        result=shell(code)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(result.stdout.startswith('__HIDDEN__\t7.0'))

    def test_empty_retry_preserves_parse_error(self):
        code=PROBE_CODE+'''
MTR_BUDGET=5 MTR_ATTEMPTS=1 MTR_TIMEOUT=2
resolve_target() { printf '104.18.33.45'; }
run_mtr_report() { if [[ "$2" == icmp ]]; then printf 'invalid report'; fi; }
first_public_hop -4 example.com
'''
        result=shell(code)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(result.stdout.startswith('__PARSE_ERROR__\t-'))


class FormatAndRulesTests(unittest.TestCase):
    def test_compact_menu_and_default_choice(self):
        start=SOURCE.index('while [[ $# -gt 0 ]]; do')
        end=SOURCE.index('\nfor setting in MTR_TIMEOUT',start)
        code='set -euo pipefail\n'+''.join(function(n) for n in
             ('set_colors','err','default_mtr_concurrency','usage','interactive_menu'))
        code+='''
VERSION=test BRAND_URL=example.com PASS_MODE=auto COMPACT_OUTPUT=0 INTERACTIVE=0
OUTPUT_JSON=0 USE_COLOR=0 ONLY_CAT=""
set_colors
'''
        cases=[('-I','0\n','auto 1'),('-I','1\n','auto 0'),('-I','\n','auto 0'),
               ('--compact',None,'auto 1'),('',None,'auto 0'),
               ('--compact -I','1\n','auto 0')]
        for args,answer,expected in cases:
            with self.subTest(args=args,answer=answer):
                # Feed menu input inside Bash to avoid Windows text-mode CRLF conversion.
                menu_input='exec <<< "$MENU_ANSWER"\n' if answer is not None else ''
                result=shell(code+menu_input+f'set -- {args}\n'+SOURCE[start:end]+
                             '\nprintf "%s %s\\n" "$PASS_MODE" "$COMPACT_OUTPUT"\n',
                             env={'MENU_ANSWER':(answer or '').rstrip('\n')})
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout.strip(),expected)
                if '-I' in args:
                    self.assertIn('请输入 0-7 [默认1]',result.stderr)
                    self.assertIn('0) 简洁模式',result.stderr)
                    self.assertIn('1) 【默认】完整检测',result.stderr)

    def test_compact_rows_hide_ip_asn_and_keep_status_colors_and_alignment(self):
        code='set -euo pipefail\n'+''.join(function(n) for n in
             ('set_colors','latency_color','format_latency_text','format_latency','print_result_row'))
        code+='''
OUTPUT_JSON=0 COMPACT_OUTPUT=1 DOMAIN_WIDTH=28
for USE_COLOR in 0 1; do
 set_colors
 for IP_WIDTH in 15 39; do
  ip=203.73.217.1
  [[ $IP_WIDTH == 39 ]] && ip=2001:4860:1234:5678:9abc:def0:1234:5678
  for latency in 0.8 15.9 198.6 999.9 1000 -; do
   print_result_row "${GREEN}●${R}" a.example "$ip" "$latency" TW 4780 'Sample ISP' 0 '可见首跳 ASN 与基准一致'
   print_result_row "${YELLOW}●${R}" long-domain.example "$ip" "$latency" US 13335 'Other ISP' 1 '复测首跳 ASN 差异'
   print_result_row "${GRAY}⊘${R}" unknown.example "$ip" "$latency" TW 4780 'Sample ISP' -1 '首跳证据不足 / 无法判定'
  done
 done
 print_result_row "${GRAY}⊘${R}" hidden.example - 9.0 -- '' '路径隐藏 / 仅目标可见' 0
 print_result_row "${RED}✗${R}" failed.example - - -- '' 'DNS 解析失败' 0
done
'''
        result=shell(code)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('203.73.217.1',result.stdout)
        self.assertNotIn('2001:4860:',result.stdout)
        self.assertNotIn('AS4780',result.stdout)
        self.assertNotIn('ISP',result.stdout)
        self.assertNotIn('可见首跳 ASN 与基准一致',result.stdout)
        plain=re.sub(r'\x1b\[[0-9;]*m','',result.stdout)
        self.assertIn('目标未回应',plain)
        self.assertIn('DNS 解析失败',plain)
        self.assertIn('路径隐藏 / 仅目标可见',plain)
        self.assertIn('首跳证据不足 / 无法判定',plain)
        lines=plain.splitlines()
        self.assertEqual(len(lines),76)
        self.assertEqual(len({re.search(r' (TW|US|--)($| )',s).start() for s in lines}),1)
        split_lines=[s for s in result.stdout.splitlines() if 'long-domain.example' in s]
        self.assertEqual(len(split_lines),24)
        self.assertTrue(all('⮜ 疑似分流' in s for s in split_lines))
        self.assertTrue(all('\x1b[33m' in s and s.endswith('\x1b[0m') for s in split_lines[12:]))
        normal_lines=[s for s in result.stdout.splitlines() if 'a.example' in s]
        self.assertIn('\x1b[32m',normal_lines[12])
        self.assertIn('\x1b[33m',normal_lines[14])
        self.assertIn('\x1b[38;5;130m',normal_lines[15])

    def test_compact_summary_hides_only_matching_domains_and_path_section(self):
        start=SOURCE.index('    if [[ $OUTPUT_JSON -eq 0 && $route_count -gt 0 ]]; then')
        end=SOURCE.index('\n}\n',start)
        code='set -euo pipefail\n'+function('print_route_summary_domains')+'''
rule_single() { printf '%s' '---'; }
short_text() { printf '%s' "$1"; }
BOLD="" R="" DIM="" YELLOW="" GREEN="" GRAY="" CYAN="" SYM_SKIP="?" SYM_WARN="!" SYM_INFO="i"
OUTPUT_JSON=0 PATH_SUMMARY_LIMIT=8
render_fixture() {
 local label="$1" route_count=3 base_desc=baseline effective_base_asn=4780 split_idx=1 split_domain_count=25 split_color_n=1
 local -a SPLIT_COLORS=("") path_order=("test-path" "AS4780 Baseline" "AS4780 Baseline -> AS13335 Other" "AS47800 Other")
 local -A route_split=([a]=0 [b]=1 [c]=-1) route_asn=([a]=4780 [b]=13335 [c]=9002)
 local -A route_isp=([a]=NormalISP [b]=OtherISP [c]=UnknownISP)
 local -A route_cc=([a]=TW [b]=US [c]=US) route_scidx=([b]=0)
 local -A path_domains=([test-path]="path-only.example") path_counts=([test-path]=1)
'''
        domains={key:' '.join(f'{key}{i:02d}.example' for i in range(count))
                 for key,count in [('a',85),('b',25),('c',12)]}
        code+=' local -A route_domains=('+ ' '.join(f'[{key}]="{value}"' for key,value in domains.items())+')\n'
        path_cases=[('AS4780 Baseline','pb',62),('AS4780 Baseline -> AS13335 Other','pm',15),('AS47800 Other','po',12)]
        for chain,prefix,count in path_cases:
            path_list=' '.join(f'{prefix}{i:02d}.example' for i in range(count))
            code+=f' path_domains["{chain}"]="{path_list}"; path_counts["{chain}"]={count}\n'
        code+=SOURCE[start:end]+'\n}\n'
        cases=[(compact,label) for compact in (0,1) for label in ('IPv4','IPv6')]
        for compact,label in cases:
            code+=f'COMPACT_OUTPUT={compact}; printf "CASE {compact} {label}\\n"; render_fixture {label}\n'
        result=shell(code)
        self.assertEqual(result.returncode,0,result.stderr)
        sections=re.split(r'^CASE [01] IPv[46]\n',result.stdout,flags=re.M)[1:]
        self.assertEqual(len(sections),4)
        for (compact,label),text in zip(cases,sections):
            with self.subTest(compact=compact,label=label):
                self.assertIn('85 域名',text)
                self.assertIn('25 域名',text)
                self.assertIn('12 域名',text)
                self.assertEqual(re.findall(r'a\d+\.example',text),
                                 [] if compact else [f'a{i:02d}.example' for i in range(10)])
                for key,count in [('b',25),('c',12)]:
                    self.assertEqual(re.findall(rf'\b{key}\d+\.example',text),
                                     [f'{key}{i:02d}.example' for i in range(count)])
                if compact:
                    self.assertNotIn('路径 ASN 摘要',text)
                    self.assertNotIn('path-only.example',text)
                    self.assertNotIn('NormalISP',text)
                else:
                    self.assertIn(f'{label} 路径 ASN 摘要',text)
                    self.assertIn('另有 75 个域名（完整列表见上方明细）',text)
                for chain,prefix,count in path_cases:
                    expected=0 if compact else min(count,10)
                    self.assertEqual(re.findall(rf'{prefix}\d+\.example',text),
                                     [f'{prefix}{i:02d}.example' for i in range(expected)])
                if not compact:
                    self.assertIn('另有 52 个域名（完整列表见上方明细）',text)
                    self.assertIn('62 域名',text)
                self.assertNotIn('个域名未展开',text)

    def test_latency_boundaries(self):
        code=function('set_colors')+function('latency_color')+'''
USE_COLOR=1; set_colors
for n in 49.9 50 200 200.1; do latency_color "$n"; printf '\\n'; done
'''
        self.assertEqual(shell(code).stdout.splitlines(),
                         ['\x1b[32m','\x1b[33m','\x1b[33m','\x1b[38;5;130m'])

    def test_default_rules_identical_and_pruned(self):
        block=SOURCE.split("DEFAULT_RULES=$(cat <<'EOF'\n",1)[1].split('\nEOF',1)[0]
        clean=lambda s:[x for x in s.splitlines() if x and not x.startswith('#')]
        rules=clean(block)
        self.assertEqual(rules,clean((ROOT/'rules.conf.example').read_text(encoding='utf-8')))
        domains={r.split('|')[1] for r in rules}
        self.assertEqual(len(rules),115)
        self.assertEqual(len(domains),115)
        self.assertIn('AI|pixtv.ai|||PixTV',rules)
        self.assertTrue(domains.isdisjoint({'startpage.com','oraclecloud.com','registry-1.docker.io',
                                           'shopee.co.th','shopee.com.my','shopee.ph','poe.com'}))
        self.assertEqual({d for d in domains if d.startswith('shopee.')},
            {'shopee.com','shopee.sg','shopee.tw','shopee.co.id','shopee.vn','shopee.com.br'})

    def test_route_summary_domain_limit_only_for_baseline_matches(self):
        code='set -euo pipefail\nR=""\n'+function('print_route_summary_domains')
        cases=[(state,count) for state in (0,1,-1) for count in (0,1,9,10,11,25)]
        for state,count in cases:
            domains=' '.join(f'd{i:02d}.example' for i in range(count))
            code+=f"printf 'CASE {state} {count}\\n'\nprint_route_summary_domains '{domains}' {state} ''\n"
        result=shell(code)
        self.assertEqual(result.returncode,0,result.stderr)
        sections=re.split(r'^CASE -?\d+ \d+\n',result.stdout,flags=re.M)[1:]
        self.assertEqual(len(sections),len(cases))
        for (state,count),text in zip(cases,sections):
            with self.subTest(state=state,count=count):
                shown=min(count,10) if state==0 else count
                self.assertEqual(re.findall(r'd\d+\.example',text),
                                 [f'd{i:02d}.example' for i in range(shown)])
                if count>shown: self.assertIn(f'另有 {count-shown} 个域名（完整列表见上方明细）',text)
                else: self.assertNotIn('未展开',text)
                lines=[s for s in text.splitlines() if '.example' in s]
                self.assertEqual([len(s.split()) for s in lines],
                                 [min(4,shown-i) for i in range(0,shown,4)])
                self.assertTrue(all(s.startswith('      ') for s in lines))

    def test_route_summary_colors_reset_and_multiple_groups(self):
        code='set -euo pipefail\n'+function('set_colors')+function('print_route_summary_domains')
        code+='USE_COLOR=1; set_colors\n'
        domains=' '.join(f'd{i:02d}.example' for i in range(12))
        code+=f'print_route_summary_domains "{domains}" 0 "$DIM"\n'
        code+=f'print_route_summary_domains "{domains}" 1 "$YELLOW"\n'
        result=shell(code)
        self.assertEqual(result.returncode,0,result.stderr)
        lines=result.stdout.splitlines()
        self.assertEqual(len(lines),7)
        self.assertTrue(all(s.endswith('\x1b[0m') for s in lines))
        self.assertTrue(all(s.startswith('\x1b[33m      ') for s in lines[4:]))
        self.assertIn('d11.example',lines[-1])

    def test_columns_and_colors(self):
        code=''.join(function(n) for n in ('set_colors','latency_color','format_latency_text','format_latency','print_result_row'))
        code+='''
OUTPUT_JSON=0
DOMAIN_WIDTH=28
for USE_COLOR in 0 1; do
 set_colors
 for IP_WIDTH in 15 39; do
  first_ip=203.73.217.1; other_ip=104.28.0.0
  if [[ $IP_WIDTH == 39 ]]; then
   first_ip=2001:4860:1234:5678:9abc:def0:1234:5678
   other_ip=2607:6bc0:1234:5678:9abc:def0:1234:5678
  fi
  for latency in 0.8 15.9 198.6 999.9 1000 -; do
   print_result_row "${GREEN}●${R}" a.example "$first_ip" "$latency" TW 4780 ISP 0
   print_result_row "${YELLOW}●${R}" very-long-domain.example "$other_ip" "$latency" US 13335 ISP 1
   print_result_row "${GRAY}⊘${R}" hidden.example - "$latency" -- '' hidden 0
  done
 done
done
'''
        result=shell(code)
        self.assertEqual(result.returncode,0,result.stderr)
        lines=result.stdout.splitlines()
        self.assertEqual(len(lines),72)
        plain=[re.sub(r'\x1b\[[0-9;]*m','',s) for s in lines]
        for start in (0,18,36,54):
            positions=[re.search(r' (TW|US|--) ',s).start() for s in plain[start:start+18]]
            self.assertEqual(len(set(positions)),1,plain[start:start+18])
        self.assertNotIn('\x1b', '\n'.join(lines[:36]))
        self.assertIn('\x1b[33m', lines[37])


@unittest.skipUnless(os.environ.get('TEST_REAL_MTR') == '1', 'Real MTR smoke test is enabled in Linux CI')
class RealMtrTests(unittest.TestCase):
    parse = ParserTests.parse

    def test_installed_mtr_loopback_report(self):
        command = ([] if os.geteuid() == 0 else ['sudo','-n']) + [
            'mtr','-4','-r','-n','-c','2','-m','3','127.0.0.1']
        result = subprocess.run(command, text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        parsed = self.parse(result.stdout,'127.0.0.1')
        self.assertEqual(parsed[0],'__HIDDEN__',result.stdout)
        self.assertRegex(parsed[1],r'^[0-9]+([.][0-9]+)?$')


@unittest.skipUnless(os.name=='posix' and shutil.which('jq'), 'Linux integration requires jq')
class IntegrationTests(unittest.TestCase):
    def configure_route_evidence(self, probe_body, baseline_body=None):
        self.rules.write_text('AI|example.com|||test\n')
        self.env['PROBE_COUNTER']=str(self.base/'probe.count')
        self.stub('getent', '''case "$*" in *google.com*) echo '8.8.8.8 STREAM google.com';; *) echo '104.18.33.45 STREAM example.com';; esac''')
        self.stub('curl', '''case "$*" in
 *-6*) exit 1;;
 *ipinfo.io/1.1.1.1/json*) echo '{"country":"US","org":"AS13335 Other ISP"}';;
 *ipinfo.io/2.2.2.2/json*) echo '{"country":"US","org":"AS9002 Third ISP"}';;
 *ipinfo.io/*/json*) echo '{"country":"TW","org":"AS4780 Baseline"}';;
 *) echo 203.73.217.1;; esac''')
        baseline_body=baseline_body or "printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0' '3.|-- 8.8.8.8 0.0% 3 1 1 1 1 0'"
        self.stub('mtr','if [[ "${@: -1}" == 8.8.8.8 ]]; then\n'+baseline_body+'\nelse\n'+probe_body+'\nfi')

    def test_missing_early_hop_not_false_split(self):
        self.configure_route_evidence("printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- ??? 100.0 3 0 0 0 0 0' '3.|-- 1.1.1.1 0.0% 3 1 1 1 1 0' '4.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'")
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertIsNone(obj['ipv4']['split_routing_detected'])
        self.assertIsNone(obj['ipv4']['results'][0]['split'])
        self.assertEqual(obj['ipv4']['results'][0]['latency_ms'],8)
        self.assertEqual(obj['ipv4']['results'][0]['first_hop_ttl'],3)
        self.assertEqual(obj['ipv4']['summary']['unknown'],1)
        text=self.run_script('-4','--no-color').stdout
        self.assertNotIn('存在分流',text)
        self.assertIn('无法判定',text)

    def test_repeat_restores_missing_baseline_hop(self):
        self.configure_route_evidence('''if [[ -e "$PROBE_COUNTER" ]]; then
printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 9 9 9 9 0'
else touch "$PROBE_COUNTER"
printf '%s\\n' '1.|-- ??? 100.0 3 0 0 0 0 0' '2.|-- ??? 100.0 3 0 0 0 0 0' '3.|-- 1.1.1.1 0.0% 3 1 1 1 1 0' '4.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'
fi''')
        obj=json.loads(self.run_script('-4','--json').stdout)
        result=obj['ipv4']['results'][0]
        self.assertFalse(result['split'])
        self.assertEqual(result['first_hop'],'203.73.217.1')
        self.assertEqual(result['latency_ms'],9)

    def test_alternating_nonbaseline_hops_remain_unknown(self):
        self.configure_route_evidence('''hop=1.1.1.1
if [[ -e "$PROBE_COUNTER" ]]; then hop=2.2.2.2; else touch "$PROBE_COUNTER"; fi
printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' "2.|-- $hop 0.0% 3 1 1 1 1 0" '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'
''')
        result=json.loads(self.run_script('-4','--json').stdout)['ipv4']['results'][0]
        self.assertIsNone(result['split'])
        self.assertIn('不稳定',result['reason'])

    def test_stable_difference_still_detected(self):
        self.configure_route_evidence("printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 1.1.1.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'")
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertTrue(obj['ipv4']['split_routing_detected'])
        self.assertEqual(obj['ipv4']['results'][0]['comparison'],'repeatable_difference')
        text=self.run_script('-4','--no-color').stdout
        self.assertIn('疑似分流',text)
        self.assertNotIn('被分流到其他出口',text)

    def test_repeat_pins_target_and_protocol(self):
        self.configure_route_evidence('''echo "$*" >> "$PROBE_COUNTER"
printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 1.1.1.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0' ''')
        self.run_script('-4','--json')
        probes=(self.base/'probe.count').read_text().splitlines()
        self.assertEqual(len(probes),2)
        self.assertEqual(probes[0],probes[1])
        self.assertTrue(probes[0].endswith('104.18.33.45'))

    def test_tcp_fallback_cannot_be_compared_to_icmp_baseline(self):
        self.configure_route_evidence('''echo "$*" >> "$PROBE_COUNTER"
if [[ " $* " != *" -T "* ]]; then echo bad-report; exit; fi
printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 1.1.1.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0' ''')
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertIsNone(obj['ipv4']['results'][0]['split'])
        # Only the initial ICMP/TCP pair; no futile extra TCP report.
        self.assertEqual(len((self.base/'probe.count').read_text().splitlines()),2)

    def test_same_asn_different_ip_and_missing_prefix_are_normal(self):
        self.configure_route_evidence('''if [[ "${@: -1}" == 104.18.33.46 ]]; then
printf '%s\\n' '1.|-- ??? 100.0 3 0 0 0 0 0' '2.|-- 203.73.217.2 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.46 0.0% 3 8 8 8 8 0'
else
printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'
fi''')
        self.rules.write_text('AI|example.com|||test\nAI|other.example|||test\n')
        self.stub('getent', '''case "$*" in *google.com*) echo '8.8.8.8 STREAM';; *other.example*) echo '104.18.33.46 STREAM';; *) echo '104.18.33.45 STREAM';; esac''')
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertEqual(obj['ipv4']['route_count'],1)
        self.assertFalse(obj['ipv4']['results'][0]['split'])
        self.assertFalse(obj['ipv4']['results'][1]['split'])
        self.assertEqual(obj['ipv4']['results'][1]['comparison_scope'],'asn')
        self.assertFalse(obj['ipv4']['split_routing_detected'])
        text=self.run_script('-4','--no-color').stdout
        self.assertNotIn('首跳证据不足 / 无法判定',text)
        self.assertIn('可见首跳 ASN 与基准一致',text)

    def test_same_asn_ignores_depth_protocol_and_alternate_responders(self):
        reports=[
            "printf '%s\\n' '1.|-- ??? 100.0 3 0 0 0 0 0' '3.|-- 203.73.217.2 0.0% 3 1 1 1 1 0' '4.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'",
            "printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 203.73.217.2 0.0% 3 1 1 1 1 0' '        203.73.217.3' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'",
            '''if [[ " $* " != *" -T "* ]]; then echo bad-report; exit; fi
printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 203.73.217.2 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0' ''',
        ]
        for probe in reports:
            with self.subTest(probe=probe):
                self.configure_route_evidence('echo "$*" >> "$PROBE_COUNTER"\n'+probe)
                counter=self.base/'probe.count'
                counter.unlink(missing_ok=True)
                obj=json.loads(self.run_script('-4','--json').stdout)
                result=obj['ipv4']['results'][0]
                self.assertFalse(result['split'])
                self.assertEqual(result['comparison_scope'],'asn')
                self.assertEqual(obj['ipv4']['summary']['unknown'],0)
                self.assertLessEqual(len(counter.read_text().splitlines()),2)

    def test_alternate_responders_not_counted_as_split(self):
        self.configure_route_evidence("printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 1.1.1.1 0.0% 3 1 1 1 1 0' '        203.73.217.1' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'")
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertIsNone(obj['ipv4']['results'][0]['split'])

    def test_gapped_reference_cannot_support_different_node_split(self):
        self.configure_route_evidence("printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'",
            "printf '%s\\n' '1.|-- ??? 100.0 3 0 0 0 0 0' '2.|-- 1.1.1.1 0.0% 3 1 1 1 1 0' '3.|-- 8.8.8.8 0.0% 3 1 1 1 1 0'")
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertIsNone(obj['ipv4']['results'][0]['split'])
        self.assertIn('前段未完整回应',obj['ipv4']['results'][0]['reason'])

    def test_stable_gapped_reference_and_same_node_match(self):
        self.configure_route_evidence("printf '%s\\n' '1.|-- ??? 100.0 3 0 0 0 0 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'",
            "printf '%s\\n' '1.|-- ??? 100.0 3 0 0 0 0 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0' '3.|-- 8.8.8.8 0.0% 3 1 1 1 1 0'")
        obj=json.loads(self.run_script('-4','--json').stdout)
        result=obj['ipv4']['results'][0]
        self.assertFalse(result['split'])
        self.assertEqual(result['comparison_scope'],'asn')
        self.assertEqual(result['latency_ms'],8)
        self.assertIn('ASN 与基准一致',result['reason'])
        text=self.run_script('-4','--compact','--no-color').stdout
        self.assertNotIn('仅节点',text)

    def test_tcp_same_exact_node_is_observation_not_full_prefix(self):
        self.configure_route_evidence('''echo "$*" >> "$PROBE_COUNTER"
if [[ " $* " != *" -T "* ]]; then
printf '%s\\n' '1.|-- ??? 100.0 3 0 0 0 0 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0'
else
printf '%s\\n' '1.|-- 10.0.0.1 71.4% 3 1 1 1 1 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 197.5 197.5 197.5 197.5 0'
fi''')
        result=json.loads(self.run_script('-4','--json').stdout)['ipv4']['results'][0]
        self.assertFalse(result['split'])
        self.assertEqual(result['comparison_scope'],'asn')
        self.assertEqual(result['latency_ms'],197.5)
        self.assertEqual(len((self.base/'probe.count').read_text().splitlines()),2)

    def test_same_asn_matches_http_reference_when_mtr_reference_unstable(self):
        self.configure_route_evidence("printf '%s\\n' '1.|-- 10.0.0.1 0.0% 3 1 1 1 1 0' '2.|-- 203.73.217.1 0.0% 3 1 1 1 1 0' '3.|-- 104.18.33.45 0.0% 3 8 8 8 8 0'",
            '''hop=203.73.217.1
if [[ -e "$PROBE_COUNTER" ]]; then hop=203.73.217.2; else touch "$PROBE_COUNTER"; fi
printf '%s\\n' '1.|-- ??? 100.0 3 0 0 0 0 0' "2.|-- $hop 0.0% 3 1 1 1 1 0" '3.|-- 8.8.8.8 0.0% 3 1 1 1 1 0' ''')
        result=json.loads(self.run_script('-4','--json').stdout)['ipv4']['results'][0]
        self.assertFalse(result['split'])
        self.assertEqual(result['comparison_scope'],'asn')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='egress-tests-')
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.bin=self.base/'bin'; self.bin.mkdir()
        self.cache=self.base/'cache'; self.cache.mkdir()
        self.rules=self.base/'rules.conf'
        self.rules.write_text('AI|example.com|||test\nAI|other.example|||test\n')
        self.env={**os.environ,'PATH':str(self.bin)+os.pathsep+os.environ['PATH'],
                  'EGRESS_CACHE':str(self.cache),'EGRESS_RULES':str(self.rules),
                  'MTR_ATTEMPTS':'1','MTR_TIMEOUT':'2','MTR_BUDGET':'5','MTR_CONCURRENCY':'2'}
        self.stub('getent', 'echo "104.18.33.45 STREAM example.com"')
        self.stub('curl', '''case "$*" in
 *-6*) exit 1;;
 *ipinfo.io/*/json*) printf '%s' '{"country":"TW","org":"AS4780 Test ISP"}';;
 *) echo 203.73.217.1;;
esac''')
        self.stub('mtr', '''printf '%s\\n' 'HOST: test Loss% Snt Last Avg Best Wrst StDev' \
 '1.|-- 203.73.217.1 0.0% 3 1.0 2.0 1.0 3.0 0.0' \
 '2.|-- 104.18.33.45 0.0% 3 9.0 9.0 9.0 9.0 0.0' ''')

    def stub(self,name,body):
        file=self.bin/name
        file.write_text('#!/usr/bin/env bash\n'+body+'\n')
        file.chmod(0o755)

    def run_script(self,*args,expected=0,env=None,input=None):
        result=subprocess.run([BASH,str(ROOT/'ip.sh'),*args],env=env or self.env,
            text=True,encoding='utf-8',capture_output=True,timeout=30,input=input)
        self.assertEqual(result.returncode,expected,result.stderr+'\n'+result.stdout)
        self.assertFalse(list(self.cache.glob('.run.*')))
        return result

    def test_json_and_no_ipv6(self):
        result=self.run_script('--json')
        obj=json.loads(result.stdout)
        self.assertFalse(obj['ipv4']['split_routing_detected'])
        self.assertIsNone(obj['ipv6']['split_routing_detected'])
        self.assertEqual(obj['ipv4']['summary']['total'],2)
        self.assertEqual(obj['ipv4']['results'][0]['latency_ms'],9)
        self.assertEqual(json.loads((self.cache/'last.json').read_text()),obj)

    def test_real_loss_layout_through_full_script(self):
        self.env['MTR_FIXTURE']=str(ROOT/'tests/fixtures/mtr-095-loss-report.txt')
        self.stub('mtr','cat "$MTR_FIXTURE"')
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertEqual(obj['ipv4']['summary']['ok'],2)
        self.assertEqual(obj['ipv4']['summary']['down'],0)
        self.assertEqual(obj['ipv4']['results'][0]['first_hop'],'1.1.1.1')
        self.assertEqual(obj['ipv4']['results'][0]['latency_ms'],1.5)

    def test_large_mtr_values_through_json(self):
        self.stub('mtr', "printf '%s\\n' '1.|-- 203.73.217.1 0.0% 3 1028. 1028. 1028. 1028. 0.0' '2.|-- 104.18.33.45 0.0% 3 1234. 1234. 1234. 1234. 0.0'")
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertEqual(obj['ipv4']['summary']['ok'],2)
        self.assertEqual(obj['ipv4']['results'][0]['latency_ms'],1234)

    def test_same_ip_lookup_is_cached(self):
        self.env['LOOKUP_LOG']=str(self.base/'lookup.log')
        self.stub('curl', '''case "$*" in
 *ipinfo.io/*/json*) echo request >> "$LOOKUP_LOG"; echo '{"country":"TW","org":"AS4780 Test ISP"}';;
 *) echo 203.73.217.1;; esac''')
        self.run_script('-4','--json')
        self.run_script('-4','--json')
        self.assertEqual((self.base/'lookup.log').read_text().splitlines(),['request'])

    def test_dual_stack_json(self):
        self.stub('getent', '''case "$*" in
 ahostsv6*) echo '2607:6bc0::10 STREAM example.com';;
 *) echo '104.18.33.45 STREAM example.com';; esac''')
        self.stub('curl', '''case "$*" in
 *ipinfo.io/*/json*) echo '{"country":"TW","org":"AS4780 Test ISP"}';;
 *-6*) echo '2001:4860::1';;
 *) echo '203.73.217.1';; esac''')
        self.stub('mtr', '''case "$*" in
 *-6*) printf '%s\\n' '1.|-- 2001:4860::1 0.0% 3 1.0 2.0 1.0 3.0 0.0' '2.|-- 2607:6bc0:0:0:0:0:0:10 0.0% 3 9.0 9.0 9.0 9.0 0.0';;
 *) printf '%s\\n' '1.|-- 203.73.217.1 0.0% 3 1.0 2.0 1.0 3.0 0.0' '2.|-- 104.18.33.45 0.0% 3 9.0 9.0 9.0 9.0 0.0';; esac''')
        obj=json.loads(self.run_script('--json').stdout)
        for family in ('ipv4','ipv6'):
            self.assertTrue(obj[family]['available'])
            self.assertFalse(obj[family]['split_routing_detected'])
            self.assertEqual(obj[family]['summary']['ok'],2)
            self.assertEqual(obj[family]['results'][0]['latency_ms'],9)
        self.assertEqual(obj['ipv6']['results'][0]['first_hop'],'2001:4860::1')

    def test_hidden_and_failed_are_unknown(self):
        self.stub('mtr', "echo '1.|-- 104.18.33.45 0.0% 3 1.0 9.0 1.0 10.0 0.0'")
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertEqual(obj['ipv4']['summary']['hidden'],2)
        self.assertIsNone(obj['ipv4']['split_routing_detected'])
        self.stub('mtr', "echo '1.|-- ??? 100.0% 3 0.0 0.0 0.0 0.0 0.0'")
        obj=json.loads(self.run_script('-4','--json',expected=2).stdout)
        self.assertEqual(obj['ipv4']['results'][0]['status'],'no_reply')
        self.assertIsNone(obj['ipv4']['results'][0]['latency_ms'])

    def test_parse_and_dns_failures(self):
        self.stub('mtr', "echo 'unrecognized report'")
        obj=json.loads(self.run_script('-4','--json',expected=2).stdout)
        self.assertEqual(obj['ipv4']['results'][0]['status'],'parse_error')
        self.stub('getent','exit 1'); self.stub('nslookup','exit 1')
        obj=json.loads(self.run_script('-4','--json',expected=2).stdout)
        self.assertEqual(obj['ipv4']['results'][0]['status'],'dns_error')

    def test_one_nonbaseline_route_sets_summary_true(self):
        self.stub('curl', '''case "$*" in
 *ipinfo.io/203.73.217.1/json*) echo '{"country":"TW","org":"AS4780 Baseline"}';;
 *ipinfo.io/*/json*) echo '{"country":"US","org":"AS13335 Other ISP"}';;
 *) echo 203.73.217.1;; esac''')
        self.stub('mtr', "printf '%s\\n' '1.|-- 1.1.1.1 0.0% 3 1.0 9.0 1.0 10.0 0.0' '2.|-- 104.18.33.45 0.0% 3 1.0 9.0 1.0 10.0 0.0'")
        obj=json.loads(self.run_script('-4','--json',env={**self.env,'EGRESS_BASE_MODE':'echo'}).stdout)
        self.assertEqual(obj['ipv4']['route_count'],1)
        self.assertTrue(obj['ipv4']['split_routing_detected'])
        self.assertTrue(all(r['split'] for r in obj['ipv4']['results']))

    def test_asn_failure_not_green_or_false(self):
        self.stub('curl', '''case "$*" in *json*|*geoip*|*ipwho.is*) exit 1;; *) echo 203.73.217.1;; esac''')
        obj=json.loads(self.run_script('-4','--json').stdout)
        self.assertIsNone(obj['ipv4']['split_routing_detected'])
        self.assertTrue(all(r['split'] is None for r in obj['ipv4']['results']))
        text=self.run_script('-4','--no-color').stdout
        self.assertIn('ASN 未知',text)
        self.assertNotIn('符合预期',text)

    def test_overlapping_runs(self):
        processes=[subprocess.Popen([BASH,str(ROOT/'ip.sh'),'-4','--json'],env=self.env,
                    text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(2)]
        for p in processes:
            out,err=p.communicate(timeout=30)
            self.assertEqual(p.returncode,0,err)
            self.assertEqual(json.loads(out)['ipv4']['summary']['ok'],2)
        self.assertFalse(list(self.cache.glob('.run.*')))
        json.loads((self.cache/'last.json').read_text())

    def test_bad_arguments_and_empty_category(self):
        for args in (('--only',),('--rules',),('--rules','/missing/rules.conf'),('--only','Absent')):
            with self.subTest(args=args): self.run_script(*args,expected=1)

    def test_menu_low_resource_and_json(self):
        result=self.run_script('-I','--json',input='5\n')
        self.assertEqual(json.loads(result.stdout)['ipv4']['summary']['total'],2)
        result=self.run_script('-I',input='6\n')
        self.assertEqual(json.loads(result.stdout)['ipv4']['summary']['total'],2)
        self.assertIn('请输入',result.stderr)

    def test_compact_keeps_full_json_and_menu_selection(self):
        normal=json.loads(self.run_script('-4','--json').stdout)
        compact=json.loads(self.run_script('-4','--compact','--json').stdout)
        self.assertEqual(normal['ipv4'],compact['ipv4'])
        self.assertEqual(normal['ipv6'],compact['ipv6'])
        result=self.run_script('-I','--no-color',input='0\n')
        self.assertNotIn('路径 ASN 摘要',result.stdout)
        self.assertIn('2 域名',result.stdout)
        self.assertNotIn('example.com',result.stdout.split('线路分流汇总',1)[1])
        self.assertIn('请输入 0-7 [默认1]',result.stderr)

    def test_probe_deadline(self):
        code=PROBE_CODE+'''
MTR_BUDGET=1 MTR_TIMEOUT=10 MTR_ATTEMPTS=4 MTR_COUNT=3 MTR_MAXTTL=30 MTR_NICE=10
resolve_target() { printf '104.18.33.45'; }
first_public_hop -4 example.com
'''
        self.stub('mtr','sleep 20')
        start=time.monotonic()
        result=shell(code,env=self.env,timeout=6)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('__PROBE_ERROR__',result.stdout)
        self.assertLess(time.monotonic()-start,5)

    def test_signal_cleanup_does_not_remove_other_runs(self):
        self.signal_cleanup_case()

    def test_repeat_signal_cleanup_does_not_remove_other_runs(self):
        self.signal_cleanup_case(repeat=True)

    def signal_cleanup_case(self, repeat=False):
        survivor=self.cache/'.run.other-instance'; survivor.mkdir()
        marker=self.base/'worker.pid'
        run_dir=self.cache/'.run.signal-test'; run_dir.mkdir()
        (run_dir/'0').write_text('1.1.1.1\t8\t1.1.1.1\t2,0,0,icmp,104.18.33.45')
        code='set -eu\n'+''.join(function(n) for n in ('run_mtr_group','stop_tree','cleanup_tmp'))+'''
OUTPUT_JSON=1 MTR_CONCURRENCY=1 SPIN_PID="" TMP_V4_RESULTS="" TMP_V6_RESULTS="" FINAL_JSON=""
ACTIVE_WORKERS=(); DOMAINS=(a)
trap 'exit 143' TERM
trap cleanup_tmp EXIT
first_public_hop() { echo "$BASHPID" > "$PID_FILE"; sleep 20; }
run_mtr_group -4 "$RUN_DIR" AI ${REPEAT_FLAG:-} 0
'''
        p=subprocess.Popen([BASH,'-c',code],env={**self.env,'RUN_DIR':str(run_dir),'PID_FILE':str(marker),'REPEAT_FLAG':'--repeat' if repeat else ''},
                           text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline: time.sleep(.05)
            self.assertTrue(marker.exists())
            p.send_signal(signal.SIGTERM)
            out,err=p.communicate(timeout=5)
            self.assertEqual(p.returncode,143,err+out)
            self.assertFalse(run_dir.exists())
            self.assertTrue(survivor.exists())
            pid=int(marker.read_text())
            # Minimal containers may not reap orphaned zombies immediately.
            # A zombie has exited and cannot keep probing or consume CPU.
            state=Path(f'/proc/{pid}/stat')
            if state.exists():
                self.assertEqual(state.read_text().rsplit(')',1)[1].split()[0],'Z')
        finally:
            if p.poll() is None: p.kill(); p.communicate()

    def test_worker_concurrency_and_cleanup(self):
        code='set -eu\n'+''.join(function(n) for n in ('run_mtr_group','stop_tree','cleanup_tmp'))+'''
OUTPUT_JSON=1 MTR_CONCURRENCY=2 SPIN_PID="" TMP_V4_RESULTS="" TMP_V6_RESULTS="" FINAL_JSON=""
ACTIVE_WORKERS=()
DOMAINS=(a b c d e f)
RUN_DIR=$(mktemp -d)
trap cleanup_tmp EXIT
first_public_hop() { sleep 0.3; printf 'done'; }
run_mtr_group -4 "$RUN_DIR" AI 0 1 2 3 4 5
for i in 0 1 2 3 4 5; do [[ $(cat "$RUN_DIR/$i") == done ]] || exit 1; done
'''
        start=time.monotonic(); result=shell(code,env=self.env)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertGreaterEqual(time.monotonic()-start,0.8)

    def test_repeat_workers_are_bounded_and_keep_pinned_probe_arguments(self):
        code='set -eu\n'+''.join(function(n) for n in ('run_mtr_group','stop_tree','cleanup_tmp'))+'''
OUTPUT_JSON=1 SPIN_PID="" TMP_V4_RESULTS="" TMP_V6_RESULTS="" FINAL_JSON=""
ACTIVE_WORKERS=(); DOMAINS=(a b c d e f)
RUN_DIR=$(mktemp -d)
trap cleanup_tmp EXIT
first_public_hop() {
 [[ "$3" == 104.18.33.45 && "$4" == icmp && "$MTR_ATTEMPTS" == 1 ]] || exit 9
 printf '+ %s\\n' "$BASHPID" >> "$EVENTS"
 sleep 0.3
 printf -- '- %s\\n' "$BASHPID" >> "$EVENTS"
 printf verified
}
for i in 0 1 2 3 4 5; do
 printf '1.1.1.1\\t8\\t1.1.1.1\\t2,0,0,icmp,104.18.33.45' > "$RUN_DIR/$i"
done
run_mtr_group -4 "$RUN_DIR" AI --repeat 0 1 2 3 4 5
for i in 0 1 2 3 4 5; do [[ $(cat "$RUN_DIR/$i.repeat") == verified ]] || exit 10; done
'''
        for concurrency,expected_peak in ((1,1),(6,2)):
            events=self.base/f'events-{concurrency}'
            result=shell(code,env={**self.env,'MTR_CONCURRENCY':str(concurrency),'EVENTS':str(events)})
            self.assertEqual(result.returncode,0,result.stderr)
            active=set(); peak=0
            for event in events.read_text().splitlines():
                action,pid=event.split()
                if action=='+': active.add(pid)
                else: active.remove(pid)
                peak=max(peak,len(active))
            self.assertEqual(peak,expected_peak)
            self.assertFalse(active)


if __name__=='__main__': unittest.main(verbosity=2)
