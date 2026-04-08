"""
anomaly_agent.py — 交易异常检测 Agent
功能：接受 CSV 或 Mock 交易数据，用规则 + AI 双重检测异常
"""

import csv
import io
import json
import os
import sys
from pathlib import Path

# 将项目根目录加入 sys.path（支持独立运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent
from prompts import ANOMALY_SYSTEM_PROMPT
from tools.anomaly_detector import (
    run_rule_based_checks,
    run_ai_based_checks,
    get_mock_transactions,
)


# ──────────────────────────────────────────────
# 工具定义
# ──────────────────────────────────────────────
ANOMALY_TOOLS = [
    {
        "name": "load_transactions",
        "description": "加载交易数据。可从 CSV 文件路径加载，或填 'mock' 使用内置 Mock 数据。",
        "input_schema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "数据来源：CSV 文件路径，或 'mock' 使用示例数据",
                }
            },
            "required": ["source"],
        },
    },
    {
        "name": "run_rule_checks",
        "description": "对交易数据执行规则检测，检查重复付款、金额异常、字段缺失、整数金额等。",
        "input_schema": {
            "type": "object",
            "properties": {
                "transactions_json": {
                    "type": "string",
                    "description": "JSON 格式的交易数据列表",
                }
            },
            "required": ["transactions_json"],
        },
    },
    {
        "name": "run_ai_checks",
        "description": "对规则未覆盖的交易进行 AI 二次分析，识别潜在异常。",
        "input_schema": {
            "type": "object",
            "properties": {
                "transactions_json": {
                    "type": "string",
                    "description": "JSON 格式的全量交易数据",
                },
                "rule_anomaly_rows_json": {
                    "type": "string",
                    "description": "已被规则标记的行号列表（JSON 数组，如 [2, 5, 7]）",
                },
            },
            "required": ["transactions_json", "rule_anomaly_rows_json"],
        },
    },
    {
        "name": "summarize_anomalies",
        "description": "汇总所有异常结果，按风险等级分组统计。",
        "input_schema": {
            "type": "object",
            "properties": {
                "all_anomalies_json": {
                    "type": "string",
                    "description": "JSON 格式的所有异常列表（规则 + AI 合并）",
                }
            },
            "required": ["all_anomalies_json"],
        },
    },
]


