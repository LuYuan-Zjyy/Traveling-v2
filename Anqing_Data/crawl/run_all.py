#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
一键运行所有安庆数据爬虫

使用方法:
    python run_all.py              # 运行全部
    python run_all.py --only 1     # 只运行脚本1 (黄梅戏)
    python run_all.py --only 2     # 只运行脚本2 (旅游帖子)
    python run_all.py --only 3     # 只运行脚本3 (景点信息)
"""

import os
import sys
import argparse
import importlib


def run_crawler(module_name, description):
    """运行单个爬虫模块"""
    print("\n" + "=" * 70)
    print(f"  Running: {description}")
    print("=" * 70 + "\n")

    try:
        module = importlib.import_module(module_name)
        module.main()
    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description='Run Anqing data crawlers')
    parser.add_argument('--only', type=int, default=0, choices=[0, 1, 2, 3],
                        help='Run only specific crawler (0=all, 1=huangmeixi, 2=tiezi, 3=visited)')
    args = parser.parse_args()

    # 确保在正确的目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    crawlers = [
        (1, 'crawl_huangmeixi',  '安庆政府网黄梅戏专栏 -> huangmeixi/'),
        (2, 'crawl_tiezi',       '马蜂窝安庆旅游帖子 -> tiezi/'),
        (3, 'crawl_visited',     '马蜂窝安庆景点信息 -> visited/'),
    ]

    print("\n" + "#" * 70)
    print("#  Anqing Data Crawlers")
    print("#" * 70)

    for num, module, desc in crawlers:
        if args.only == 0 or args.only == num:
            run_crawler(module, desc)

    print("\n" + "#" * 70)
    print("#  All crawlers finished!")
    print("#" * 70 + "\n")


if __name__ == '__main__':
    main()
