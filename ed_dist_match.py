from functools import lru_cache
import numpy as np
import os
import sys
from os import path

@lru_cache(None)
def edit_dis(s1, s2):
    if s1 == '' or s2 == '':
        return max(len(s1), len(s2))
    if s1[-1] == s2[-1]:
        return edit_dis(s1[:-1], s2[:-1])
    return min(
        edit_dis(s1[:-1], s2), 
        edit_dis(s1, s2[:-1]),
        edit_dis(s1[:-1], s2[:-1])
    ) + 1
    
prefs = [
 'h5-vid-hwt',
 'iot-pentest-cb',
 'art-wrt-eff-prog',
 'sprsec-3x-cb',
 'kali-wrls-pentest-ess',
 'go-dsn-ptn',
 'lrn-cs-dev-gm-unity2021',
 'py-auto-cb',
 'ms-sprcl',
 'hsn-svls-app-go',
 'raspi-andr-pj',
 'h5-blpt-webdev',
 'bg-react',
 'adv-cpp',
 'lrn-py-bd-gm',
 'go-stdlib-cb',
 'js-mvto-es15',
 'py-prog-bp',
 'vue3-ex',
 'dwcs6-mobi-web-dev-h5c3-jqmobi',
 'lrn-linux-bin-anls',
 'ms-spr5',
 'ltnfs-mobi-app-dev-galio',
 'node-ess',
 'lrn-php-data-obj',
 'vuep-qk-st-gd',
 'bd-web-mobi-arcgis-svr-app-js',
 'ms-resp-web-dsn',
 'mtpl-gm-dev-h5',
 'hsn-oop-cs',
 'php8-prog-tip',
 'qt5-cpp-gui-prog-cb',
 'php7-dsal',
 'kali-wrls-pentest-cb',
 'prac-linux-sec-cb',
 'ms-py-sc-sys-adm',
 'adv-cpp-prog-cb',
 'ocs-dkr',
 'flstk-react-pj',
 'hiperf-java9',
 'hsn-linux-adm-az',
 'spark-py-dev',
 'lrn-java-lmd',
 'np-ess',
 'ms-kali-adv-pentest',
 'hsn-pentest-kali-nthtr',
 'hsn-k8s-az',
 'less-webdev-ess',
 'resp-web-dsn-h5c3-2e',
 'cryeng-gm-prog-cpp-cs-lua',
 'hsn-bc-py-dev',
 'php7-prog-cb',
 'eff-py-pentest',
 'ms-andr-dev-kt',
 'mysql8-cb',
 'mst-num-cmp-np',
 'resp-web-dsn-gd-2e',
 'bd-svls-msvc-py',
 'java9-prog-bp',
 'lrn-boost-cpp-lib',
 'ns-ng-mobi-dev',
 'hsn-btc-prog-py',
 'cpp-gui-prog-qt5',
 'prac-py-prog-iot',
 'ctn-opstk',
 'mongo-dt-mdl',
 'cpp-appdev-cdblk',
 'ms-kali-web-pentest',
 'py-pll-prog-cb',
 'gtst-react-vr',
 'lrn-fp-go',
 'js-json-ess',
 'as-cb',
 'bg-dop-dkr',
 'sw-arch-cs9-dn5',
 'node-webdev',
 'pentest-bash-sh',
 'kali2018-win-pentest',
 'ms-svg',
 'lrn-py-net-prog',
 'pytest-qk-st-gd',
 'hsn-sys-prog-go',
 'linux-adm-cb',
 'cpp-dsal-dsn-prin',
 'pyspark-cb',
 'ms-css',
 'ms-go-websvc',
 'hsn-pentest-py',
 'mod-py-cb',
 'crt-yr-own-mysql-db',
 'ins-flask-webdev',
 'rst-java-ptn-best-prac',
 'go-prog-bp',
 '.gitkeep',
 'hsn-bgdt-anlt-pyspark',
 'ws-ess',
 'crt-flt-dsn-wbst',
 'dkr-ws',
 'mean-webdev-2e',
 'go-prog-cb-2e',
 'react16-ess',
 'tbst-dkr',
 'dj-pj-bp',
 'cln-code-cs',
 'hsn-linux-arch',
 'hsn-emb-prog-cpp17',
 'flstk-dev-vue-node',
 'tk-gui-app-dev-cb',
 'hsn-flstk-web-dev-ng6-lrv5',
 'vue3-cb',
 'bd-webapp-flask',
 'mod-py-stlib-cb',
 'h5-fls-dev',
 'lrn-node-mobi-app-dev',
 'sec-dkr',
 'hsn-web-scp-py',
 'lrn-react-ts3',
 'hsn-dsn-ptn-rn',
 'sprmvc-dsn-rw-webapp',
 'ms-as3',
 'k8s-svls-app',
 'ms-cpp-gm-dev',
 'cpl-vue2-web-dev',
 'hsn-go-prog',
 'spark-dl-cb',
 'dop-k8s',
 'lrn-ue-andr-gm-dev',
 'lrn-redis',
 'lrv-st',
 'adv-node-dev',
 'ms-py-net',
 'hsn-sprsec5-rct-app',
 'hsn-etp-auto-py',
 'js-ddd',
 'lrn-dkr',
 'flstk-react-ts-node',
 'js-pj-kid',
 'pgs-webapp-react',
 'linux-util-cb',
 'prof-js',
 'bd-gmf-wbst-php-jq',
 'hsn-js-py-dev',
 'py-algo-trd-cb',
 'bd-vrt-pentest-lab',
 'svls-webapp-react-frbs',
 'mtspl-pentest-cb',
 'cs-dsal',
 'react16-tl',
 'sw-arch-py',
 'flstk-vue2-lrv5',
 'ins-bpst-st',
 'lrn-dj-webdev',
 'nmap-ess',
 'prcd-cont-gen-cpp-gm-dev',
 'gtst-cpp-aud-prog-gm-dev',
 'lrn-pentest-py',
 'aws-pentest',
 'gm-dev-pj-ue',
 'cpp-gm-dev-cb',
 'node-cb',
 'app-dev-qt-crt',
 'vue2-bts4-web-dev',
 'dev-msvc-node',
 'crt-xplat-cs-app-uno-plat',
 'exp-ng',
 'h5-dr-svc-cb',
 'ng6-entrd-webapp',
 'lrn-go-web-prog',
 'cd-dkr-jkn',
 'dj-dsn-ptn-best-prac',
 'h5-gm-dev-ex',
 'swc-ng2',
 'emb-prog-mod-cpp-cb',
 'sprdt',
 'hsn-fp-cpp',
 'lrv-app-dev-bp',
 'vue2-ex',
 'wpk5-uprn',
 'ext-asb',
 'dj11-test-dbg',
 'ue4-scp-cpp-cb',
 'bd-svls-app-py',
 'hsn-unity2020-gm-dev',
 'jsm-js-test-2e',
 'andr-prog-kt-bg',
 'ms-py-fin-2e',
 'hsn-aws-pentest-kali',
 'ms-cncr-go',
 'xplat-dsk-app-dev',
 'rst-java-websvc-sec',
 'andr-dev-kt',
 'react',
 'node-6x-bp',
 'ms-asb-4e',
 'hsn-etp-java-msvc-ecl-mprf',
 'andr-prog-bg-3e',
 'ms-wrls-pentest-hisec-env',
 'lrn-kali2019',
 'e2e-web-test-cprs',
 'k8s-cb-2e',
 'node-ex',
 'kubectl-cli-k8s-nsh',
 'linux-eml',
 'ts-msvc',
 'ms-cpp-mltrd',
 'xplat-dev-qt6-mod-cpp',
 'edr-css',
 'java9-jsh',
 'lrn-np-arr',
 'java-fund',
 'nest-prgs-node-fw',
 'py-pentest-ess',
 'hsn-ml-algo-trd',
 'dkr-k8s-java-dev',
 'lrn-nss-pentest',
 'js-re',
 'fn-cs',
 'mdl-prog-py',
 'fp-js',
 'kali2018-asr-sec-pentest',
 'lrn-bc-prog-js',
 'hsn-sys-prog-cpp',
 'ml-spark',
 'bd-py-rw-app-storm',
 'node-sec',
 'cfg-ipcop-fw',
 'hsn-dsal-py',
 'lrn-py-web-pentest',
 'comptia-linux-crt-gd',
 'gtst-py-iot',
 'storm-bp',
 'cpl-mtspl-gd',
 'ms-ml-pentest',
 'nmap6-net-exp-sec-adt-cb',
 'adv-ts-prog-pj',
 'np-bgn-gd-3e',
 'np-cb-2e',
 'ms-linux-dvc-dvr-dev',
 'hsn-sys-prog-linux',
 'spark-2x-ml-cb',
 'wsl2-tip-trk-tech',
 'ext-jks',
 'h5-gm-dev-impact',
 'h5-webapp-dev-ex',
 'etp-app-dev-ext-spr',
 'lrn-react-hk',
 'ms-linux-net-adm',
 'hsn-hiperf-go',
 'asb-qk-st-gd',
 'web-pentest-kali-3e',
 'ms-linux-sec-hdn',
 'go-webdev-cb',
 'ms-kvm-vrt',
 'ins-kali',
 'bd-lgscl-webapp-ng',
 'mtspl-bc',
 'dkr-aws',
 'lrn-go-prog',
 'sec-net-infra-nmap-nss7',
 'hsn-fin-trd-py',
 '40-algo-shld-know',
 'mongo-fund',
 'prac-asb',
 'cld-ntv-py',
 'adv-pentest-hisec-env',
 'k8s-ws',
 'dkr-win',
 'gtst-k8s',
 'svls-arch-k8s',
 'lrn-pentest',
 'php7-prog-bp',
 'bg-cpp-gm-prog',
 'boost-asio-cpp-net-prog',
 'lrn-cuda-prog',
 'lrn-ionic-2e',
 'mgt-php-dev-gd',
 'ms-win8-cpp-appdev',
 'cpp-hiperf',
 'ms-spark',
 'ms-ccr-py',
 'ms-node',
 'go-web-scr-qk-st-gd',
 'py-pentest-cb',
 'dg-frns-kali',
 'php-ajax-cb',
 'cpl-code-itw-gd-java',
 'mgt-linux-ms-az',
 'ms-flstk-react-web-dev',
 'ng2-cpn',
 'dkr-qk-st-gd',
 'h5-cnv-cb',
 'dsn-nxgen-web-pj-c3',
 'mobi-1st-dsn-h5c3',
 'mod-cpp',
 'hsn-dep-inj-go',
 'ms-cncr-prog-java8',
 'ins-pentest',
 'flask-ex',
 'ms-lrv',
 'lrn-mtspl-exp-dev',
 'bg-php',
 'ms-gui-prog-py',
 'ntv -dkr-cls-swm',
 'lrn-vue2',
 'linux-krn-prog-pt2',
 'k8s-aws',
 'intr-prog',
 'sec-go',
 'hsn-ds-py-ml',
 'mobx-qk-st-gd',
 'cln-code-py',
 'py-gui-prog-cb',
 'oo-js',
 'ms-py',
 'py-test-cb',
 'bg-api-dev-node',
 'exp-cpp-prog',
 'lrn-cs-7d',
 'cdbd-vr-pj-andr',
 'cs7-dncore2-hiperf',
 'react17-dsn-ptn-best-prac',
 'hsn-auto-test-java-bg',
 'h5-gph-dtvz-cb',
 'sw-arch-spr5',
 'hsn-flstk-dev-sprbt2-react',
 'linux-sh-scp-cb',
 'lrn-k8s-sec',
 'h5-gm-dev-gmkr',
 'spr-websvc2-cb',
 'lrn-fuelphp-eff-php-dev',
 'rn-bp',
 'lrn-asb',
 'lrn-llvm12',
 'php-msvc',
 'resp-web-dsn-h5c3-ess',
 'iso-go',
 'java7-new-feat-cb',
 'py3-oop-2e',
 'lrn-h5-crt-fun-gm',
 'webdev-mongo-node',
 'go-sys-prog',
 'lrn-dkr-net',
 'rhel-tbst-gd',
 'bg-cpp-prog',
 'hsn-test-mgt-jira',
 'app-cmp-thk-py',
 'spark-ds',
 'hwt-bd-andr-app-kt',
 'h5-mobii-dev-cb',
 'flask-bp',
 'rn-cb-2e',
 'linux-sh-scp-bc',
 'adv-quant-fin-cpp',
 'bd-vue-app-graphgl',
 'dkr-net-cb',
 'ng2-ex',
 'opstk-adm-asb2',
 'xplat-app-dev-react',
 'js-ex',
 'java11-cb',
 'gtst-dj',
 'cs7-dncore-cb',
 'h5c3-resp-wev-dsn-cb',
 'py-aprt',
 'sw-arch-cpp',
 'hsn-crpt-py',
 'lrn-py-prog-2e',
 'lrn-net-prog-java',
 'ms-ts',
 'dkr-dpdv',
 'ms-storm',
 'k8s-dkr',
 'mnt-dkr',
 'bpst-cb',
 'ng-test-dvn-dev',
 'couchdb-php-webdev-bgd',
 'hsn-dsn-ptn-cs-dncore',
 'linux-dvc-dvr-dev-cb',
 'lrn-spark-sql',
 'exp-py-prog',
 'lrn-web-dev-react-bts',
 'pentest-shcd',
 'vue-qk-st-gd',
 'andr-ndk-bdg-2e',
 'hsn-cpp-gm-ani-prog',
 'linux-krn-prog',
 'cld-ntv-k8s',
 'lrn-php7-hiperf',
 'hsn-fin-mdl-msexcel2019',
 'ms-h5-frm',
 'fn-php',
 'cpp-sys-prog-cb',
 'bd-rst-websvc-php7',
 'javafx-ess',
 'lrn-wasm',
 'mod-lgc-app-php',
 'rsnml-qk-st-gd',
 'ins-andr-sys-dev-hwt',
 'hsn-gm-dev-wasm',
 'app-math-py',
 'dist-cmp-go',
 'cs5-1st-lk',
 'kali-itrs-exp-cb',
 'cld-ntv-app-java',
 'andr-hw-itfc-bglbn-blk',
 'cs-dncore-tdd',
 'lrv-dsn-ptn-best-prac',
 'ms-emb-linux-prog',
 'py-web-scp-cb',
 'mcpy-cb',
 'cpp-ws',
 'lrn-flask-fw',
 'test-dvn-java-dev',
 'asb-pb-ess',
 'scala-spark-bgdt-anlt',
 'h5-mtmd-dev-cb',
 'hsn-msvc-sprbt-sprcl',
 'hsn-prl-prog-cs8-dncore3',
 'iot-prog-pj',
 'hsn-js-hiperf',
 'hsn-hiperf-spr5',
 'kali-eth-hkr-cc',
 'cld-ntv-prog-go',
 'bd-frm-vue',
 'ms-php7',
 'hsn-rbt-prog-cpp',
 'stat-calc-py-ws',
 'py-gui-prog',
 'fp-py',
 'java7-cncr-cb',
 'ms-fst-web-php',
 'spark-cb',
 'hsn-web-pentest-mtspl',
 'ins-mtspl',
 'web-dev-bts4-ng2',
 'hsn-k8s-win',
 'hsn-etp-app-dev-py',
 'lrn-kafka-2e',
 'prac-bgdt-anlt',
 'lrn-linux-sh-scp',
 'prst-php-dct-orm',
 'linux-dvc-dvr-dev',
 'ms-dj',
 'node-hiperf',
 'mdl-prog-php7',
 'ue4-vr-pj',
 'dmst-oop-cpp',
 'spr-msvc',
 'lrn-qt5',
 'lrn-andr-frns',
 'cpp-clg',
 'linux-net-prof',
 'bd-rst-websvc-spr5',
 'vue-cli3-qk-st-gd',
 'dop-25-tk',
 'ms-linux-sh-scp',
 'algo-shtsl-py',
 'mongo-cb',
 'hsn-nuxt-web-dev',
 'spr-itg-ess',
 'bd-dtdvn-app-danfo',
 'ms-linux-krn-dev',
 'linux-sys-prog-tech',
 'vue2-cb',
 'effls-cld-ntv-app-dev-skfd',
 'vue2-dsn-ptn-best-prac',
 'bd-svls-py-websvc-zappa',
 'lrn-cs-prog',
 'lgscl-ml-spark',
 'react-rn-2e',
 'adv-js',
 'adv-infra-pentest',
 'hsn-swe-py',
 'hsn-dsal-js',
 'exp-cpp',
 'prac-iot-js',
 'fund-linux',
 'prac-node-red-prog',
 'pentest-raspi',
 'rst-webapi-dsn-node10',
 'arch-linux-env-stp-hwt',
 'lrn-java-bd-andr-gm',
 'rhel8-adm',
 'hsn-cicd',
 'mean-qk-st-gd',
 'ms-py-net-sec',
 'andr-gm-dev-hb',
 'wk-linux',
 'cpp-rct-prog',
 'ms',
 'lrn-cpp-bd-gm-ue4',
 'lrn-helm',
 'net-auto-cb',
 'ml-algo-trd',
 'ms-dkr-3e',
 'hsn-msvc-k8s',
 'dkr-cb',
 'lrn-flink',
 'cln-code-js',
 'test-vue-cpn-jest',
 'ms-js-dsn-ptn',
 'react-rtr-qk-st-gd',
 'lrn-ng',
 'ts2-ng-dev',
 'hsn-gpu-prog-py',
 'lrn-node-dev',
 'rct-prog-js',
 'cffs-prog-jq-els-node',
 'lrv-app-dev-cb',
 'cs7-dncore2-bp',
 'lrn-dkr-pt2',
 'mod-js-webdev-cb',
 'ms-k8s',
 'drupal-crt-blg',
 'ms-flask',
 'ng-dsn-ptn',
 'lrn-linux-qk',
 'ms-pma34-eff-mysql-mgt',
 'rt-anlt-storm-csdr',
 'mlt-trd-cs5-cb',
 'k8s-bk',
 'lrn-rct-prog-java8',
 'hsn-mqtt-prog-py',
 'lrn-3js',
 'ms-sw-test-junit5',
 'k8s-dev',
 'lrn-cpp-fp',
 'bd-dj20-webapp',
 'ng-cb',
 'prof-c3',
 'web-dev-ng-bts',
 'ms-linux-adm',
 'ins-mrt-h5c3-hwt',
 'dpl-dkr',
 'py-dg-frns-cb',
 'asb-cfg-mgt',
 'node-ui-test',
 'java-prog-bg',
 'ggl-web-tk-gwt',
 'ms-spr-app-dev',
 'hsn-dkr-msvc-py',
 'ms-js-fp',
 'mysql8-adm-gd',
 'mysql-mgt-adm',
 'lrn-emb-linux-yocto-pj',
 'ms-mongo-4x',
 'h5-iph-webapp-dev',
 'bd-rst-websvc-go',
 'webapp-dev-yii-php',
 'ms-ml-spark-2x',
 'arcgis-js-dev-ex',
 'ms-spark-ds',
 'boost-cpp-appdev-cb-2e',
 'ms-oo-py',
 'java-se7-std-gd',
 'ms-cpp-prog',
 'ms-centos7-linux-svr',
 'hsn-app-pentest-bpst',
 'gtst-h5-ws-prog',
 'prac-mobi-frns',
 'k8s-cpl-dop-cb',
 'ins-spr-andr-st',
 'iot-prog-js',
 'dj3-webdev-cb-4e',
 'prac-web-dsn',
 'ng-ui-dev-primeng',
 'xmr-frm-pj',
 'py-web-pentest-cb',
 'php-app-dev-ntbn',
 'ms-py-re',
 'lrn-kt-bd-andr-app',
 'cs10-dn6-mod-xplat-dev',
 'andr-sqlite-ess',
 'ms-php-dsn-ptn',
 'linux-sh-scp-ess',
 'solr-php-intg',
 'gtst-py',
 'vue2-web-dev-pj',
 'bg-cs7-hsn'
]

