"""
main.py — AI 税务会计 Agent 系统入口
支持 5 种运行模式：
  --file <path>          : 税务文件处理
  --ask "<question>"     : 税法问答
  --transactions <path>  : 交易异常检测
  --report               : 生成完整报告
  --mock                 : Mock 测试（不需要真实文件）
  (无参数)               : 交互式 REPL 模式
"""

import argparse
import json
import os
import sys

# ── Windows 控制台 UTF-8 兼容 ──
if sys.platform == "win32" and sys.stdout.encoding.lower() != "utf-8":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── 加载环境变量 ──
from dotenv import load_dotenv
load_dotenv()

# ── 验证 API Key ──
if not os.environ.get("DEEPSEEK_API_KEY"):
    print("错误：未找到 DEEPSEEK_API_KEY。请创建 .env 文件并填入 DeepSeek API Key。")
    print("参考 .env.example 文件。")
    sys.exit(1)

from router import Router
from agents.document_agent import DocumentAgent
from agents.research_agent import ResearchAgent
from agents.anomaly_agent import AnomalyAgent
from agents.report_agent import ReportAgent


# ──────────────────────────────────────────────
# 各模式处理函数
# ──────────────────────────────────────────────

def run_document_mode(file_path: str, mock_mode: bool) -> dict:
    """模式1：处理税务文件"""
    agent = DocumentAgent(mock_mode=mock_mode)
    target = "mock" if mock_mode else file_path
    return agent.run(target)


def run_research_mode(question: str) -> dict:
    """模式2：税法问答"""
    agent = ResearchAgent()
    return agent.run(question)


def run_anomaly_mode(data_source: str, mock_mode: bool) -> dict:
    """模式3：交易异常检测"""
    agent = AnomalyAgent(mock_mode=mock_mode)
    target = "mock" if mock_mode else data_source
    return agent.run(target)


def run_report_mode(
    file_path: str = None,
    transactions_path: str = None,
    question: str = None,
    mock_mode: bool = False,
) -> str:
    """模式4：生成完整报告（调用所有相关 Agent）"""

    document_results = None
    anomaly_results = None
    research_results = None

    # ── 文件处理（如有）──
    if file_path or mock_mode:
        doc_agent = DocumentAgent(mock_mode=mock_mode)
        target = "mock" if mock_mode else file_path
        document_results = doc_agent.run(target)
        print()

    # ── 交易检测（如有）──
    if transactions_path or mock_mode:
        anomaly_agent = AnomalyAgent(mock_mode=mock_mode)
        target = "mock" if mock_mode else transactions_path
        anomaly_results = anomaly_agent.run(target)
        print()

    # ── 税法问答（如有）──
    if question:
        research_agent = ResearchAgent()
        research_results = research_agent.run(question)
        print()

    # ── 生成报告 ──
    report_agent = ReportAgent()
    return report_agent.run(
        document_results=document_results,
        anomaly_results=anomaly_results,
        research_results=research_results,
        stream=True,
    )


def run_interactive_mode(mock_mode: bool):
    """模式5：交互式 REPL"""
    router = Router()

    print("\n" + "━" * 50)
    print(" AI 税务会计 Agent 系统")
    print("━" * 50)
    print("输入税法问题、文件路径、或 CSV 数据路径")
    print("命令: /help | /quit | /mock on/off")
    print("━" * 50 + "\n")

    while True:
        try:
            user_input = input(">>> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n再见！")
            break

        if not user_input:
            continue

        # 内置命令
        if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
            print("再见！")
            break
        elif user_input.lower() == "/help":
            _print_help()
            continue
        elif user_input.lower() == "/mock on":
            mock_mode = True
            print("[系统] Mock 模式已开启")
            continue
        elif user_input.lower() == "/mock off":
            mock_mode = False
            print("[系统] Mock 模式已关闭")
            continue

        # 路由
        route_result = router.route(user_input)
        task = route_result.get("task", "research")
        print(f"\n[Router] 识别任务类型: {task}\n")

        try:
            if task == "document":
                fp = route_result.get("file_path") or user_input.strip()
                result = run_document_mode(fp, mock_mode)
                print("\n提取结果：")
                print(json.dumps(result, ensure_ascii=False, indent=2))

            elif task == "research":
                result = run_research_mode(user_input)
                if result.get("answer"):
                    print(f"\n{result['answer']}")
                    if result.get("citations"):
                        print("\n法律依据：")
                        for c in result["citations"]:
                            print(f"  • {c}")
                    if result.get("notes"):
                        print(f"\n注意：{result['notes']}")

            elif task == "anomaly":
                fp = route_result.get("file_path") or user_input.strip()
                result = run_anomaly_mode(fp, mock_mode)
                _print_anomaly_summary(result)

            elif task == "report":
                run_report_mode(mock_mode=mock_mode)

        except Exception as e:
            print(f"\n[错误] {e}")

        print()


