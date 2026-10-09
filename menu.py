#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git 提交统计 —— 右键菜单 安装/卸载 工具（M3）

支持 Windows 与 macOS：

    python menu.py                     # 安装（按当前系统）
    python menu.py --uninstall         # 卸载
    python menu.py --dry-run           # 只打印将要做的事，不真正写入
    python menu.py --name "我的菜单"   # 自定义菜单显示名（默认「Git 提交统计」）

实现方式：
- Windows：写注册表 HKEY_CURRENT_USER\\Software\\Classes\\Directory\\shell（当前用户，无需管理员）。
- macOS：写一个 Automator 快速操作到 ~/Library/Services/（Finder 右键 → 快速操作）。
         macOS 部分未经真机验证，失败时会打印手工安装步骤。
"""

import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_PY = os.path.join(HERE, "run.py")
MENU_LABEL = "Git 提交统计"


def force_utf8():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


def pythonw_path():
    exe = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return exe if os.path.isfile(exe) else sys.executable


# ============================================================ Windows
def _delete_key_recursive(key, sub_key):
    import winreg
    try:
        with winreg.OpenKey(key, sub_key, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            while True:
                try:
                    name = winreg.EnumKey(k, 0)
                    _delete_key_recursive(key, sub_key + "\\" + name)
                except OSError:
                    break
        winreg.DeleteKey(key, sub_key)
    except FileNotFoundError:
        pass


def install_windows(dry_run=False, label=MENU_LABEL):
    import winreg
    pyw = pythonw_path()
    cmd = '"%s" "%s" "%%1"' % (pyw, RUN_PY)             # 文件夹：%1 为选中目录
    cmd_bg = '"%s" "%s" "%%V"' % (pyw, RUN_PY)          # 空白处：%V 为当前目录
    cmd_code = '"%s" "%s" "%%1" "--code"' % (pyw, RUN_PY)
    cmd_code_bg = '"%s" "%s" "%%V" "--code"' % (pyw, RUN_PY)

    entries = [
        (r"Software\Classes\Directory\shell\GitStats", cmd, label),
        (r"Software\Classes\Directory\Background\shell\GitStats", cmd_bg, label),
        (r"Software\Classes\Directory\shell\GitStatsCode", cmd_code, "代码详情统计"),
        (r"Software\Classes\Directory\Background\shell\GitStatsCode", cmd_code_bg, "代码详情统计"),
    ]
    for key_path, command, lbl in entries:
        if dry_run:
            print("[dry-run] 写 HKCU\\%s  名称=%s  命令=%s" % (key_path, lbl, command))
            continue
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, lbl)
        winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, '"%s",0' % pyw)
        c = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path + r"\command")
        winreg.SetValueEx(c, "", 0, winreg.REG_SZ, command)
        winreg.CloseKey(c)
        winreg.CloseKey(k)
    print("已安装右键菜单（Windows，当前用户）：「%s」与「代码详情统计」。" % label)


def uninstall_windows(dry_run=False):
    for key_path in (
        r"Software\Classes\Directory\shell\GitStats",
        r"Software\Classes\Directory\Background\shell\GitStats",
        r"Software\Classes\Directory\shell\GitStatsCode",
        r"Software\Classes\Directory\Background\shell\GitStatsCode",
    ):
        if dry_run:
            print("[dry-run] 删除 HKCU\\%s" % key_path)
            continue
        _delete_key_recursive(__import__("winreg").HKEY_CURRENT_USER, key_path)
    if not dry_run:
        print("已卸载右键菜单（Windows）。")


# ============================================================ macOS
def install_macos(dry_run=False, label=MENU_LABEL):
    services = os.path.expanduser("~/Library/Services")
    wf = os.path.join(services, "GitStats.workflow")
    contents = os.path.join(wf, "Contents")

    info_plist = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>NSServices</key>
  <array>
    <dict>
      <key>NSMenuItem</key>
      <dict><key>default</key><string>%(label)s</string></dict>
      <key>NSMessage</key>
      <string>runWorkflowAsService</string>
      <key>NSRequiredContext</key>
      <dict>
        <key>NSApplicationIdentifier</key><string>com.apple.finder</string>
        <key>NSServicesIncludesFileNames</key><true/>
      </dict>
      <key>NSSendFileTypes</key>
      <array><string>public.folder</string></array>
    </dict>
  </array>
</dict>
</plist>
""" % {"label": label}

    # 说明：document.wflow 是 Automator 的归档格式，此处为尽力而为的最小实现，未经真机验证。
    document_wflow = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>AMApplicationBuild</key><string>521</string>
  <key>AMApplicationVersion</key><string>2.10</string>
  <key>AMDocumentVersion</key><string>2</string>
  <key>actions</key>
  <array>
    <dict>
      <key>action</key>
      <dict>
        <key>AMAccepts</key>
        <dict>
          <key>Container</key><string>List</string>
          <key>Optional</key><true/>
          <key>Types</key><array><string>com.apple.cocoa.path</string></array>
        </dict>
        <key>AMActionVersion</key><string>2.0.3</string>
        <key>AMApplication</key><array><string>Automator</string></array>
        <key>AMBundleIdentifier</key><string>com.apple.RunShellScript</string>
        <key>AMCanShowSelectedItemsWhenRun</key><true/>
        <key>AMParameterProperties</key>
        <dict>
          <key>COMMAND_STRING</key><dict><key>savedValueType</key><string>default</string></dict>
          <key>CheckedForUserDefaultShell</key><dict><key>savedValueType</key><string>checked</string></dict>
          <key>inputMethod</key><dict><key>savedValueType</key><string>arguments</string></dict>
          <key>shell</key><dict><key>savedValueType</key><string>default</string></dict>
          <key>source</key><dict><key>savedValueType</key><string>text</string></dict>
          <key>COMMAND_STRING</key><dict><key>savedValueType</key><string>default</string></dict>
        </dict>
        <key>AMProvides</key><dict><key>Container</key><string>List</string><key>Types</key><array><string>com.apple.cocoa.string</string></array></dict>
        <key>ActionBundlePath</key><string>/System/Library/Automator/Run Shell Script.action</string>
        <key>ActionName</key><string>Run Shell Script</string>
        <key>ActionParameters</key>
        <dict>
          <key>COMMAND_STRING</key><string>python3 "%(run)s" "$@"</string>
          <key>inputMethod</key><integer>1</integer>
          <key>shell</key><string>/bin/bash</string>
          <key>source</key><string></string>
        </dict>
      </dict>
      <key>isViewVisible</key><true/>
      <key>position</key>
      <dict><key>y</key><integer>0.0</integer></dict>
    </dict>
  </array>
  <key>connectors</key><dict/>
  <key>workflowMetaData</key>
  <dict>
    <key>serviceInputTypeIdentifier</key><string>com.apple.Automator.fileSystemObject.folder</string>
    <key>serviceOutputTypeIdentifier</key><string>com.apple.Automator.nothing</string>
    <key>serviceProcessesInput</key><integer>0</integer>
  </dict>
