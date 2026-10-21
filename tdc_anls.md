# tdc.js — 腾讯防水墙 `/cap_union_new_verify` 接口调用逻辑与参数加密分析

> 分析对象：`D:\src\doctool\tdc.js`（78,080 字节，单行）
> 生成日期：2026-10-22
> 配套资料：`_tdc_analysis/`（反汇编、运行时 trace、字符串表）、`tdc_collect.js`（可直接复用 worker）

---

## 0. 结论速览

- **`tdc.js` 是腾讯防水墙(验证码)的设备指纹 / 行为采集脚本**，由验证码 iframe 通过 `tdc_path` 字段动态加载，暴露一个全局对象 `window.TDC`。
- 它**不直接请求 `/cap_union_new_verify`**，而是为验证码主流程生成提交参数所需的**加密指纹数据**。
- `TDC.getData()` 的输出，就是 `/cap_union_new_verify` 提交参数里的 **`collect`** 字段（已与本地抓包 `agnes_vcode.txt` 比对确认格式一致）。
- 加密算法：**XXTEA 变体**（delta `0x9E3779B9` = 2654435769，已在 VM 操作数中直接命中），输出为**多段 base64 拼接 → URL 编码**。
- 结构上可观测：**固定 16 字节前缀 + 指纹/数据可变区 + 尾部固定块**；设备指纹、UA、注入的 uid 都会落在特定字节块上，且**同一环境完全可复现**（固定随机种子 + 时间即可稳定输出）。

---

## 1. 接口调用逻辑（完整链路）

根据本地抓包 `agnes_vcode.txt` / `preh_live.raw` 与 `tdc.js` 分析，`/cap_union_new_verify` 处于一条典型的腾讯验证码流程末端：

```
业务页(如 platform.agnes-ai.com/login)
  │  加载 tcaptcha-frame
  ▼
GET /cap_union_prehandle?aidd=189979000&...&callback=_aq_xxx
  │ 返回 JSONP: {state:1, sess:"s0...", subcapclass:"1408",
  │            data.comm_captcha_cfg.tdc_path:"/tdc.js?app_data=<sid>&t=<ts>",
  │            data.dyn_show_info.img_url / sprite_url, pow_cfg:{prefix,md5}, ...}
  ▼
加载 tdc.js  ←──── 本文件。暴露 window.TDC
  │
  ▼
下载题目图 GET /cap_union_new_getcapbysig?img_index=0/1&image=...&sess=...
  │（bg 大图 + sprite 缺口/点选小图）
  ▼
用户解题 → 得到点击坐标（点选式 DynAnswerType_POS）或滑动轨迹
  │
  ▼
POST https://ca.turing.captcha.qcloud.com/cap_union_new_verify
  │  表单参数（URL 编码）:
  │    collect    = TDC.getData()          ← 本文件产物（设备指纹密文）
  │    tlg        = collect 解码后长度     ← 观察值 1784 == len(url-decode(collect))
  │    eks        = 另一段加密指纹(176B)   ← 与 getInfo().info 等长但内容独立
  │    sess       = prehandle 返回的 sess
  │    ans        = [{"elem_id":1,"type":"DynAnswerType_POS","data":"260,274"},...]
  │    pow_answer = <prefix>#<n>            ← 由 pow_cfg.prefix 做 md5 碰撞
  │    pow_calc_time
  ▼
响应 {errorCode:"0", randstr:"@9nx", ticket:"tr03...", errMessage:"", sess:""}
  │
  ▼
业务后端用 ticket + randstr 二次校验
```

**重点**：`collect` 字段在 `agnes_create.py` 的 `solve_captcha()` 里目前是硬编码 `"TODO"`，本分析给出 `tdc_collect.js` 来填充它。

---

## 2. `tdc.js` 代码结构

文件主体是一段**腾讯混沌混淆（TENCENT CHAOS）虚拟机**：

```
window._ghGjWRgeDbBaceeSncKdHcbjHnBmhGDX = function(){ return new Date() };      // Date.now() 包装
window._nikQgmHJBMkVQOgaOHekZgKUgHkOkCJZ = function(a,b){ return Date[a].apply(Date,b) };
window.WjOSMcXYWOMRdVFPXHNDHWBamfZFQUDl  = '<236 字符 base64>';                  // = getInfo().info 的静态部分
var __TENCENT_CHAOS_STACK = function(){
    function __TENCENT_CHAOS_VM(w,E,T,I,g,j,U,z){ ... }   // 解释器
    for(var D=[function(){...},...];;)try{ ... }            // opcode 表（70 个 handler）
    ...
}(<两个数组>)
```

