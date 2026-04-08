"""
data_parser.py — 税务文档字段解析工具
从 OCR 提取的原始文字中识别并结构化税务字段
使用正则表达式 + 关键词匹配，输出标准 JSON
"""

import re
from typing import Optional


# ──────────────────────────────────────────────
# 金额格式化辅助函数
# ──────────────────────────────────────────────
def _fmt_amount(value: Optional[float]) -> Optional[str]:
    """将数值格式化为 $X,XXX.XX 格式，None 返回 null"""
    if value is None:
        return None
    return f"${value:,.2f}"


def _parse_amount(text: str, patterns: list) -> Optional[float]:
    """用正则从文字中提取金额数值"""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # 去除逗号后转为 float
            raw = match.group(1).replace(",", "")
            try:
                return float(raw)
            except ValueError:
                continue
    return None


def _parse_name(text: str, patterns: list) -> Optional[str]:
    """用正则从文字中提取名称"""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


# ──────────────────────────────────────────────
# 文件类型检测
# ──────────────────────────────────────────────
def _detect_doc_type(text: str) -> str:
    """根据关键词判断文件类型"""
    text_upper = text.upper()
    if "FORM W-2" in text_upper or "WAGE AND TAX STATEMENT" in text_upper:
        return "W-2"
    elif "FORM 1099-NEC" in text_upper or "NONEMPLOYEE COMPENSATION" in text_upper:
        return "1099-NEC"
    elif "FORM 1099-INT" in text_upper or "INTEREST INCOME" in text_upper:
        return "1099-INT"
    elif "FORM 1099-MISC" in text_upper or "MISCELLANEOUS" in text_upper:
        return "1099-MISC"
    elif "INVOICE" in text_upper and ("TOTAL DUE" in text_upper or "AMOUNT DUE" in text_upper):
        return "Invoice"
    else:
        return "Unknown"


# ──────────────────────────────────────────────
# W-2 字段解析
# ──────────────────────────────────────────────
def _parse_w2(text: str) -> dict:
    """提取 W-2 表单字段"""

    # 雇主名称：寻找 EIN 后面的公司名行
    employer = _parse_name(text, [
        r"Employer['\u2019]?s name[,\s]+address.*?\n([A-Z][A-Z\s&.,]+(?:INC|LLC|CORP|CO|LTD|INC\.|LLC\.)?)",
        r"EIN\):\s*[\d-]+\s*\n\s*([A-Z][A-Z\s&.,]+)",
    ])

    # 雇员姓名
    taxpayer = _parse_name(text, [
        r"Employee['\u2019]?s name\s*[:\n]\s*([A-Za-z\s]+)",
        r"Employee['\u2019]?s name[,\s]+address.*?\n.*?\n([A-Za-z][A-Za-z\s]+)\n",
    ])

    # Box 1: 工资收入
    income = _parse_amount(text, [
        r"Box\s*1[^:]*:\s*([\d,]+\.?\d*)",
        r"Wages,\s*tips.*?:\s*([\d,]+\.?\d*)",
    ])

    # Box 2: 联邦税代扣
    fed_tax = _parse_amount(text, [
        r"Box\s*2[^:]*:\s*([\d,]+\.?\d*)",
        r"Federal income tax withheld[^:]*:\s*([\d,]+\.?\d*)",
    ])

    # Box 17: 州税代扣
    state_tax = _parse_amount(text, [
        r"Box\s*17[^:]*:\s*([\d,]+\.?\d*)",
        r"State income tax[^:]*:\s*([\d,]+\.?\d*)",
    ])

    # 税年
    period_match = re.search(r"(20\d{2})", text)
    period = period_match.group(1) if period_match else None

    return {
        "document_type": "W-2",
        "taxpayer_name": taxpayer,
        "employer_name": employer,
        "income_amount": _fmt_amount(income),
        "tax_withheld_federal": _fmt_amount(fed_tax),
        "tax_withheld_state": _fmt_amount(state_tax),
        "period": period,
        "invoice_number": None,
        "confidence": _calc_confidence([taxpayer, employer, income, fed_tax]),
    }


# ──────────────────────────────────────────────
# 1099-NEC 字段解析
# ──────────────────────────────────────────────
def _parse_1099_nec(text: str) -> dict:
    """提取 1099-NEC 表单字段"""

    payer = _parse_name(text, [
        r"PAYER['\u2019]?S name[:\s]+([A-Za-z][\w\s&.,]+)",
    ])

    recipient = _parse_name(text, [
        r"RECIPIENT['\u2019]?S name[:\s]+([A-Za-z][\w\s]+)",
    ])

    income = _parse_amount(text, [
        r"Box\s*1[^:]*:\s*([\d,]+\.?\d*)",
        r"Nonemployee compensation[^:]*:\s*([\d,]+\.?\d*)",
    ])

    fed_tax = _parse_amount(text, [
        r"Box\s*4[^:]*:\s*([\d,]+\.?\d*)",
        r"Federal income tax withheld[^:]*:\s*([\d,]+\.?\d*)",
    ])

    state_tax = _parse_amount(text, [
        r"State tax withheld[^:]*:\s*([\d,]+\.?\d*)",
    ])

    period_match = re.search(r"(20\d{2})", text)
    period = period_match.group(1) if period_match else None

    return {
        "document_type": "1099-NEC",
        "taxpayer_name": recipient,
        "employer_name": payer,
        "income_amount": _fmt_amount(income),
        "tax_withheld_federal": _fmt_amount(fed_tax),
        "tax_withheld_state": _fmt_amount(state_tax),
        "period": period,
        "invoice_number": None,
        "confidence": _calc_confidence([recipient, payer, income]),
    }


