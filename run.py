#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Git 提交统计 —— 右键入口编排器（M3）

由右键菜单（menu.py 安装，用 pythonw 无控制台运行）调用：
选分支 → 采集 → 生成 → 打开报告。

为适配「无控制台」运行，做了三件事：
1. 把 stdout/stderr 重定向到日志文件（temp 目录 git-stats.log），避免 pythonw 下
   sys.stderr 为 None 导致的静默崩溃；
2. 全程 try/except，出错也弹窗告知（含日志路径）；
3. 成功时弹窗明确告知报告路径，并自动打开报告与所在文件夹。

用法：
    python run.py <仓库目录> [--branch NAME] [--no-open] [--no-gui]

    --branch   指定分支，跳过选择对话框
    --code   代码详情统计（不要求 Git 仓库）
    --no-open  不自动打开报告（浏览器）
    --no-gui   不弹任何对话框、不打开文件夹（用于自动化/调试）
"""

import os
import platform
import subprocess
import sys
import tempfile
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(tempfile.gettempdir(), "git-stats.log")
_WINDOWS_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _system():
    return platform.system()


def is_repo(d):
    return os.path.exists(os.path.join(d, ".git"))


def list_branches(repo):
    r = subprocess.run(
        ["git", "-C", repo, "for-each-ref", "--format=%(refname:short)", "refs/heads"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_WINDOWS_NO_WINDOW,
    )
    return [ln.strip() for ln in r.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def current_branch(repo):
    r = subprocess.run(
        ["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=_WINDOWS_NO_WINDOW,
    )
    n = r.stdout.decode("utf-8", "replace").strip()
    return n if n and n != "HEAD" else None


def open_file(path):
    try:
        if _system() == "Darwin":
            subprocess.Popen(["open", path])
        elif _system() == "Windows":
            os.startfile(path)  # noqa
        else:
            import webbrowser
            webbrowser.open("file://" + path)
    except Exception:
        pass


def open_folder(path):
    try:
        if _system() == "Darwin":
            subprocess.Popen(["open", path])
        elif _system() == "Windows":
            os.startfile(path)  # 打开文件所在目录
    except Exception:
        pass


def _working_win(msg):
    """无控制台下的轻量「正在统计…」提示窗（仅 Windows）。"""
    try:
        import tkinter as tk
        r = tk.Tk()
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.configure(bg="#161b22")
        tk.Label(r, text=msg, fg="#ffffff", bg="#161b22",
                 padx=28, pady=20, font=("Microsoft YaHei", 11)).pack()
        r.update_idletasks()
        w = r.winfo_width(); h = r.winfo_height()
        r.geometry("+%d+%d" % ((r.winfo_screenwidth() - w) // 2, (r.winfo_screenheight() - h) // 2))
        r.update()
        return r
    except Exception:
        return None


def pick_branch_tk(names):
    try:
        import tkinter as tk
    except Exception:
        return None
    root = tk.Tk()
    root.title("选择要统计的分支")
    tk.Label(root, text="请选择要统计的分支：").pack(padx=12, pady=(12, 4), anchor="w")
    lb = tk.Listbox(root, height=min(14, len(names)), exportselection=False)
    for n in names:
        lb.insert("end", n)
    lb.select_set(0)
    lb.pack(padx=12, fill="both", expand=True)
    result = {"v": None}

    def ok():
        sel = lb.curselection()
        if sel:
            result["v"] = names[sel[0]]
        root.destroy()

    btn = tk.Frame(root)
    btn.pack(pady=10)
    tk.Button(btn, text="确定", width=10, command=ok).pack(side="left", padx=6)
    tk.Button(btn, text="取消", width=10, command=root.destroy).pack(side="left", padx=6)
    root.mainloop()
    return result["v"]


def pick_branch_mac(names):
    quoted = ",".join('"%s"' % n for n in names)
    script = 'choose from list {%s} with prompt "选择要统计的分支" default items "%s"' % (quoted, names[0])
    r = subprocess.run(["osascript", "-e", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out = r.stdout.decode("utf-8", "replace").strip()
    return out if out and out != "false" else None


def _osascape(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def show_error(msg, title="Git 提交统计"):
    print("[错误] " + msg, file=sys.stderr)
    try:
        if _system() == "Windows":
            import tkinter.messagebox as mb
            mb.showerror(title, msg + "\n\n详细日志：\n" + LOG)
        elif _system() == "Darwin":
            subprocess.run(["osascript", "-e",
                            'display dialog "%s\n\n日志：%s" with icon stop buttons {"好"}'
                            % (_osascape(msg), _osascape(LOG))])
    except Exception:
        pass


def show_success(path, title="Git 提交统计"):
    print("[成功] 报告已生成：" + path, file=sys.stderr)
    try:
        if _system() == "Windows":
            import tkinter.messagebox as mb
            mb.showinfo(title, "统计完成 ✓\n\n报告位置：\n%s" % path)
        elif _system() == "Darwin":
            subprocess.run(["osascript", "-e",
                            'display dialog "统计完成\n报告：%s" buttons {"打开报告","关闭"} default button "打开报告"'
                            % _osascape(path)])
    except Exception:
        pass


def _cleanup(p):
    try:
        os.unlink(p)
    except OSError:
        pass


def _run_code(repo, no_open, no_gui):
    repo_name = os.path.basename(repo.rstrip("/\\")) or "repository"
    report_path = os.path.join(os.path.dirname(repo), repo_name + "-code-report.html")
    folder = os.path.dirname(report_path)

    tmp = tempfile.NamedTemporaryFile(prefix="gitstats-", suffix=".json", delete=False)
    tmp.close()
    stats_path = tmp.name

    sys.path.insert(0, HERE)
    import codestats
    import generate

    work_win = None
    if not no_gui and _system() == "Windows":
        work_win = _working_win("正在统计代码详情…\n请稍候")
    try:
        rc = codestats.main([repo, "--output", stats_path, "--quiet"])
        if rc:
            _cleanup(stats_path)
            if not no_gui:
                show_error("代码详情统计失败，请确认是有效的 Git 仓库。", "代码详情统计")
            return rc
        rc = generate.main([stats_path, "--output", report_path,
                            "--template", os.path.join(HERE, "report", "code_template.html")])
        _cleanup(stats_path)
        if rc:
            if not no_gui:
                show_error("代码报告生成失败。", "代码详情统计")
            return rc
    finally:
        if work_win is not None:
            try:
                work_win.destroy()
            except Exception:
                pass

    print("代码报告已生成：%s" % report_path)
    if not no_open:
        open_file(report_path)
    if not no_gui:
        open_folder(folder)
        show_success(report_path, "代码详情统计")
    return 0


def _run(argv):
    repo = os.path.abspath(argv[0])
    branch_arg = None
    no_open = False
    no_gui = False
    code_mode = False
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--branch" and i + 1 < len(argv):
            branch_arg = argv[i + 1]; i += 2
        elif a == "--no-open":
            no_open = True; i += 1
        elif a == "--no-gui":
            no_gui = True; i += 1
        elif a == "--code":
            code_mode = True; i += 1
        elif a == "--quiet":
            i += 1
        else:
            i += 1

    if code_mode:
        return _run_code(repo, no_open, no_gui)

    if not is_repo(repo):
        if not no_gui:
            show_error("不是 Git 仓库：\n%s" % repo)
        return 1

    # 选择分支
    if branch_arg:
        branch = branch_arg
    else:
        names = list_branches(repo)
        if not names:
            if not no_gui:
                show_error("该仓库没有任何分支（可能是空仓库）")
            return 1
        if len(names) == 1:
            branch = names[0]
        else:
            if no_gui:
                branch = current_branch(repo)
            elif _system() == "Darwin":
                branch = pick_branch_mac(names) or current_branch(repo)
            else:
                branch = pick_branch_tk(names) or current_branch(repo)
            if not branch:
                return 0  # 用户取消

    print("仓库：%s" % repo)
    print("统计分支：%s" % branch)

    repo_name = os.path.basename(repo.rstrip("/\\")) or "repository"
    report_path = os.path.join(os.path.dirname(repo), repo_name + "-git-stats-report.html")
    folder = os.path.dirname(report_path)

    tmp = tempfile.NamedTemporaryFile(prefix="gitstats-", suffix=".json", delete=False)
    tmp.close()
    commits_path = tmp.name

    sys.path.insert(0, HERE)
    import collect
    import generate

    work_win = None
    if not no_gui and _system() == "Windows":
        work_win = _working_win("正在统计分支 %s …\n请稍候" % branch)
    try:
        rc = collect.main([repo, "--branch", branch, "--output", commits_path, "--quiet"])
        if rc:
            _cleanup(commits_path)
            if not no_gui:
                show_error("采集提交失败，请确认该目录是有效的 Git 仓库。")
            return rc

        rc = generate.main([commits_path, "--output", report_path])
        _cleanup(commits_path)
        if rc:
            if not no_gui:
                show_error("报告生成失败。")
            return rc
    finally:
        if work_win is not None:
            try:
                work_win.destroy()
            except Exception:
                pass

    print("报告已生成：%s" % report_path)
    if not no_open:
        open_file(report_path)          # 浏览器打开
    if not no_gui:
        open_folder(folder)             # 打开所在文件夹，让用户看到文件
        show_success(report_path)       # 弹窗告知路径
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv

    # 尽早重定向到日志，杜绝无控制台下 stdout/stderr 为 None 的崩溃
    try:
        logf = open(LOG, "a", encoding="utf-8")
    except Exception:
        logf = open(os.devnull, "w")
    sys.stdout = logf
    sys.stderr = logf

    try:
        if len(argv) < 1:
            print("用法：run.py <仓库目录> [--branch NAME] [--no-open] [--no-gui]", file=sys.stderr)
            return 1
        print("=" * 60)
        print("run.py argv = %r" % (argv,))
        return _run(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
    except Exception:
        traceback.print_exc()
        try:
            show_error("运行过程中出现异常，详见日志：\n%s" % LOG)
        except Exception:
            pass
        return 1
    finally:
        try:
            logf.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())