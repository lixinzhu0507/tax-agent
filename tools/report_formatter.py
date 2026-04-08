"""
report_formatter.py — 报告格式化工具
将各 Agent 的输出整合成 Markdown 或 JSON 格式的专业报告
"""

import json
from datetime import datetime
from typing import Optional


# ──────────────────────────────────────────────
# Markdown 报告生成
# ──────────────────────────────────────────────
def format_as_markdown(data: dict) -> str:
    """
    将汇总数据格式化为 Markdown 报告
    data 结构：{
        "executive_summary": [...],
        "document_results": {...},
        "anomaly_results": [...],
        "research_results": {...},
        "action_items": [...]
    }
    """
    lines = []
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")

    # ── 报告头部 ──
    lines.append("━" * 50)
    lines.append("")
    lines.append("# 税务文件分析报告")
    lines.append(f"> 生成时间：{now}")
    lines.append(f"> 本报告由 AI 税务 Agent 自动生成，仅供参考。具体税务决策请咨询持证税务专业人士。")
    lines.append("")
    lines.append("━" * 50)
    lines.append("")

    # ── 第一章：执行摘要 ──
    lines.append("## 一、执行摘要")
    lines.append("")
    summary = data.get("executive_summary", [])
    if summary:
        for item in summary:
            lines.append(f"- {item}")
    else:
        lines.append("- 暂无摘要信息")
    lines.append("")

    # ── 第二章：文件处理结果 ──
    lines.append("## 二、文件处理结果")
    lines.append("")
    doc = data.get("document_results")
    if doc and isinstance(doc, dict) and not doc.get("error"):
        lines.append(f"| 字段 | 内容 |")
        lines.append(f"|------|------|")
        field_labels = {
            "document_type": "文件类型",
            "taxpayer_name": "纳税人姓名",
            "employer_name": "雇主/付款方",
            "income_amount": "收入金额",
            "tax_withheld_federal": "联邦税代扣",
            "tax_withheld_state": "州税代扣",
            "period": "税务期间",
            "invoice_number": "发票号",
            "confidence": "提取置信度",
        }
        for key, label in field_labels.items():
            value = doc.get(key)
            display = value if value is not None else "_未提取到_"
            lines.append(f"| {label} | {display} |")
    elif doc and doc.get("error"):
        lines.append(f"> ⚠️ 文件处理失败：{doc['error']}")
    else:
        lines.append("> 本次分析未包含税务文件处理。")
    lines.append("")

    # ── 第三章：异常交易清单 ──
    lines.append("## 三、异常交易清单")
    lines.append("")
    anomalies = data.get("anomaly_results", [])
    # 过滤掉错误信息，只保留真正的异常
    real_anomalies = [a for a in anomalies if "anomaly_type" in a]

    if real_anomalies:
        # 按风险等级排序：高 > 中 > 低
        risk_order = {"高": 0, "中": 1, "低": 2}
        real_anomalies.sort(key=lambda x: risk_order.get(x.get("risk_level", "低"), 3))

        risk_icons = {"高": "⚠️ 高风险", "中": "🔶 中风险", "低": "🔷 低风险"}
        type_names = {
            "duplicate_payment": "重复付款",
            "statistical_outlier": "金额异常",
            "missing_fields": "字段缺失",
            "round_number": "整数金额",
            "ai_flagged": "AI 识别",
        }

        for a in real_anomalies:
            risk_label = risk_icons.get(a.get("risk_level", "低"), "• 未知")
            type_label = type_names.get(a.get("anomaly_type", ""), a.get("anomaly_type", ""))
            lines.append(f"### {risk_label} — {type_label}（第 {a.get('row_index', '?')} 行）")
            lines.append("")
            lines.append(f"**描述**：{a.get('description', '')}")
            if a.get("amount"):
                lines.append(f"**金额**：{a['amount']}")
            if a.get("vendor"):
                lines.append(f"**供应商**：{a['vendor']}")
            lines.append(f"**检测来源**：{a.get('source', 'rule')}")
            lines.append("")

        # 汇总统计
        high = sum(1 for a in real_anomalies if a.get("risk_level") == "高")
        mid = sum(1 for a in real_anomalies if a.get("risk_level") == "中")
        low = sum(1 for a in real_anomalies if a.get("risk_level") == "低")
        lines.append(f"> **汇总**：共 {len(real_anomalies)} 条异常 | ⚠️ 高风险 {high} 条 | 🔶 中风险 {mid} 条 | 🔷 低风险 {low} 条")
    else:
        lines.append("> ✅ 未检测到异常交易。")
    lines.append("")

    # ── 第四章：税法建议 ──
    lines.append("## 四、税法建议")
    lines.append("")
    research = data.get("research_results")
    if research and isinstance(research, dict):
        answer = research.get("answer", "")
        citations = research.get("citations", [])
        notes = research.get("notes", "")

        if answer:
            lines.append(answer)
            lines.append("")

        if citations:
            lines.append("**法律依据**：")
            for c in citations:
                lines.append(f"- {c}")
            lines.append("")

        if notes:
            lines.append(f"> ⚠️ **注意**：{notes}")
            lines.append("")
    else:
        lines.append("> 本次分析未包含税法问答。")
    lines.append("")

    # ── 第五章：待办事项 ──
    lines.append("## 五、待办事项（需人工复查）")
    lines.append("")
    action_items = data.get("action_items", [])

    # 自动生成待办（基于异常）
    auto_items = []
    if real_anomalies:
        high_risk = [a for a in real_anomalies if a.get("risk_level") == "高"]
        for a in high_risk:
            if a.get("anomaly_type") == "duplicate_payment":
                auto_items.append(f"- [ ] 核查第 {a.get('row_index')} 行重复付款，确认是否为真实双次交易")
            elif a.get("anomaly_type") == "statistical_outlier":
                auto_items.append(f"- [ ] 审核第 {a.get('row_index')} 行大额支出 {a.get('amount', '')}，获取相关合同/发票")

        mid_risk = [a for a in real_anomalies if a.get("risk_level") == "中"]
        for a in mid_risk:
            if a.get("anomaly_type") == "missing_fields":
                auto_items.append(f"- [ ] 补充第 {a.get('row_index')} 行缺失的 {a.get('description', '字段信息')}")

    # 合并手动和自动待办
    all_items = list(action_items) + auto_items
    if all_items:
        for item in all_items:
            if not item.startswith("- [ ]"):
                item = f"- [ ] {item}"
            lines.append(item)
    else:
        lines.append("- [ ] 请会计师审核本报告并确认所有数据准确性")
    lines.append("")

    # ── 报告尾部 ──
    lines.append("---")
    lines.append("")
    lines.append("*⚠️ 免责声明：本报告由 AI 系统自动生成，仅供会计师参考使用。*")
    lines.append("*税务相关决策请以最新 IRS 指引和专业税务顾问意见为准。*")
    lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# JSON 报告生成