def _print_anomaly_summary(result: dict):
    """打印异常检测摘要"""
    print(f"\n异常检测结果：")
    print(f"  总计: {result.get('total', 0)} 条异常")
    print(f"  ⚠️  高风险: {result.get('high_risk', 0)}")
    print(f"  🔶 中风险: {result.get('medium_risk', 0)}")
    print(f"  🔷 低风险: {result.get('low_risk', 0)}")

    anomalies = result.get("all_anomalies", [])
    real_anomalies = [a for a in anomalies if "anomaly_type" in a]

    if real_anomalies:
        print("\n异常详情：")
        for a in real_anomalies:
            icon = {"高": "⚠️ ", "中": "🔶", "低": "🔷"}.get(a.get("risk_level", ""), "• ")
            print(f"  {icon} 第{a.get('row_index', '?')}行 | {a.get('anomaly_type')} | {a.get('description', '')[:60]}")


def _print_help():
    """打印帮助信息"""
    print("""
可用命令：
  直接输入问题      → 税法问答（如：家庭办公室如何抵扣？）
  输入文件路径      → 处理税务文件（如：w2.pdf）
  输入 CSV 路径     → 检测交易异常（如：transactions.csv）
  /mock on/off     → 开启/关闭 Mock 模式
  /quit            → 退出程序
  /help            → 显示此帮助
""")


# ──────────────────────────────────────────────
# CLI 参数解析
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI 税务会计 Agent 系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py --mock --report           # Mock 测试全流程
  python main.py --file w2.pdf             # 处理税务文件
  python main.py --ask "家庭办公室如何抵扣？" # 税法问答
  python main.py --transactions data.csv   # 检测交易异常
  python main.py --report --mock           # 生成完整报告（Mock 模式）
  python main.py                           # 交互式模式
""",
    )

    parser.add_argument("--file", "-f", metavar="PATH",
                        help="税务文件路径（PDF / 图片）")
    parser.add_argument("--ask", "-q", metavar="QUESTION",
                        help="税法问题（用引号括起来）")
    parser.add_argument("--transactions", "-t", metavar="CSV_PATH",
                        help="交易数据 CSV 文件路径")
    parser.add_argument("--report", "-r", action="store_true",
                        help="生成完整税务分析报告")
    parser.add_argument("--mock", "-m", action="store_true",
                        help="使用 Mock 数据测试，不需要真实文件")
    parser.add_argument("--output", "-o", metavar="FORMAT",
                        choices=["markdown", "json"], default="markdown",
                        help="输出格式（markdown 或 json，默认 markdown）")

    args = parser.parse_args()

    # ── 无参数：交互式模式 ──
    if len(sys.argv) == 1:
        run_interactive_mode(mock_mode=False)
        return

    # ── Mock 全流程测试 ──
    if args.mock and args.report:
        print("\n[Router] 识别任务类型: report（Mock 全流程）\n")
        run_report_mode(mock_mode=True)
        return

    # ── 生成报告模式 ──
    if args.report:
        print("\n[Router] 识别任务类型: report\n")
        run_report_mode(
            file_path=args.file,
            transactions_path=args.transactions,
            question=args.ask,
            mock_mode=args.mock,
        )
        return

    # ── 文件处理模式 ──
    if args.file:
        print(f"\n[Router] 识别任务类型: document_processing\n")
        result = run_document_mode(args.file, args.mock)
        print("\n提取结果：")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # ── 税法问答模式 ──
    if args.ask:
        print(f"\n[Router] 识别任务类型: research\n")
        result = run_research_mode(args.ask)
        print("\n" + "━" * 40)
        if result.get("answer"):
            print(result["answer"])
        if result.get("citations"):
            print("\n法律依据：")
            for c in result["citations"]:
                print(f"  • {c}")
        if result.get("notes"):
            print(f"\n注意：{result['notes']}")
        if result.get("disclaimer"):
            print(f"\n⚠️  {result['disclaimer']}")
        return

    # ── 交易异常检测模式 ──
    if args.transactions:
        print(f"\n[Router] 识别任务类型: anomaly_detection\n")
        result = run_anomaly_mode(args.transactions, args.mock)
        _print_anomaly_summary(result)
        return

    # ── Mock 单独模式（--mock 但没有其他参数）──
    if args.mock:
        print("\n[Mock] 运行 Mock 全流程测试...\n")
        print("[Router] 识别任务类型: report（Mock 模式）\n")
        run_report_mode(mock_mode=True)
        return

    # ── 兜底：交互式模式 ──
    run_interactive_mode(mock_mode=args.mock)


if __name__ == "__main__":
    main()
