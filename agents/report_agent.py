"""
report_agent.py — 报告生成 Agent
功能：汇总所有 Agent 的输出，生成完整的税务分析报告
支持流式输出（Markdown 格式）
"""

import json
import os
import sys

# 将项目根目录加入 sys.path（支持独立运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent
from prompts import REPORT_SYSTEM_PROMPT
from tools.report_formatter import (
    format_as_markdown,
    format_as_json,
    generate_executive_summary,
)


# ──────────────────────────────────────────────
# 工具定义
# ──────────────────────────────────────────────
REPORT_TOOLS = [
    {
        "name": "compile_report_data",
        "description": "将各 Agent 的输出整合为统一的报告数据结构。",
        "input_schema": {
            "type": "object",
            "properties": {
                "document_results_json": {
                    "type": "string",
                    "description": "DocumentAgent 输出的 JSON 字符串（文件字段提取结果），没有则传 'null'",
                },
                "anomaly_results_json": {
                    "type": "string",
                    "description": "AnomalyAgent 输出的 JSON 字符串（异常检测结果），没有则传 'null'",
                },
                "research_results_json": {
                    "type": "string",
                    "description": "ResearchAgent 输出的 JSON 字符串（税法问答结果），没有则传 'null'",
                },
            },
            "required": ["document_results_json", "anomaly_results_json", "research_results_json"],
        },
    },
    {
        "name": "generate_executive_summary",
        "description": "根据汇总数据自动生成 3-5 条执行摘要。",
        "input_schema": {
            "type": "object",
            "properties": {
                "compiled_data_json": {
                    "type": "string",
                    "description": "compile_report_data 工具返回的 JSON 字符串",
                }
            },
            "required": ["compiled_data_json"],
        },
    },
    {
        "name": "format_final_report",
        "description": "将汇总数据格式化为最终报告（Markdown 或 JSON 格式）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "compiled_data_json": {
                    "type": "string",
                    "description": "包含 executive_summary 在内的完整汇总数据 JSON",
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json"],
                    "description": "输出格式：markdown 或 json",
                    "default": "markdown",
                },
            },
            "required": ["compiled_data_json"],
        },
    },
]


