@echo off
setlocal
cd /d "%~dp0"

if not exist "config.json" (
  echo [ERROR] 缺少 config.json，请先填写配置文件。
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 weibo_crawler.py
) else (
  python weibo_crawler.py
)

set EXIT_CODE=%errorlevel%
echo.
if not "%EXIT_CODE%"=="0" (
  echo 抓取失败，详细信息见上面的错误输出。
) else (
  echo 抓取完成，输出目录已在上面打印为 OUTPUT_DIR=...
)
pause
exit /b %EXIT_CODE%
