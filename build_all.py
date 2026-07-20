#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键生成当日全部分类新闻并重建站点。

依次运行：
    1. build_dashboard.py   生成 AI 日报（ai-daily）
    2. build_rss.py         生成 feeds.yaml 中配置的分类（tech/finance/world …）
    3. build_archive.py     重建首页 / 归档页 / 当日汇总页 / sitemap / robots

用法：
    python build_all.py
    python build_all.py 2026-07-20      # 指定日期（默认今天）

完成后按需提交并推送，GitHub Actions 会自动部署。
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
STEPS = ("build_dashboard.py", "build_rss.py", "build_archive.py")


def main():
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    for script in STEPS:
        print(f"\n========== {script} ==========")
        cmd = [PY, str(ROOT / script)]
        if date_arg and script in ("build_rss.py", "build_dashboard.py"):
            cmd.append(date_arg)
        rc = subprocess.run(cmd, cwd=ROOT).returncode
        if rc != 0:
            print(f"!! {script} 执行失败（退出码 {rc}），已中止。", file=sys.stderr)
            sys.exit(rc)
    print("\n✅ 全部完成。可运行 `git add . && git commit -m \"news\" && git push` 发布。")


if __name__ == "__main__":
    main()