# ──────────────────────────────────────────────
def format_as_json(data: dict) -> str:
    """将汇总数据格式化为 JSON 字符串"""
    output = {
        "report_generated_at": datetime.now().isoformat(),
        "executive_summary": data.get("executive_summary", []),
        "document_results": data.get("document_results"),
        "anomaly_results": data.get("anomaly_results", []),
        "research_results": data.get("research_results"),
        "action_items": data.get("action_items", []),
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# 生成执行摘要（辅助函数）
# ──────────────────────────────────────────────
def generate_executive_summary(data: dict) -> list:
    """
    根据各 Agent 输出自动生成执行摘要（3-5 条）
    """
    summary = []

    # 文件处理摘要
    doc = data.get("document_results")
    if doc and not doc.get("error"):
        doc_type = doc.get("document_type", "税务文件")
        income = doc.get("income_amount")
        employer = doc.get("employer_name")
        period = doc.get("period")
        if income and employer:
            summary.append(
                f"成功提取 {doc_type}（{employer}，{period}）：收入 {income}，"
                f"联邦税代扣 {doc.get('tax_withheld_federal', 'N/A')}"
            )

    # 异常检测摘要
    anomalies = data.get("anomaly_results", [])
    real_anomalies = [a for a in anomalies if "anomaly_type" in a]
    if real_anomalies:
        high = sum(1 for a in real_anomalies if a.get("risk_level") == "高")
        if high > 0:
            summary.append(
                f"⚠️ 检测到 {high} 条高风险异常交易，需立即人工复查（含重复付款或大额异常支出）"
            )
        else:
            summary.append(
                f"共检测到 {len(real_anomalies)} 条潜在异常交易（均为中低风险），建议核查"
            )
    else:
        summary.append("✅ 交易数据审查通过，未发现明显异常")

    # 税法建议摘要
    research = data.get("research_results")
    if research and research.get("answer"):
        summary.append("已提供税法查询结果，请参考第四章详细内容及法律依据")

    # 文件置信度警告
    if doc and doc.get("confidence") == "low":
        summary.append("⚠️ 文件字段提取置信度较低，建议人工核对原始文件所有字段")

    # 确保至少 3 条
    if len(summary) < 3:
        summary.append("建议定期运行税务合规检查，保持记录完整性")

    return summary[:5]  # 最多 5 条


# ──────────────────────────────────────────────
# 独立测试
# ──────────────────────────────────────────────
if __name__ == "__main__":
    # 构造测试数据
    test_data = {
        "executive_summary": [],
        "document_results": {
            "document_type": "W-2",
            "taxpayer_name": "Jane Doe",
            "employer_name": "Anthropic Inc",
            "income_amount": "$120,000.00",
            "tax_withheld_federal": "$24,000.00",
            "tax_withheld_state": "$7,200.00",
            "period": "2024",
            "invoice_number": None,
            "confidence": "high",
        },
        "anomaly_results": [
            {
                "row_index": 2,
                "anomaly_type": "duplicate_payment",
                "risk_level": "高",
                "description": "疑似重复付款",
                "source": "rule",
                "amount": "$500.00",
                "vendor": "Office Depot",
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
        "research_results": {
            "answer": "根据 IRC Section 280A，家庭办公室抵扣须满足专用性要求。",
            "citations": ["IRC § 280A", "IRS Publication 587"],
            "notes": "建议咨询持证税务专业人士",
        },
        "action_items": [],
    }

    test_data["executive_summary"] = generate_executive_summary(test_data)

    print("=== Markdown 报告预览 ===\n")
    print(format_as_markdown(test_data))