- **opcode 表 D**：70 个 `function(){...}` 处理器，语义包含 `>=, ===, <<, >>, ^, &, |, +, *, apply, new, closure 构造, strcat 构造字符串` 等，是自研 bytecode 解释器。
- **两个输入数组**：
  1. 一串 base64 程序串（`g(x)` 解出后约 52,954 字节），
  2. 操作数数组 `[5,1518,303,...,2366 项]`，两者按"位置-值"交错出最终指令流 A（54,137 项）。
- 最终导出的全局对象只有 **`window.TDC`**。

> 静态反汇编产物见 `_tdc_analysis/vm_disasm.txt`（5,617 条指令，含 closure 常量展开）。

### TDC 对象（运行时确认）

```
TDC = {
  getInfo() -> { info: "<236字符 base64>", tokenid: <int> }
  getData() -> "<URL 编码的 base64>"     // 即 collect
  setData(k,v)                            // 注入 uid 等附加数据（影响 getData 输出）
  clearTc()
}
```

`getInfo()` 每次调用 `info` 字段恒定（= 文件头 `WjOS...` 常量），`tokenid` 形如 `1301654072:1792593280`（随机数:时间戳），对应 cookie `TDC_itoken`。

---

## 3. 参数加密方式

### 3.1 `TDC.getData()` → `collect` 的加密管线

```
明文(采集数据 JSON, 含 {"cd":[...]} 等) 
   → XXTEA 分块加密 (delta=0x9E3779B9)
   → 若干段 base64（观测到 4 段：btoa(24B)+btoa(96B)+btoa(288B)+btoa(16B)）
   → 拼接后整体再 encodeURIComponent
```

### 3.2 加密特征证据

| 证据 | 说明 |
|---|---|
| VM 操作数含 `2654435769` | `0x9E3779B9`，TEA/XXTEA 家族标准 delta |
| 运行时高频立即数 `84941944608` | = `2654435769 × 32`，即 XXTEA 循环里 delta 的累积上界（delta×n） |
| `1579030` / `789506` 成对出现 | TEA 变体中间常量 |
| 输出逐 16 字节块独立变化 | 改 uid 只影响块 1/12/24/26，其余块完全不变 → 分块(ECB 风格)加密 |
| 固定随机+固定时间 → 输出完全可复现 | 说明加密**确定性**、key 为编译期常量，便于离线复现 |

### 3.3 字节块布局（黑盒实验）

- **前缀**：固定 `threYf4Y+rLCOpPg5lNub`（22 个 base64 字符 = 16 字节 `b61ade61fe18fab2...`），各环境一致。
- **指纹区**：改变 UA / navigator 属性 → 中部约 16 字节块整体变化，且**密文总长随指纹变长**（真实浏览器采集更多 → collect 更长，与抓包 1784 字符吻合）。
- **注入区**：`setData('uid','x')` → 命中块 1、12、24、26（其中块 24 前半 = uid 明文区，后半为固定尾巴 `4b13f0ca...`）。
- **校验尾**：末尾有随内容变化的完整性块（block 26 随注入长度改变并增长）。

### 3.4 `getInfo().info`（176 字节，以 `XX` 开头）

- 解码后熵 ~6.75 bit/byte，非纯文本；开头 `58 58`（`XX`）为协议头。
- 内容是**预先生成的设备指纹密文**，静态固化在脚本头（`WjOS...` 常量），与 `getData()` 的动态密文同源。
- `eks`（verify 里的另一段 176B 加密指纹）与 `info` **等长但字节独立**，说明两者是同一加密框架下的不同数据（`eks` 不含静态头）。

---

## 4. 运行时采集与反自动化检测

通过反汇编出的字符串表（`_tdc_analysis/strings.txt`，160 项）确认，`tdc.js` 不仅加密，还做了大量**浏览器环境探测与自动化检测**：

- **WebDriver/Selenium**：`navigator.webdriver`、`$cdc_asdjflasutopfhvcZLmcfl_`、`__webdriver_script_fn`、`fxdriver_id`、`__fxdriver_unwrapped`、`domAutomation`、`ubot`
- **PhantomJS**：`window._phantom` / `callPhantom` / UA 正则
- **Zombie / CasperJS**：`Zombie` vendor/appName、`CasperError`、`casper`、`patchRequire`
- **DOM 无序化检测**：`document.createElement('div')` + `insertBefore` + `cloneNode` + `outerHTML`，比较节点顺序是否被浏览器"改正"（webdriver 会破坏原生顺序）
- **iframe 内嵌检测**：`document.createElement('iframe')` + `contentWindow`，`inIframe`
- **cookie / storage**：`TDC_itoken`、`sessionStorage`、`localStorage`，`et`/`etGuid`（事件采集）
- 数据格式：`{"cd":[...]}`、`sd`、`DynAnswerType_POS` 等字段名

