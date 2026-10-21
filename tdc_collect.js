#!/usr/bin/env node
/**
 * tdc_collect.js — 在本地运行腾讯 tdc.js，生成 cap_union_new_verify 所需的加密参数。
 *
 * tdc.js 是腾讯防水墙(验证码)的设备指纹/行为采集脚本，由页面 iframe 从
 *   https://ca.turing.captcha.qcloud.com/tdc.js?app_data=<sid>&t=<ts>
 * 加载。它暴露 window.TDC，其中：
 *   TDC.getInfo() -> { info: <176B base64 设备指纹>, tokenid: <int> }
 *   TDC.getData() -> URL 编码的 base64 密文   ← /cap_union_new_verify 的 collect 参数
 *   TDC.setData(key, val)                     ← 注入 uid 等附加数据
 *   TDC.clearTc()
 *
 * getData() 的产物结构（见 tdc_anls.md）:
 *   encodeURIComponent( base64( concat( b64(24B), b64(96B), b64(288B), b64(16B) ) ) )
 *   底层为 XXTEA 分块加密 (delta = 0x9E3779B9)，输出固定 16B 前缀 + 指纹/数据可变区。
 *
 * 用法:
 *   node tdc_collect.js                # JSON: {collect, info, tokenid}
 *   node tdc_collect.js --data         # 仅打印 collect (URL 编码的 base64)
 *   node tdc_collect.js --info         # 仅打印 getInfo().info 的 base64
 *   node tdc_collect.js --uid=xyz      # setData('uid', 'xyz') 后再取
 *   node tdc_collect.js --raw          # collect 不解 URL 编码
 *
 * Python 调用示例 (嵌入 agnes_create.py):
 *   import subprocess, json
 *   out = subprocess.run(['node', 'tdc_collect.js'], capture_output=True, text=True).stdout
 *   j = json.loads(out)
 *   collect, info, tokenid = j['collect'], j['info'], j['tokenid']
 *
 * 依赖: jsdom (项目 node_modules 已有)。mock 了 canvas 指纹以保证可复现。
 */
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const uid = (args.find(a => a.startsWith('--uid=')) || '').split('=')[1] || '';
const want = args.includes('--data') ? 'data' : args.includes('--info') ? 'info' : 'json';
const raw = args.includes('--raw');

let JSDOM;
try { JSDOM = require('jsdom').JSDOM; }
catch (e) { console.error('需要 jsdom: 在项目目录执行 npm install jsdom'); process.exit(1); }

const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
  url: 'https://ca.turing.captcha.qcloud.com/',
  referrer: 'https://platform.agnes-ai.com/login',
  contentType: 'text/html',
  pretendToBeVisual: true,
  runScripts: 'outside-only',
});
const w = dom.window;

// ---- 最小 canvas 2D 指纹 mock（返回固定值；真实浏览器会用 WebGL/font/canvas 哈希）----
w.HTMLCanvasElement.prototype.getContext = function () {
  return {
    canvas: this, fillRect(){}, clearRect(){}, getImageData(){ return { data: new Uint8Array(4), width: 300, height: 150 }; },
    putImageData(){}, drawImage(){}, createLinearGradient(){ return { addColorStop(){} }; }, createRadialGradient(){ return { addColorStop(){} }; },
    measureText(){ return { width: 10 }; }, fillText(){}, strokeText(){}, beginPath(){}, moveTo(){}, lineTo(){}, arc(){}, fill(){},
    stroke(){}, save(){}, restore(){}, translate(){}, scale(){}, rotate(){}, transform(){}, setTransform(){}, clip(){},
    closePath(){}, rect(){}, font: '', fillStyle: '', strokeStyle: '', globalAlpha: 1, lineWidth: 1,
    textAlign: 'left', textBaseline: 'alphabetic',
  };
};
w.HTMLCanvasElement.prototype.toDataURL = function () { return 'data:image/png;base64,fakecanvas'; };

const src = fs.readFileSync(path.join(__dirname, 'tdc.js'), 'utf8');
w.eval(src);

if (uid) { try { w.TDC.setData('uid', uid); } catch (e) {} }

if (want === 'data') { process.stdout.write(raw ? decodeURIComponent(w.TDC.getData()) : w.TDC.getData()); }
else if (want === 'info') { process.stdout.write(w.TDC.getInfo().info); }
else {
  const info = w.TDC.getInfo();
  const collect = w.TDC.getData();
  process.stdout.write(JSON.stringify({ collect, info: info.info, tokenid: info.tokenid }));
}