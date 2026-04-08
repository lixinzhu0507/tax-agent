"""
anomaly_detector.py — 交易异常检测工具
第一层：规则检测（快速、确定性）
第二层：AI 辅助检测（对规则未覆盖的情况）
每条异常记录标注来源：rule / ai
"""

import json
import math
from datetime import datetime, timedelta
from typing import Any


# ──────────────────────────────────────────────
# Mock 交易数据（--mock 模式使用）
# 包含 10 条记录，注入 4 类典型异常
# ──────────────────────────────────────────────
MOCK_TRANSACTIONS = [
    {
        "row_index": 0,
        "date": "2024-01-05",
        "vendor": "Office Depot",
        "description": "办公用品采购",
        "amount": 325.50,
        "invoice_number": "INV-2024-001",
        "payment_method": "corporate_card",
    },
    {
        "row_index": 1,
        "date": "2024-01-10",
        "vendor": "AWS",
        "description": "云服务费用",
        "amount": 1850.00,  # 整数金额（低风险异常）
        "invoice_number": "AWS-20240110",
        "payment_method": "bank_transfer",
    },
    {
        "row_index": 2,
        "date": "2024-01-15",
        "vendor": "Office Depot",
        "description": "办公用品",
        "amount": 500.00,  # 第一笔重复付款（重复异常）
        "invoice_number": "INV-2024-015",
        "payment_method": "corporate_card",
    },
    {
        "row_index": 3,
        "date": "2024-01-16",
        "vendor": "Office Depot",
        "description": "办公用品",
        "amount": 500.00,  # 第二笔重复付款（重复异常）
        "invoice_number": "INV-2024-016",
        "payment_method": "corporate_card",
    },
    {
        "row_index": 4,
        "date": "2024-01-20",
        "vendor": "Consulting LLC",
        "description": "咨询服务费",
        "amount": 5000.00,  # 整数金额（低风险异常）
        "invoice_number": "CONS-2024-005",
        "payment_method": "check",
    },
    {
        "row_index": 5,
        "date": "2024-02-01",
        "vendor": "",          # 缺少供应商（字段缺失异常）
        "description": "采购支出",
        "amount": 2300.00,
        "invoice_number": "",  # 缺少发票号（字段缺失异常）
        "payment_method": "cash",
    },
    {
        "row_index": 6,
        "date": "2024-02-10",
        "vendor": "Staples Inc",
        "description": "打印机耗材",
        "amount": 189.99,
        "invoice_number": "STA-2024-089",
        "payment_method": "corporate_card",
    },
    {
        "row_index": 7,
        "date": "2024-02-15",
        "vendor": "Unknown Vendor",
        "description": "设备采购",
        "amount": 98000.00,   # 超大金额（统计异常）
        "invoice_number": "UNKN-001",
        "payment_method": "wire_transfer",
    },
    {
        "row_index": 8,
        "date": "2024-03-01",
        "vendor": "FedEx",
        "description": "快递费",
        "amount": 67.25,
        "invoice_number": "FDX-20240301",
        "payment_method": "corporate_card",
    },
    {
        "row_index": 9,
        "date": "2024-03-15",
        "vendor": "Adobe Systems",
        "description": "软件订阅",
        "amount": 599.88,
        "invoice_number": "ADO-2024-Q1",
        "payment_method": "corporate_card",
    },
]


