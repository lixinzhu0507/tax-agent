"""
ocr_tool.py — PDF / 图片文字提取工具
支持 pypdf（PDF）和 pytesseract（图片）
--mock 模式下返回预设数据，不依赖真实文件
"""

import os
from pathlib import Path


# ──────────────────────────────────────────────
# Mock 数据：用于测试，不需要真实文件
# ──────────────────────────────────────────────
MOCK_DOCUMENTS = {
    "w2": """
FORM W-2 Wage and Tax Statement 2024
Employer identification number (EIN): 94-1234567
Employer's name, address, and ZIP code:
ANTHROPIC INC
123 Market Street, San Francisco, CA 94105

Employee's social security number: ***-**-6789
Employee's name: Jane Doe
123 Elm Street, San Francisco, CA 94102

Box 1 - Wages, tips, other compensation: 120000.00
Box 2 - Federal income tax withheld: 24000.00
Box 3 - Social security wages: 120000.00
Box 4 - Social security tax withheld: 7440.00
Box 5 - Medicare wages and tips: 120000.00
Box 6 - Medicare tax withheld: 1740.00
Box 16 - State wages: 120000.00
Box 17 - State income tax withheld: 7200.00
State: CA
""",
    "1099_nec": """
FORM 1099-NEC Nonemployee Compensation 2024
PAYER'S name: ACME CONSULTING LLC
PAYER'S TIN: 12-3456789
RECIPIENT'S TIN: ***-**-4321
RECIPIENT'S name: John Smith
456 Oak Avenue, Austin, TX 78701

Box 1 - Nonemployee compensation: 45000.00
Box 4 - Federal income tax withheld: 0.00
State income: 45000.00
State tax withheld: 0.00
State: TX
""",
    "1099_int": """
FORM 1099-INT Interest Income 2024
PAYER'S name: FIRST NATIONAL BANK
PAYER'S TIN: 98-7654321
RECIPIENT'S name: Jane Doe
123 Elm Street, San Francisco, CA 94102

Box 1 - Interest income: 1250.75
Box 2 - Early withdrawal penalty: 0.00
Box 4 - Federal income tax withheld: 0.00
""",
    "invoice": """
INVOICE
Invoice Number: INV-2024-00892
Invoice Date: 2024-03-15
Due Date: 2024-04-15

FROM:
TechSupplies Corp
789 Industrial Blvd
Chicago, IL 60601
EIN: 36-9876543

TO:
Acme Consulting LLC
456 Business Park
Austin, TX 78701

DESCRIPTION:
- 5x Laptop Computer (Dell XPS 15)  @ $1,800.00 each = $9,000.00
- 2x Monitor (27" 4K)               @ $650.00 each  = $1,300.00
- Shipping & Handling                               =   $150.00

Subtotal:  $10,450.00
Tax (8%):     $836.00
TOTAL DUE: $11,286.00

Payment terms: Net 30
""",
}


def extract_text_from_pdf(file_path: str) -> dict:
    """
    从 PDF 文件中提取文字内容
    使用 pypdf 库，如果文件不存在则返回错误信息
    """
    path = Path(file_path)
    if not path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}", "text": ""}

    try:
        # 延迟导入，避免没有安装 pypdf 时整个模块失败
        import pypdf

        text_parts = []
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"[Page {i + 1}]\n{page_text}")

        full_text = "\n\n".join(text_parts)
        return {
            "success": True,
            "text": full_text,
            "pages": len(reader.pages),
            "source": "pypdf",
        }

    except ImportError:
        return {
            "success": False,
            "error": "pypdf 未安装，请运行: pip install pypdf",
            "text": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "text": ""}


def extract_text_from_image(file_path: str) -> dict:
    """
    从图片文件中提取文字（OCR）
    使用 pytesseract + Pillow，需要安装 Tesseract OCR 引擎
    """
    path = Path(file_path)
    if not path.exists():
        return {"success": False, "error": f"文件不存在: {file_path}", "text": ""}

    try:
        import pytesseract
        from PIL import Image

        img = Image.open(file_path)
        # 转为灰度提升 OCR 精度
        img = img.convert("L")
        text = pytesseract.image_to_string(img, lang="eng")

        return {
            "success": True,
            "text": text,
            "image_size": f"{img.width}x{img.height}",
            "source": "tesseract",
        }

    except ImportError:
        return {
            "success": False,
            "error": "pytesseract 或 Pillow 未安装，请运行: pip install pytesseract Pillow",
            "text": "",
        }
    except Exception as e:
        return {"success": False, "error": str(e), "text": ""}


def extract_text_from_file(file_path: str) -> dict:
    """
    自动检测文件类型并提取文字
    支持 PDF、PNG、JPG、JPEG
    """
    suffix = Path(file_path).suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(file_path)
    elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
        return extract_text_from_image(file_path)
    else:
        return {
            "success": False,
            "error": f"不支持的文件格式: {suffix}",
            "text": "",
        }


def get_mock_document(doc_type: str = "w2") -> dict:
    """
    返回预设的 Mock 文档内容（用于测试，不需要真实文件）
    doc_type: "w2" | "1099_nec" | "1099_int" | "invoice"
    """
    doc_type = doc_type.lower().replace("-", "_")
    if doc_type not in MOCK_DOCUMENTS:
        # 默认返回 W-2
        doc_type = "w2"

    return {
        "success": True,
        "text": MOCK_DOCUMENTS[doc_type],
        "source": "mock",
        "doc_type_hint": doc_type,
    }


# ──────────────────────────────────────────────
# 独立测试
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=== OCR Tool 测试（Mock 模式）===\n")

    # 测试 W-2 mock
    result = get_mock_document("w2")
    print("Mock W-2 文档:")
    print(result["text"][:300])
    print("...")

    # 测试 1099 mock
    result = get_mock_document("1099_nec")
    print("\nMock 1099-NEC 文档:")
    print(result["text"][:200])

    # 测试不存在的文件
    result = extract_text_from_file("nonexistent.pdf")
    print(f"\n不存在文件测试: success={result['success']}, error={result['error']}")
