"""
document_agent.py — 税务文件处理 Agent
功能：读取 PDF / 图片，提取关键税务字段
支持 --mock 模式，使用预设数据，不依赖真实文件
"""

import json
import sys
import os

# 将项目根目录加入 sys.path（支持独立运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent
from prompts import DOCUMENT_SYSTEM_PROMPT
from tools.ocr_tool import extract_text_from_file, get_mock_document
from tools.data_parser import parse_tax_fields


# ──────────────────────────────────────────────
# 工具定义（Anthropic tool schema）
# ──────────────────────────────────────────────
DOCUMENT_TOOLS = [
    {
        "name": "extract_document_text",
        "description": "从税务文件（PDF 或图片）中提取原始文字内容。如果文件路径为 'mock'，返回预设的 W-2 示例数据。",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件路径，或填 'mock' 使用示例数据，或填 'mock:1099_nec' 等指定类型",
                }
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "parse_document_fields",
        "description": "从提取的原始文字中解析税务字段，返回结构化 JSON（含收入金额、税款代扣、纳税人信息等）。",
        "input_schema": {
            "type": "object",
            "properties": {
                "raw_text": {
                    "type": "string",
                    "description": "从文件中提取的原始文字内容",
                },
                "doc_type_hint": {
                    "type": "string",
                    "description": "文件类型提示：'auto'（自动检测）、'w2'、'1099_nec'、'1099_int'、'invoice'",
                    "default": "auto",
                },
            },
            "required": ["raw_text"],
        },
    },
]


class DocumentAgent(BaseAgent):
    """
    税务文件处理 Agent
    支持解析 W-2、1099-NEC、1099-INT、发票等税务文件
    """

    def __init__(self, mock_mode: bool = False):
        super().__init__(name="DocumentAgent")
        self.mock_mode = mock_mode  # 是否使用 Mock 数据

    def _dispatch_tool(self, tool_name: str, tool_input: dict) -> dict:
        """分发工具调用到具体实现"""

        if tool_name == "extract_document_text":
            file_path = tool_input.get("file_path", "")

            # mock 模式或路径以 "mock" 开头
            if self.mock_mode or file_path.lower().startswith("mock"):
                # 支持 "mock:1099_nec" 格式指定文档类型
                doc_type = "w2"
                if ":" in file_path:
                    doc_type = file_path.split(":", 1)[1].strip()
                return get_mock_document(doc_type)
            else:
                return extract_text_from_file(file_path)

        elif tool_name == "parse_document_fields":
            raw_text = tool_input.get("raw_text", "")
            doc_type_hint = tool_input.get("doc_type_hint", "auto")
            return parse_tax_fields(raw_text, doc_type_hint)

        else:
            return {"error": f"未知工具: {tool_name}"}

    def run(self, file_path: str) -> dict:
        """
        主入口：处理税务文件，提取字段
        file_path: 文件路径，或 "mock" / "mock:1099_nec" 等
        返回：结构化字段 JSON
        """
        self.log(f"开始处理文件: {file_path}")

        # 构造初始消息
        if self.mock_mode:
            user_content = "请处理 Mock W-2 税务文件，提取所有关键字段。"
            display_path = "mock"
        else:
            user_content = f"请处理税务文件 '{file_path}'，提取所有关键字段。"
            display_path = file_path

        messages = [{"role": "user", "content": user_content}]

        self.log("正在解析文件内容...")

        # 执行 tool-use 循环
        messages, final_text = self._run_tool_loop(
            messages=messages,
            tools=DOCUMENT_TOOLS,
            system=DOCUMENT_SYSTEM_PROMPT,
        )

        # 从消息历史中提取最后一次 parse_document_fields 的结果
        result = self._extract_parse_result(messages)

        if result:
            self.log(
                f"提取完成 ✓ | 文件类型: {result.get('document_type')} | "
                f"收入: {result.get('income_amount')} | "
                f"置信度: {result.get('confidence')}"
            )
        else:
            self.log("文件处理完成（未提取到结构化字段）")
            result = {"error": "未能提取到结构化字段", "raw_response": final_text}

        return result

    def _extract_parse_result(self, messages: list) -> dict:
        """
        从消息历史中提取最后一次 parse_document_fields 工具调用的结果
        """
        # 逆序查找 tool_result 消息
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in reversed(content):
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            try:
                                data = json.loads(block.get("content", "{}"))
                                # 检查是否为 parse_document_fields 的输出
                                if "document_type" in data:
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

    print("=== DocumentAgent 独立测试（Mock 模式）===\n")

    agent = DocumentAgent(mock_mode=True)
    result = agent.run("mock")

    print("\n最终提取结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n--- 测试 1099-NEC ---")
    result2 = agent.run("mock:1099_nec")
    print(json.dumps(result2, ensure_ascii=False, indent=2))