# ──────────────────────────────────────────────
# 规则检测
# ──────────────────────────────────────────────
def run_rule_based_checks(transactions: list) -> list:
    """
    对交易列表执行规则检测，返回异常列表
    每条异常格式：{row_index, anomaly_type, risk_level, description, source}
    """
    anomalies = []

    amounts = [t.get("amount", 0) for t in transactions if t.get("amount") is not None]
    mean_amount = sum(amounts) / len(amounts) if amounts else 0
    # 计算标准差
    if len(amounts) > 1:
        variance = sum((x - mean_amount) ** 2 for x in amounts) / len(amounts)
        std_amount = math.sqrt(variance)
    else:
        std_amount = 0

    threshold = mean_amount + 3 * std_amount

    for i, tx in enumerate(transactions):
        row = tx.get("row_index", i)
        amount = tx.get("amount")
        vendor = str(tx.get("vendor", "")).strip()
        invoice = str(tx.get("invoice_number", "")).strip()
        date_str = tx.get("date", "")

        # ── 规则 1：字段缺失 ──
        missing = []
        if not vendor:
            missing.append("供应商名称")
        if not invoice:
            missing.append("发票号")

        if missing:
            anomalies.append({
                "row_index": row,
                "anomaly_type": "missing_fields",
                "risk_level": "中",
                "description": f"缺少必要字段：{', '.join(missing)}",
                "source": "rule",
                "amount": f"${amount:,.2f}" if amount is not None else "N/A",
                "vendor": vendor or "(空)",
            })

        # ── 规则 2：统计异常（超过均值+3σ） ──
        if amount is not None and std_amount > 0 and amount > threshold:
            anomalies.append({
                "row_index": row,
                "anomaly_type": "statistical_outlier",
                "risk_level": "高",
                "description": (
                    f"金额 ${amount:,.2f} 超过统计阈值 ${threshold:,.2f}"
                    f"（均值 ${mean_amount:,.2f} + 3σ ${3*std_amount:,.2f}）"
                ),
                "source": "rule",
                "amount": f"${amount:,.2f}",
                "vendor": vendor,
            })

        # ── 规则 3：整数金额 ≥ $1,000 ──
        if amount is not None and amount >= 1000 and amount == int(amount):
            anomalies.append({
                "row_index": row,
                "anomaly_type": "round_number",
                "risk_level": "低",
                "description": f"金额 ${amount:,.2f} 为整数，可能是估算值而非实际发生金额",
                "source": "rule",
                "amount": f"${amount:,.2f}",
                "vendor": vendor,
            })

    # ── 规则 4：重复付款（相同金额+相同供应商+7天内）──
    for i, tx_a in enumerate(transactions):
        for j, tx_b in enumerate(transactions):
            if i >= j:
                continue
            v_a = str(tx_a.get("vendor", "")).strip().lower()
            v_b = str(tx_b.get("vendor", "")).strip().lower()
            amt_a = tx_a.get("amount")
            amt_b = tx_b.get("amount")

            if not v_a or not v_b or v_a != v_b:
                continue
            if amt_a is None or amt_b is None or amt_a != amt_b:
                continue

            try:
                date_a = datetime.strptime(tx_a.get("date", ""), "%Y-%m-%d")
                date_b = datetime.strptime(tx_b.get("date", ""), "%Y-%m-%d")
                if abs((date_a - date_b).days) <= 7:
                    row_a = tx_a.get("row_index", i)
                    row_b = tx_b.get("row_index", j)
                    anomalies.append({
                        "row_index": row_a,
                        "anomaly_type": "duplicate_payment",
                        "risk_level": "高",
                        "description": (
                            f"疑似重复付款：第 {row_a} 行与第 {row_b} 行，"
                            f"相同供应商 '{tx_a.get('vendor')}'，"
                            f"相同金额 ${amt_a:,.2f}，"
                            f"日期相差 {abs((date_a - date_b).days)} 天"
                        ),
                        "source": "rule",
                        "amount": f"${amt_a:,.2f}",
                        "vendor": tx_a.get("vendor"),
                        "related_row": row_b,
                    })
            except (ValueError, TypeError):
                continue

    return anomalies


def run_ai_based_checks(transactions: list, rule_anomaly_rows: set, client: Any, model: str) -> list:
    """
    对规则未标记的交易进行 AI 二次判断
    client: openai.OpenAI 实例（指向 DeepSeek）
    rule_anomaly_rows: 已被规则标记的行号集合（跳过，避免重复）
    """
    from prompts import ANOMALY_AI_PROMPT

    # 筛选出规则未覆盖的交易
    unchecked = [t for t in transactions if t.get("row_index", 0) not in rule_anomaly_rows]

    if not unchecked:
        return []

    # 构建 AI 请求
    tx_text = json.dumps(unchecked, ensure_ascii=False, indent=2)
    prompt = f"{ANOMALY_AI_PROMPT}\n\n交易数据：\n{tx_text}"

    try:
        # OpenAI 兼容格式（DeepSeek）
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()

        # 提取 JSON
        if raw.startswith("["):
            results = json.loads(raw)
        else:
            # 尝试从代码块中提取
            json_match = __import__("re").search(r"\[.*\]", raw, __import__("re").DOTALL)
            if json_match:
                results = json.loads(json_match.group())
            else:
                results = []

        # 确保来源标注为 ai
        for r in results:
            r["source"] = "ai"
        return results

    except Exception as e:
        return [{"error": str(e), "source": "ai", "note": "AI 检测失败，跳过此步骤"}]


def get_mock_transactions() -> list:
    """返回 Mock 交易数据（用于 --mock 模式）"""
    return MOCK_TRANSACTIONS.copy()


# ──────────────────────────────────────────────
# 独立测试
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=== Anomaly Detector 测试（规则检测）===\n")

    transactions = get_mock_transactions()
    anomalies = run_rule_based_checks(transactions)

    print(f"共检测到 {len(anomalies)} 条异常：\n")
    for a in anomalies:
        risk_icon = {"高": "⚠️", "中": "🔶", "低": "🔷"}.get(a["risk_level"], "•")
        print(f"{risk_icon} [{a['risk_level']}] 第 {a['row_index']} 行 | {a['anomaly_type']}")
        print(f"   {a['description']}")
        print(f"   来源: {a['source']}")
        print()