</dict>
</plist>
''' % {"run": RUN_PY, "label": label}

    if dry_run:
        print("[dry-run] 写 Automator 快速操作到 %s" % wf)
        print("[dry-run] 命令：python3 %s \"$@\"" % RUN_PY)
        print("[dry-run] 写 Automator 快速操作到 %s（命令：python3 %s \"$@\" --code）"
              % (os.path.join(services, "GitStatsCode.workflow"), RUN_PY))
        return

    os.makedirs(contents, exist_ok=True)
    with open(os.path.join(contents, "Info.plist"), "w", encoding="utf-8") as f:
        f.write(info_plist)
    with open(os.path.join(contents, "document.wflow"), "w", encoding="utf-8") as f:
        f.write(document_wflow)

    print("已写出 Automator 快速操作：%s" % wf)

    # 第二个入口：代码详情统计（复制并改成 --code 命令 + 标题）
    code_wf = os.path.join(services, "GitStatsCode.workflow")
    shutil.copytree(wf, code_wf, dirs_exist_ok=True)
    code_doc = os.path.join(code_wf, "Contents", "document.wflow")
    with open(code_doc, "r", encoding="utf-8") as f:
        s = f.read()
    with open(code_doc, "w", encoding="utf-8") as f:
        f.write(s.replace('python3 "%s" "$@"' % RUN_PY, 'python3 "%s" "$@" --code' % RUN_PY))
    code_info = os.path.join(code_wf, "Contents", "Info.plist")
    with open(code_info, "r", encoding="utf-8") as f:
        s = f.read()
    with open(code_info, "w", encoding="utf-8") as f:
        f.write(s.replace(label, "代码详情统计"))
    print("已写出 Automator 快速操作：%s" % code_wf)
    print("若右键未立即出现，请执行 killall Finder 或注销重登录。")
    print("\n若上面自动安装不可用，可手工创建（30 秒）：")
    print("1. 打开「自动操作(Automator)」→ 新建「快速操作(Quick Action)」")
    print("2. 工作流程收到：选择「文件或文件夹」，位于：Finder")
    print("3. 左侧搜索「运行 Shell 脚本」拖入，改「传递输入」为「作为自变量」")
    print('4. 粘贴命令： python3 "%s" "$@"' % RUN_PY)
    print('5. 保存为「%s」即可。' % label)


def uninstall_macos(dry_run=False):
    for name in ("GitStats", "GitStatsCode"):
        wf = os.path.expanduser("~/Library/Services/" + name + ".workflow")
        if dry_run:
            print("[dry-run] 删除 %s" % wf)
        else:
            shutil.rmtree(wf, ignore_errors=True)
    if not dry_run:
        print("已卸载 Automator 快速操作（macOS）。")


def main(argv=None):
    force_utf8()
    argv = sys.argv[1:] if argv is None else argv
    dry_run = "--dry-run" in argv
    uninstall = "--uninstall" in argv
    label = MENU_LABEL
    if "--name" in argv:
        i = argv.index("--name")
        if i + 1 < len(argv):
            label = argv[i + 1]

    sys_ = platform.system()
    print("目标系统：%s" % sys_)

    if sys_ == "Windows":
        if uninstall:
            uninstall_windows(dry_run)
        else:
            install_windows(dry_run, label)
    elif sys_ == "Darwin":
        if uninstall:
            uninstall_macos(dry_run)
        else:
            install_macos(dry_run, label)
    else:
        print("暂不支持该系统：%s" % sys_)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())