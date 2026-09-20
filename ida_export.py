# IDA Pro 导出脚本 - 在 IDA 中运行 (File -> Script File)
# 导出每个函数为单独的 JSON 文件：<程序名>_<函数名>.json

import idautils
import idc
import json
import ida_hexrays
import os
import re

def export_all_functions():
    total = 0

    # 获取程序名（不含扩展名）
    input_file = idc.get_input_file_path()
    # 输出目录
    output_dir = os.path.splitext(os.path.basename(input_file))[0]
    output_dir = output_dir.replace(' ', '_') + '_ida_export'
    output_dir = os.path.join(os.path.dirname(input_file), output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # 初始化 Hex-Rays
    hexrays_available = ida_hexrays.init_hexrays_plugin()
    if not hexrays_available:
        print("Warning: Hex-Rays decompiler not available")

    for ea in idautils.Functions():
        total += 1
        func_name = idc.get_func_name(ea)
        func_end = idc.get_func_attr(ea, idc.FUNCATTR_END)
        func_size = func_end - ea

        # 获取反编译伪代码
        pseudocode = "Decompilation not available"
        if hexrays_available:
            try:
                cfunc = ida_hexrays.decompile(ea)
                if cfunc:
                    pseudocode = str(cfunc)
                else:
                    pseudocode = "Decompilation failed"
            except Exception as e:
                pseudocode = "Decompilation error: " + str(e)

        # 获取汇编代码
        asm_lines = []
        for head in idautils.Heads(ea, func_end):
            try:
                asm_line = idc.generate_disasm_line(head, 0)
                asm_lines.append({
                    "address": hex(head),
                    "instruction": asm_line
                })
            except:
                pass

        # 构建函数数据
        func_data = {
            "address": hex(ea),
            "name": func_name,
            "size": hex(func_size),
            "pseudocode": pseudocode,
            "assembly": asm_lines
        }

        # 文件名：程序名_函数名.json
        filename = re.sub(r'[^\w\.\-]', '_', func_name)[:128] + '.json'
        filepath = os.path.join(output_dir, filename)

        # 保存单个函数 JSON
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(func_data, f, indent=2, ensure_ascii=False)

        # 进度显示
        if total % 100 == 0:
            print("Processed {} functions...".format(total))

    print("Done! Exported {} functions to {}".format(total, output_dir))

if __name__ == "__main__":
    export_all_functions()