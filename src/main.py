#!/usr/bin/env python3
"""
AI Daily 主入口
自动获取 AI 资讯并生成精美的 HTML 页面
"""
import sys
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import (
    ZHIPU_API_KEY,
    OUTPUT_DIR
)
from src.rss_fetcher import RSSFetcher
from src.claude_analyzer import ClaudeAnalyzer
from src.html_generator import HTMLGenerator
from src.notifier import EmailNotifier


def print_banner():
    """打印程序横幅"""
    banner = """
╔════════════════════════════════════════════════════════════╗
║                                                              ║
║   AI Daily - AI 资讯日报自动生成器                          ║
║                                                              ║
║   自动获取 smol.ai 资讯 · Claude 智能分析                   ║
║   精美 HTML 页面 · 自动部署                                 ║
║                                                              ║
╚════════════════════════════════════════════════════════════╝
"""
    print(banner)


def get_target_date(days_offset: int = 2) -> str:
    """
    获取目标日期

    Args:
        days_offset: 向前偏移的天数，默认2天

    Returns:
        格式化的日期字符串 (YYYY-MM-DD)
    """
    target_date = (datetime.now(timezone.utc) - timedelta(days=days_offset))
    return target_date.strftime("%Y-%m-%d")


def merge_contents(contents: list) -> dict:
    """
    合并多个日期的内容

    Args:
        contents: 内容列表

    Returns:
        合并后的内容字典
    """
    if not contents:
        return None

    # 使用第一个内容作为基础
    merged = contents[0].copy()

    # 合并标题
    titles = [c.get('title', '') for c in contents if c.get('title')]
    if len(titles) > 1:
        merged['title'] = f"AI资讯汇总 ({len(titles)}天)"

    # 合并内容
    all_content = []
    for i, content in enumerate(contents):
        date_str = get_target_date(days_offset=i)
        all_content.append(f"\n\n## {date_str} 资讯\n")
        all_content.append(content.get('content', ''))

    merged['content'] = '\n'.join(all_content)
    merged['description'] = f"汇总了 {len(titles)} 天的 AI 前沿资讯"

    return merged


def main():
    """主函数"""
    print_banner()

    # 检查环境变量
    if not ZHIPU_API_KEY:
        print("❌ 错误: ZHIPU_API_KEY 环境变量未设置")
        print("   请设置智谱 AI 的 API Key")
        sys.exit(1)

    # 初始化组件
    notifier = EmailNotifier()
    email_enabled = notifier._is_configured()
    total_steps = 5 if email_enabled else 4

    try:
        # 1. 计算目标日期范围 (获取最近3天的资讯)
        end_date = get_target_date(days_offset=0)
        start_date = get_target_date(days_offset=2)
        print(f"[日期范围] {start_date} ~ {end_date} (3天)")
        print(f"   (北京时间: {datetime.now(timezone.utc) + timedelta(hours=8)} + 8h)")
        print()

        # 2. 下载并解析 RSS
        print(f"[步骤 1/{total_steps}] 下载 RSS...")
        fetcher = RSSFetcher()
        rss_data = fetcher.fetch()

        # 显示 RSS 信息
        date_range = fetcher.get_date_range(rss_data)
        if date_range[0] and date_range[1]:
            print(f"   RSS 日期范围: {date_range[0]} ~ {date_range[1]}")
        print()

        # 3. 查找多天的资讯并合并
        print(f"[步骤 2/{total_steps}] 查找多天的资讯...")
        contents = []
        for offset in range(3):  # 0, 1, 2 天前
            date_str = get_target_date(days_offset=offset)
            content = fetcher.get_content_by_date(date_str, rss_data)
            if content:
                contents.append(content)
                print(f"   ✓ {date_str}: {content.get('title', '')[:50]}...")

        if not contents:
            print("   目标日期范围无内容，生成空页面")
            if email_enabled:
                notifier.send_empty(
                    start_date,
                    f"RSS 中未找到 {start_date} ~ {end_date} 的资讯内容。"
                    f"RSS 可用日期范围: {date_range[0]} ~ {date_range[1]}"
                )

            # 生成空页面
            generator = HTMLGenerator()
            generator.generate_css()
            generator.generate_empty(end_date)
            generator.update_index(end_date, {"summary": ["暂无资讯"]})

            print("   完成")
            return

        # 合并多天的内容
        print(f"\n   合并 {len(contents)} 天的资讯...")
        merged_content = merge_contents(contents)
        print()

        # 4. 调用 Claude 分析
        print(f"[步骤 3/{total_steps}] 调用 Claude 进行智能分析...")
        analyzer = ClaudeAnalyzer()
        result = analyzer.analyze(merged_content, end_date)

        # 检查分析状态
        if result.get("status") == "empty":
            print("   分析结果为空")
            if email_enabled:
                notifier.send_empty(end_date, result.get("reason", "内容分析为空"))
            return

        print()

        # 5. 生成 HTML
        print(f"[步骤 4/{total_steps}] 生成 HTML 页面...")
        generator = HTMLGenerator()
        generator.generate_css()

        # 生成日报页面
        html_path = generator.generate_daily(result)
        print(f"   文件路径: {html_path}")
        print()

        # 计算总资讯数
        total_items = sum(
            len(cat.get('items', []))
            for cat in result.get('categories', [])
        )

        # 6. 发送成功通知（可选）
        if email_enabled:
            print(f"[步骤 5/{total_steps}] 发送邮件通知...")
            notifier.send_success(end_date, total_items)
            print()
        else:
            print("   (邮件通知未配置，跳过)")
            print()

        # 完成
        print("╔════════════════════════════════════════════════════════════╗")
        print("║                                                              ║")
        print("║   ✅ 任务完成!                                              ║")
        print("║                                                              ║")
        print(f"║   日期范围: {start_date} ~ {end_date}                          ║")
        print(f"║   资讯天数: {len(contents)} 天                                         ║")
        print(f"║   资讯数: {total_items} 条                                          ║")
        print(f"║   主题: {result.get('theme', 'blue')}                                                ║")
        print("║                                                              ║")
        print("╚════════════════════════════════════════════════════════════╝")

    except KeyboardInterrupt:
        print("\n⚠️ 用户中断")
        sys.exit(130)

    except Exception as e:
        print(f"\n[错误] 执行过程出错: {e}")
        import traceback
        traceback.print_exc()

        # 发送错误通知（如果配置了邮件）
        if email_enabled:
            try:
                target_date = get_target_date(days_offset=0)
                notifier.send_error(target_date, str(e))
            except:
                pass

        sys.exit(1)


if __name__ == "__main__":
    main()
