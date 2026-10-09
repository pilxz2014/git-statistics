@echo off
chcp 936 >nul
cd /d "%~dp0"
echo.
echo  ============================================
echo    Git 提交统计 / 代码详情统计 —— 右键菜单卸载
echo  ============================================
echo.
python menu.py --uninstall
echo.
echo  已卸载两个右键菜单。
echo.
pause
