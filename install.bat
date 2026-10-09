@echo off
chcp 936 >nul
cd /d "%~dp0"
echo.
echo  ============================================
echo    Git 提交统计 / 代码详情统计 —— 右键菜单安装
echo  ============================================
echo.
python menu.py
echo.
echo  安装完成后，在任意文件夹上点右键即可看到两个菜单。
echo  （Git 提交统计 / 代码详情统计）
echo.
pause
