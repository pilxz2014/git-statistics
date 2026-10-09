# Git 提交统计

> 右键一个带 `.git` 的工程目录 → 点击「Git 提交统计」→ 自动采集仓库数据 → 生成一个**可离线双击打开、可动态筛选**的 HTML 报告。

从**提交次数**和**代码行数**两条主线，直观呈现团队或个人的活跃度与贡献分布。另附一个独立的「代码详情统计」，用于统计当前工程的代码构成（文件数 / 总行数 / 代码行 / 空行）。

## 特性

- **零依赖使用**：Windows 上装一次右键菜单，之后纯鼠标操作，不需要命令行、不需要起服务。
- **报告自包含**：产出单个 HTML，ECharts 已内联进去，双击即开、无需联网。
- **双统计口径**：不只数「提了多少次」，也数「改了多少行代码」，一键切换。
- **分支维度**：统计前预选单分支，报告标注被统计的分支，并附仓库分支清单作参考。
- **分类 + 联动筛选**：报告按 Tab 分类；时间 / 人员 / 类型 / 关键字筛选器联动所有图表。
- **仅用 Python 标准库**：不需要 pip install 任何东西。

## 环境要求

- Windows（主目标平台）；macOS 做了适配但**未经真机验证**。
- Python 3（在 3.12 / 3.13 上验证过），且 `python` 在 PATH 中。
- git 在 PATH 中（代码详情统计也依赖 `git ls-files` 来尊重 `.gitignore`）。

## 快速开始

**安装右键菜单**：双击 `install.bat`。装完在任意文件夹上点右键（或文件夹空白处右键）即可看到：

- 「Git 提交统计」——统计 Git 提交历史并出报告
- 「代码详情统计」——统计当前工程的代码构成

**卸载**：双击 `uninstall.bat`。

菜单写在 `HKEY_CURRENT_USER\Software\Classes\Directory(\\Background)\shell\GitStats*`，只影响当前用户，**不需要管理员权限**。

## 目录结构

```
├── install.bat / uninstall.bat   双击安装 / 卸载右键菜单
├── menu.py                       注册 / 卸载右键菜单（Windows 写注册表，macOS 写 Automator 快速操作）
├── run.py                        右键菜单真正的执行入口，由 pythonw.exe 无控制台调起
├── collect.py                    采集 Git 提交数据 → commits.json
├── codestats.py                  统计工程代码构成 → codestats.json
├── generate.py                   把 JSON 注入模板 → 单个自包含 HTML
├── report/
│   ├── template.html             提交统计报告模板
│   ├── code_template.html        代码详情报告模板
│   └── echarts.min.js            本地 ECharts，会被内联进报告
└── docs/                         需求文档与原型
```

## 命令行用法

嫌右键麻烦或想接自动化，可以直接跑：

```bash
# 采集提交数据（默认当前分支）
python collect.py D:/my/project
python collect.py D:/my/project --branch develop   # 指定分支
python collect.py D:/my/project --list-branches    # 只列出本地分支名(JSON)
python collect.py D:/my/project -o out.json        # 指定输出路径

# 生成报告
python generate.py commits.json                    # 默认输出同目录 git-stats-report.html
python generate.py commits.json -o report.html

# 代码详情统计
python codestats.py D:/my/project -o codestats.json

# 一键跑完整流程（右键菜单走的就是它）
python run.py D:/my/project                        # 选分支 → 采集 → 生成 → 打开报告
python run.py D:/my/project --branch main
python run.py D:/my/project --code                 # 代码详情统计
python run.py D:/my/project --no-open --no-gui     # 不弹窗、不开浏览器，适合自动化/调试

# 只打印要写什么，不真动注册表
python menu.py --dry-run
python menu.py --uninstall
```

## 报告输出位置

报告生成在**被统计工程的上一级目录**：

- `<父目录>/<工程名>-git-stats-report.html`
- `<父目录>/<工程名>-code-report.html`

运行日志在 `%TEMP%\git-stats.log`。`run.py` 由 `pythonw.exe` 无控制台调起，所以出错时不靠控制台，而是弹窗并把日志路径一起告诉你。

## 开发注意事项

### `.bat` 必须保持 GBK + CRLF

`install.bat` / `uninstall.bat` 里含中文，它们**必须是 GBK(cp936) 编码 + CRLF 换行 + 首行 `chcp 936 >nul`**。这不是洁癖，是踩过的坑：

- **LF-only 换行**会让 cmd.exe 解析错乱——首行中文整行被吞，甚至把 `@echo off` 从中间劈开，报 `'ho' is not recognized as an internal or external command`。
- **文件内写 `chcp 65001`** 更阴：cmd 按字节偏移读取批处理文件，中途切代码页会打乱读取指针，后续行会从**行中间**被重读，表现为 `'indows，当前用户）。' is not recognized ...`，也就是**静默跳过命令**——比乱码危险得多。

所以用编辑器改这两个文件时，**必须另存为 ANSI/GBK**，存成 UTF-8 会立刻复发。

仓库里的 `.gitattributes` 内容是 `* -text`（禁止任何换行自动转换），用来防止 `core.autocrlf=true` 把 bat 的 CRLF 规范化成 LF 存进仓库——否则 clone 到别的机器上又变成坏 bat。**不要删这个文件。**

### 改 `.py` 不用管编码

Python 源码按 UTF-8 读，正常存 UTF-8 即可。

## 文档

- [`docs/需求文档.md`](docs/需求文档.md) —— 完整需求与数据口径定义
- [`docs/原型.html`](docs/原型.html) —— 报告交互原型