docs = [
'40-algo-every-prog-should-know',
'app-math-py',
'get-start-py-iot',
'get-start-py',
'handson-btc-prog-py',
'handson-crypto-py',
'handson-dsal-py',
'handson-enter-auto-py',
'handson-gpu-prog-py-cuda',
'iot-prog-proj',
'learn-py-build-game',
'learn-py-net-prog',
'learn-scrapy',
'lmpythw-zh',
'master-gui-prog-py',
'master-py-fin',
'master-py-net-sec',
'master-py-net',
'master-py-script-sys-admin',
'modern-py-cb',
'modern-py-std-lib-cb',
'py-auto-cb',
'py-digi-fore-cb',
'py-dist-comp',
'py-gui-prog-cb',
'py-gui-prog',
'py-paral-prog-cb',
'py-prog-blueprint',
'py-web-scrape-cb',
'pytest-quick-start-guide',
'stat-calc-py-workshop',
'think-py-2e-zh',
'tkinter-gui-app-dev-cb',
]

def most_sim(name, li):
    dists = [edit_dis(name, it) for it in li]
    minidx = np.argmin(dists)
    return li[minidx]
    
def most_sim_li(li1, li2, full=False):
    li1_most_sim = {it:most_sim(it, li2) for it in li1}
    li2_sub = set(li1_most_sim.values())
    li2_most_sim = {it:most_sim(it, li1) for it in li2_sub}
    matches = [
        [it1, it2]
        for it1, it2 in li1_most_sim.items()
        if li2_most_sim.get(it2) == it1
    ]
    if full:
        li1_sub = {m[0] for m in matches}
        li2_sub = {m[1] for m in matches}
        matches += [
            [it, '']
            for it in li1
            if it not in li1_sub
        ]
        matches += [
            ['', it]
            for it in li2
            if it not in li2_sub
        ]
    return matches
    
def match_dirs(dir1, dir2):
    fnames1 = [
        n.split('_')[0]
        for n in os.listdir(dir1)
        if path.isdir(path.join(dir1, n)) or n.endswith('.yaml') or n.endswith('.md')
    ]
    fnames2 = [
        n.split('_')[0]
        for n in os.listdir(dir2)
        if path.isdir(path.join(dir2, n)) or n.endswith('.yaml') or n.endswith('.md')
    ]
    return most_sim_li(list(set(fnames1)), list(set(fnames2)), True)

def main():
    dir1 = sys.argv[1]
    dir2 = sys.argv[2]
    print(match_dirs(dir1, dir2))

if __name__ == '__main__': main()    