这解释了为何**本地 jsdom mock 跑出的 collect 比真实浏览器短**：mock 环境少采集了 canvas/WebGL/字体等真实指纹。但结构、加密、格式完全一致。

---

## 5. 本地验证（可复现步骤）

```bash
node tdc_collect.js             # JSON: {collect, info, tokenid}
node tdc_collect.js --data      # 仅 collect
node tdc_collect.js --uid=xyz   # 注入 uid
```

已做实验记录：

| 实验 | 结果 |
|---|---|
| 固定 `Math.random` + `Date.now` | `getData()` 输出**逐字节可复现**（deterministic） |
| 覆盖 `window.WjOS...` 常量 | `getInfo().info` 与 `getData()` 均不受影响（常量编译进 VM） |
| 注入 `setData('uid', ...)` | 精确命中块 1/12/24/26；密文总长随 uid 变长 |
| 更换 UA（Win/Chrome vs iPhone/Safari） | 中部指纹块整体变化、长度变化，前缀/尾块不变 |
| 与抓包 `collect` 比对 | 同为 URL 编码的纯 base64；`tlg == len(decodeURIComponent(collect))` |

---

## 6. 复用方案：接入 `agnes_create.py`

`agnes_create.py` 的 `solve_captcha()` 中：

```python
collect = "TODO"   # ← 已接入 tdc_collect.js
```

替换为（已完成，并端到端实测通过）：

```python
import subprocess, json

def tdc_collect(uid=""):
    cmd = ["node", "tdc_collect.js"] + ([f"--uid={uid}"] if uid else [])
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out)   # {"collect":..., "info":..., "tokenid":...}
```

### 实测结果（2026-10-22）

`python agnes_create.py --solve` 完整跑通：

```
模板匹配 -> 三个点击点: (290,120) (279,280) (129,199)
PoW:       prefix=e8989caad44c4980#   n=14202  answer=0000b31d7855ff1c#14202  15ms
verify:    errorCode=0  ticket=tr03RbEs...**  randstr=@khk
```

- **`collect`** = `tdc_collect()` 输出（TDC.getData()，XXTEA 密文，URL 编码 base64）。
- **`tlg`** = `len(decodeURIComponent(collect))`（与抓包 `tlg=1784` 语义一致）。
- **`eks`** = 用 `getInfo().info` 兜底，实测服务端接受（本场景未做严格一致性校验）。
- **`pow_answer`** = `md5(prefix + str(n))[:16] + '#' + str(n)`，`leading=4` 个前导零，约 0.1~0.2s 解出；`pow_calc_time` = 求解毫秒数。
- **`ans`** = 3 个 `DynAnswerType_POS` 点选坐标的 JSON（背景逻辑尺寸 `672x480` 像素）。

> PoW 具体变换可能随版本微调；若线上 4 位前导零不通过，将 `pow_solve(leading)` 调大或对照真实 `pow_answer` 在线校准。

### 局限与提示

- 本地 mock 的 canvas/WebGL 指纹是固定假值，若服务端对 `collect` 做严格的环境一致性校验，可能被判异常；**真实指纹建议直接在浏览器加载真实 `tdc.js` 抓取**。
- `eks` 与 `tlg` 不在 `tdc.js` 的 TDC 对象中生成（`eks` 与 `info` 同框架、等长但内容独立；`tlg` 为 `collect` 解码后长度）。
- 本脚本仅用于学习/自动化测试合法场景。

---

## 7. 文件清单

| 文件 | 说明 |
|---|---|
| `tdc.js` | 被分析对象（腾讯防水墙 tdc 脚本） |
| `tdc_collect.js` | 可直接复用的 Node worker |
| `_tdc_analysis/vm_disasm.txt` | VM 静态反汇编（5,617 条指令） |
| `_tdc_analysis/strings.txt` / `all_strings.json` | 反汇编还原的 160 个字符串常量 |
| `_tdc_analysis/getData_imm_trace.txt` | `getData()` 运行时立即数 trace（32k 条，含 XXTEA 常量） |
| `_tdc_analysis/extract_strings.js` | 字符串提取脚本 |
| `agnes_vcode.txt` | 本地抓包（prehandle → verify → ticket 全流程参考） |