# ──────────────────────────────────────────────
# CSV 加载辅助函数
# ──────────────────────────────────────────────
def _load_csv_transactions(file_path: str) -> dict:
    """从 CSV 文件加载交易数据，自动规范化字段名"""
    path = Path(file_path)
    if not path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}", "transactions": []}

    try:
        transactions = []
        with open(file_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                tx = {"row_index": i}
                # 字段名规范化（小写、去空格）
                for k, v in row.items():
                    key = k.lower().strip().replace(" ", "_")
                    # 尝试转换金额字段
                    if key in ("amount", "金额", "price", "total"):
                        try:
                            tx["amount"] = float(str(v).replace(",", "").replace("$", ""))
                        except ValueError:
                            tx["amount"] = None
                    elif key in ("date", "日期", "transaction_date"):
                        tx["date"] = str(v).strip()
                    elif key in ("vendor", "供应商", "payee", "merchant"):
                        tx["vendor"] = str(v).strip()
                    elif key in ("description", "备注", "memo", "desc"):
                        tx["description"] = str(v).strip()
                    elif key in ("invoice_number", "发票号", "invoice_no", "invoice"):
                        tx["invoice_number"] = str(v).strip()
                    elif key in ("payment_method", "支付方式", "method"):
                        tx["payment_method"] = str(v).strip()
                    else:
                        tx[key] = str(v).strip()

                transactions.append(tx)

        return {"success": True, "transactions": transactions, "count": len(transactions)}

    except Exception as e:
        return {"success": False, "error": str(e), "transactions": []}


class AnomalyAgent(BaseAgent):
    """交易异常检测 Agent，结合规则检测和 AI 判断"""

    def __init__(self, mock_mode: bool = False):
        super().__init__(name="AnomalyAgent")
        self.mock_mode = mock_mode
        # 缓存加载的交易数据，供 _dispatch_tool 中的工具共享
        self._transactions_cache: list = []

    def _dispatch_tool(self, tool_name: str, tool_input: dict) -> dict:

        if tool_name == "load_transactions":
            source = tool_input.get("source", "mock")
            if self.mock_mode or source.lower() == "mock":
                txs = get_mock_transactions()
                self._transactions_cache = txs
                return {"success": True, "transactions": txs, "count": len(txs), "source": "mock"}
            else:
                result = _load_csv_transactions(source)
                if result["success"]:
                    self._transactions_cache = result["transactions"]
                return result

        elif tool_name == "run_rule_checks":
            try:
                txs = json.loads(tool_input.get("transactions_json", "[]"))
            except json.JSONDecodeError:
                txs = self._transactions_cache
            anomalies = run_rule_based_checks(txs)
            return {"anomalies": anomalies, "count": len(anomalies)}

        elif tool_name == "run_ai_checks":
            try:
                txs = json.loads(tool_input.get("transactions_json", "[]"))
            except json.JSONDecodeError:
                txs = self._transactions_cache

            try:
                rule_rows = set(json.loads(tool_input.get("rule_anomaly_rows_json", "[]")))
            except json.JSONDecodeError:
                rule_rows = set()

            ai_anomalies = run_ai_based_checks(txs, rule_rows, self.client, self.model)
            return {"anomalies": ai_anomalies, "count": len(ai_anomalies)}

        elif tool_name == "summarize_anomalies":
            try:
                all_anomalies = json.loads(tool_input.get("all_anomalies_json", "[]"))
            except json.JSONDecodeError:
                return {"error": "无法解析异常列表"}

            # 按风险等级分组
            high = [a for a in all_anomalies if a.get("risk_level") == "高"]
            mid = [a for a in all_anomalies if a.get("risk_level") == "中"]
            low = [a for a in all_anomalies if a.get("risk_level") == "低"]

            summary = {
                "total": len(all_anomalies),
                "high_risk": len(high),
                "medium_risk": len(mid),
                "low_risk": len(low),
                "by_type": {},
                "all_anomalies": all_anomalies,
            }

            # 按类型统计
            for a in all_anomalies:
                t = a.get("anomaly_type", "unknown")
                summary["by_type"][t] = summary["by_type"].get(t, 0) + 1

            return summary

        else:
            return {"error": f"未知工具: {tool_name}"}

    def run(self, data_source: str) -> dict:
        """
        主入口：检测交易数据中的异常
        data_source: CSV 文件路径，或 "mock"
        返回：包含所有异常的汇总结果
        """
        self.log(f"加载交易数据: {data_source}")

        if self.mock_mode:
            display = "Mock 测试数据（10条交易，含注入异常）"
        else:
            display = data_source

        messages = [
            {
                "role": "user",
                "content": (
                    f"请分析以下交易数据并检测异常：数据来源 = '{data_source}'。\n"
                    f"请依次执行：加载数据 → 规则检测 → AI 检测 → 生成汇总。"
                ),
            }
        ]

        self.log("正在执行规则检测...")

        messages, final_text = self._run_tool_loop(
            messages=messages,
            tools=ANOMALY_TOOLS,
            system=ANOMALY_SYSTEM_PROMPT,
        )

        # 从消息历史中提取汇总结果
        result = self._extract_summary_result(messages)

        if result:
            self.log(
                f"检测完成 ✓ | 共 {result.get('total', 0)} 条异常 | "
                f"高风险 {result.get('high_risk', 0)} | "
                f"中风险 {result.get('medium_risk', 0)} | "
                f"低风险 {result.get('low_risk', 0)}"
            )
        else:
            self.log("检测完成（无汇总数据）")
            result = {"total": 0, "all_anomalies": [], "note": final_text}

        return result

    def _extract_summary_result(self, messages: list) -> dict:
        """从消息历史中提取最后一次 summarize_anomalies 的结果"""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in reversed(content):
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            try:
                                data = json.loads(block.get("content", "{}"))
                                if "total" in data and "all_anomalies" in data:
                                    return data
                            except (json.JSONDecodeError, TypeError):
                                continue
        return None


# ──────────────────────────────────────────────
# 独立测试
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()

    print("=== AnomalyAgent 独立测试（Mock 模式）===\n")

    agent = AnomalyAgent(mock_mode=True)
    result = agent.run("mock")

    print("\n检测结果汇总：")
    print(f"总异常数: {result.get('total', 0)}")
    print(f"高风险: {result.get('high_risk', 0)}")
    print(f"中风险: {result.get('medium_risk', 0)}")
    print(f"低风险: {result.get('low_risk', 0)}")
    print(f"\n按类型统计: {json.dumps(result.get('by_type', {}), ensure_ascii=False)}")

    print("\n异常详情：")
    for a in result.get("all_anomalies", []):
        if "anomaly_type" in a:
            risk_icon = {"高": "⚠️", "中": "🔶", "低": "🔷"}.get(a.get("risk_level", ""), "•")
            print(f"{risk_icon} 第{a.get('row_index')}行 | {a.get('anomaly_type')} | {a.get('description', '')[:60]}")