class ReportAgent(BaseAgent):
    """报告生成 Agent，整合所有分析结果，流式输出 Markdown 报告"""

    def __init__(self):
        super().__init__(name="ReportAgent")

    def _dispatch_tool(self, tool_name: str, tool_input: dict) -> dict:

        if tool_name == "compile_report_data":
            # 解析各 Agent 的输出
            def safe_parse(s: str):
                if not s or s.lower() == "null":
                    return None
                try:
                    return json.loads(s)
                except (json.JSONDecodeError, TypeError):
                    return None

            doc = safe_parse(tool_input.get("document_results_json", "null"))
            anomaly = safe_parse(tool_input.get("anomaly_results_json", "null"))
            research = safe_parse(tool_input.get("research_results_json", "null"))

            # 提取异常列表（anomaly_results 可能包含 all_anomalies 子键）
            if anomaly and "all_anomalies" in anomaly:
                anomaly_list = anomaly["all_anomalies"]
            elif isinstance(anomaly, list):
                anomaly_list = anomaly
            else:
                anomaly_list = []

            compiled = {
                "document_results": doc,
                "anomaly_results": anomaly_list,
                "research_results": research,
                "action_items": [],
                "executive_summary": [],
            }
            return compiled

        elif tool_name == "generate_executive_summary":
            try:
                data = json.loads(tool_input.get("compiled_data_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                return {"summary": [], "error": "无法解析数据"}

            summary = generate_executive_summary(data)
            data["executive_summary"] = summary
            return {"summary": summary, "updated_data": data}

        elif tool_name == "format_final_report":
            try:
                data = json.loads(tool_input.get("compiled_data_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                return {"error": "无法解析数据"}

            fmt = tool_input.get("format", "markdown")
            if fmt == "json":
                return {"report": format_as_json(data), "format": "json"}
            else:
                return {"report": format_as_markdown(data), "format": "markdown"}

        else:
            return {"error": f"未知工具: {tool_name}"}

    def run(
        self,
        document_results: dict = None,
        anomaly_results: dict = None,
        research_results: dict = None,
        stream: bool = True,
    ) -> str:
        """
        主入口：生成完整的税务分析报告
        document_results: DocumentAgent 的输出（可选）
        anomaly_results: AnomalyAgent 的输出（可选）
        research_results: ResearchAgent 的输出（可选）
        stream: 是否流式输出（默认 True）
        返回：完整报告文字
        """
        self.log("开始生成分析报告...")

        # 将输入序列化为 JSON 字符串，传给工具
        doc_json = json.dumps(document_results, ensure_ascii=False) if document_results else "null"
        anomaly_json = json.dumps(anomaly_results, ensure_ascii=False) if anomaly_results else "null"
        research_json = json.dumps(research_results, ensure_ascii=False) if research_results else "null"

        messages = [
            {
                "role": "user",
                "content": (
                    "请根据以下各 Agent 的分析结果，生成完整的税务分析报告（Markdown 格式）：\n\n"
                    f"文件处理结果：{doc_json[:500] if len(doc_json) > 500 else doc_json}\n\n"
                    f"异常检测结果：{anomaly_json[:500] if len(anomaly_json) > 500 else anomaly_json}\n\n"
                    f"税法研究结果：{research_json[:500] if len(research_json) > 500 else research_json}\n\n"
                    "请依次执行：整合数据 → 生成摘要 → 格式化报告。\n"
                    "在 format_final_report 工具中传入完整的 compiled_data（含 executive_summary）。"
                ),
            }
        ]

        # 执行 tool-use 循环（先调用工具生成报告内容）
        messages, _ = self._run_tool_loop(
            messages=messages,
            tools=REPORT_TOOLS,
            system=REPORT_SYSTEM_PROMPT,
        )

        # 从工具结果中提取报告内容
        report_content = self._extract_report_content(messages)

        if report_content:
            self.log("正在输出报告...\n")
            print("\n" + "━" * 50)

            if stream:
                # 逐字符流式打印（模拟流式效果）
                import time
                for char in report_content:
                    try:
                        print(char, end="", flush=True)
                    except UnicodeEncodeError:
                        print(char.encode("utf-8", errors="replace").decode("utf-8"), end="", flush=True)
                print()
            else:
                print(report_content)
        else:
            # fallback：让 Claude 基于消息历史直接流式生成报告
            self.log("正在流式生成报告...\n")
            print("\n" + "━" * 50)

            # 添加最终提示
            messages.append({
                "role": "user",
                "content": "请根据以上工具调用结果，直接输出完整的税务分析报告（Markdown 格式）。",
            })
            report_content = self._stream_response(
                messages=messages,
                system=REPORT_SYSTEM_PROMPT,
            )

        self.log("报告生成完成 ✓")
        return report_content or ""

    def _extract_report_content(self, messages: list) -> str:
        """从消息历史中提取 format_final_report 工具的报告内容"""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in reversed(content):
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            try:
                                data = json.loads(block.get("content", "{}"))
                                if "report" in data:
                                    return data["report"]
                            except (json.JSONDecodeError, TypeError):
                                continue
        return None


# ──────────────────────────────────────────────
# 独立测试
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()

    print("=== ReportAgent 独立测试（Mock 数据）===\n")

    # 构造测试输入
    mock_doc = {
        "document_type": "W-2",
        "taxpayer_name": "Jane Doe",
        "employer_name": "Anthropic Inc",
        "income_amount": "$120,000.00",
        "tax_withheld_federal": "$24,000.00",
        "tax_withheld_state": "$7,200.00",
        "period": "2024",
        "invoice_number": None,
        "confidence": "high",
    }

    mock_anomalies = {
        "total": 3,
        "high_risk": 2,
        "medium_risk": 1,
        "low_risk": 0,
        "all_anomalies": [
            {
                "row_index": 2,
                "anomaly_type": "duplicate_payment",
                "risk_level": "高",
                "description": "疑似重复付款：第2行与第3行，Office Depot，$500.00，相差1天",
                "source": "rule",
                "amount": "$500.00",
                "vendor": "Office Depot",
            },
            {
                "row_index": 7,
                "anomaly_type": "statistical_outlier",
                "risk_level": "高",
                "description": "金额 $98,000.00 超过统计阈值",
                "source": "rule",
                "amount": "$98,000.00",
                "vendor": "Unknown Vendor",
            },
            {
                "row_index": 5,
                "anomaly_type": "missing_fields",
                "risk_level": "中",
                "description": "缺少：供应商名称, 发票号",
                "source": "rule",
                "amount": "$2,300.00",
                "vendor": "(空)",
            },
        ],
    }

    mock_research = {
        "question": "家庭办公室抵扣",
        "answer": "根据 IRC Section 280A，家庭办公室抵扣须满足专用性要求。",
        "citations": ["IRC § 280A", "IRS Publication 587"],
        "needs_professional": True,
    }

    agent = ReportAgent()
    agent.run(
        document_results=mock_doc,
        anomaly_results=mock_anomalies,
        research_results=mock_research,
    )