# ──────────────────────────────────────────────
# 1099-INT 字段解析
# ──────────────────────────────────────────────
def _parse_1099_int(text: str) -> dict:
    """提取 1099-INT 表单字段"""

    payer = _parse_name(text, [
        r"PAYER['\u2019]?S name[:\s]+([A-Za-z][\w\s&.,]+)",
    ])

    recipient = _parse_name(text, [
        r"RECIPIENT['\u2019]?S name[:\s]+([A-Za-z][\w\s]+)",
    ])

    income = _parse_amount(text, [
        r"Box\s*1[^:]*:\s*([\d,]+\.?\d*)",
        r"Interest income[^:]*:\s*([\d,]+\.?\d*)",
    ])

    fed_tax = _parse_amount(text, [
        r"Box\s*4[^:]*:\s*([\d,]+\.?\d*)",
        r"Federal income tax withheld[^:]*:\s*([\d,]+\.?\d*)",
    ])

    period_match = re.search(r"(20\d{2})", text)
    period = period_match.group(1) if period_match else None

    return {
        "document_type": "1099-INT",
        "taxpayer_name": recipient,
        "employer_name": payer,
        "income_amount": _fmt_amount(income),
        "tax_withheld_federal": _fmt_amount(fed_tax),
        "tax_withheld_state": None,
        "period": period,
        "invoice_number": None,
        "confidence": _calc_confidence([recipient, payer, income]),
    }


# ──────────────────────────────────────────────
# 发票字段解析
# ──────────────────────────────────────────────
def _parse_invoice(text: str) -> dict:
    """提取发票字段"""

    # 发票号
    inv_num = _parse_name(text, [
        r"Invoice\s*(?:Number|No\.?|#)[:\s]+([A-Z0-9-]+)",
        r"INV[- ]*([A-Z0-9-]+)",
    ])

    # 付款方（FROM）
    payer = _parse_name(text, [
        r"FROM:\s*\n([A-Za-z][\w\s&.,]+)\n",
    ])

    # 收款方（TO）
    recipient = _parse_name(text, [
        r"TO:\s*\n([A-Za-z][\w\s&.,]+)\n",
    ])

    # 总金额
    total = _parse_amount(text, [
        r"TOTAL\s*DUE[:\s]*([\d,]+\.?\d*)",
        r"AMOUNT\s*DUE[:\s]*([\d,]+\.?\d*)",
        r"Total[:\s]+([\d,]+\.?\d*)",
    ])

    # 税前小计
    subtotal = _parse_amount(text, [
        r"Subtotal[:\s]+([\d,]+\.?\d*)",
    ])

    # 发票日期
    date_match = re.search(
        r"Invoice\s*Date[:\s]+(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})",
        text,
        re.IGNORECASE,
    )
    period = date_match.group(1) if date_match else None

    return {
        "document_type": "Invoice",
        "taxpayer_name": recipient,
        "employer_name": payer,
        "income_amount": _fmt_amount(total),
        "tax_withheld_federal": None,
        "tax_withheld_state": _fmt_amount(subtotal),  # 复用字段存小计
        "period": period,
        "invoice_number": inv_num,
        "confidence": _calc_confidence([inv_num, payer, recipient, total]),
    }


# ──────────────────────────────────────────────
# 置信度计算
# ──────────────────────────────────────────────
def _calc_confidence(fields: list) -> str:
    """根据成功提取的字段数量计算置信度"""
    non_null = sum(1 for f in fields if f is not None)
    ratio = non_null / len(fields) if fields else 0
    if ratio >= 0.75:
        return "high"
    elif ratio >= 0.5:
        return "medium"
    else:
        return "low"


# ──────────────────────────────────────────────
# 主入口：解析税务字段
# ──────────────────────────────────────────────
def parse_tax_fields(raw_text: str, doc_type_hint: str = "auto") -> dict:
    """
    从原始文字中提取税务字段
    doc_type_hint: "auto" | "w2" | "1099_nec" | "1099_int" | "invoice"
    返回标准化 JSON，字段缺失填 null
    """
    if not raw_text or not raw_text.strip():
        return {
            "document_type": "Unknown",
            "error": "文档内容为空",
            "confidence": "low",
        }

    # 自动检测文件类型
    if doc_type_hint == "auto" or doc_type_hint not in ("w2", "1099_nec", "1099_int", "invoice"):
        detected = _detect_doc_type(raw_text)
    else:
        type_map = {
            "w2": "W-2",
            "1099_nec": "1099-NEC",
            "1099_int": "1099-INT",
            "invoice": "Invoice",
        }
        detected = type_map.get(doc_type_hint, _detect_doc_type(raw_text))

    # 根据类型选择解析器
    if detected == "W-2":
        return _parse_w2(raw_text)
    elif detected == "1099-NEC":
        return _parse_1099_nec(raw_text)
    elif detected == "1099-INT":
        return _parse_1099_int(raw_text)
    elif detected == "Invoice":
        return _parse_invoice(raw_text)
    else:
        # 未知类型：尝试通用提取
        return {
            "document_type": "Unknown",
            "taxpayer_name": None,
            "employer_name": None,
            "income_amount": None,
            "tax_withheld_federal": None,
            "tax_withheld_state": None,
            "period": None,
            "invoice_number": None,
            "confidence": "low",
            "note": "无法识别文件类型，请人工核查",
        }


# ──────────────────────────────────────────────
# 独立测试
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import json
    from ocr_tool import get_mock_document

    print("=== Data Parser 测试 ===\n")

    for doc_type in ["w2", "1099_nec", "1099_int", "invoice"]:
        mock = get_mock_document(doc_type)
        result = parse_tax_fields(mock["text"])
        print(f"--- {doc_type.upper()} 解析结果 ---")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()
