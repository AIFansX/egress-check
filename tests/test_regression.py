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
        if shutil.which('mawk'): variants.append('mawk -W traditional')
        if shutil.which('busybox'): variants.append('busybox awk')
        data=report(row('10.0.0.1'),row('168.95.98.254'),row('104.18.33.45'))
        for variant in variants:
            with self.subTest(awk=variant):
                self.assertEqual(self.parse(data,awk=variant)[0], '168.95.98.254')
                self.assertEqual(self.parse(report(row('fe80::1'),row('2001:4860::1'),
                    row('2607:6bc0:0:0:0:0:0:10')), '2607:6bc0::10', variant)[0], '2001:4860::1')
                self.assertEqual(self.parse(report(row('???','0.0','100.0')),awk=variant)[0], '__NO_REPLY__')

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


class FormatAndRulesTests(unittest.TestCase):
    def test_latency_boundaries(self):
        code=function('set_colors')+function('latency_color')+'''
USE_COLOR=1; set_colors
for n in 49.9 50 200 200.1; do latency_color "$n"; printf '\\n'; done
'''
        self.assertEqual(shell(code).stdout.splitlines(),
                         ['\x1b[32m','\x1b[33m','\x1b[33m','\x1b[38;5;130m'])

    def test_rules_unchanged_and_identical(self):
        block=SOURCE.split("DEFAULT_RULES=$(cat <<'EOF'\n",1)[1].split('\nEOF',1)[0]
        clean=lambda s:[x for x in s.splitlines() if x and not x.startswith('#')]
        rules=clean(block)
        self.assertEqual(rules,clean((ROOT/'rules.conf.example').read_text(encoding='utf-8')))
        self.assertEqual(len(rules),121)
        self.assertEqual(len({r.split('|')[1] for r in rules}),121)

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
        survivor=self.cache/'.run.other-instance'; survivor.mkdir()
        marker=self.base/'worker.pid'
        run_dir=self.cache/'.run.signal-test'; run_dir.mkdir()
        code='set -eu\n'+''.join(function(n) for n in ('run_mtr_group','stop_tree','cleanup_tmp'))+'''
OUTPUT_JSON=1 MTR_CONCURRENCY=1 SPIN_PID="" TMP_V4_RESULTS="" TMP_V6_RESULTS="" FINAL_JSON=""
ACTIVE_WORKERS=(); DOMAINS=(a)
trap 'exit 143' TERM
trap cleanup_tmp EXIT
first_public_hop() { echo "$BASHPID" > "$PID_FILE"; sleep 20; }
run_mtr_group -4 "$RUN_DIR" AI 0
'''
        p=subprocess.Popen([BASH,'-c',code],env={**self.env,'RUN_DIR':str(run_dir),'PID_FILE':str(marker)},
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


if __name__=='__main__': unittest.main(verbosity=2)
