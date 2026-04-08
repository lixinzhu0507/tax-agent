"""
research_agent.py — 税法研究 Agent
功能：回答税法相关问题，每个答案必须引用法律依据
支持中英文提问，内置知识库搜索
"""

import json
import os
import re
import sys
from pathlib import Path

# 将项目根目录加入 sys.path（支持独立运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base_agent import BaseAgent
from prompts import RESEARCH_SYSTEM_PROMPT

# 知识库文件路径
KNOWLEDGE_FILE = Path(__file__).parent.parent / "knowledge" / "tax_guidelines.md"


# ──────────────────────────────────────────────
# 工具定义
# ──────────────────────────────────────────────
RESEARCH_TOOLS = [
    {
        "name": "search_tax_guidelines",
        "description": "在内置税法知识库中搜索与问题相关的内容，返回相关的 Q&A 条目。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，如 '家庭办公室'、'Section 179'、'capital gains' 等",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "format_tax_answer",
        "description": "将税法答案格式化为标准结构，包含核心答案、详细说明、法律依据和注意事项。",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "用户的原始问题",
                },
                "answer": {
                    "type": "string",
                    "description": "核心答案内容（包含法律依据）",
                },
                "citations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "法律依据列表，如 ['IRC § 280A', 'IRS Publication 587']",
                },
                "needs_professional": {
                    "type": "boolean",
                    "description": "是否建议咨询税务专业人士（情况复杂或因人而异时为 true）",
                },
                "notes": {
                    "type": "string",
                    "description": "补充说明或警告（可选）",
                },
            },
            "required": ["question", "answer", "citations"],
        },
    },
]


# ──────────────────────────────────────────────
# 知识库搜索实现
# ──────────────────────────────────────────────
def _search_knowledge_base(query: str) -> dict:
    """
    在 tax_guidelines.md 中搜索相关内容
    使用关键词匹配，返回最相关的 Q&A 条目
    """
    if not KNOWLEDGE_FILE.exists():
        return {"results": [], "error": "知识库文件不存在"}

    content = KNOWLEDGE_FILE.read_text(encoding="utf-8")
    query_lower = query.lower()

    # 将关键词拆分（支持中文和英文）
    keywords = re.split(r"[\s,，]+", query_lower)
    keywords = [k for k in keywords if len(k) > 1]

    # 按 ## 分割 Q&A 条目
    sections = re.split(r"(?=^## )", content, flags=re.MULTILINE)
    results = []

    for section in sections:
        if not section.strip() or section.startswith("# "):
            continue

        section_lower = section.lower()
        # 计算命中关键词数量
        hits = sum(1 for kw in keywords if kw in section_lower)

        if hits > 0:
            # 提取标题
            title_match = re.match(r"## (.*)", section)
            title = title_match.group(1) if title_match else "相关条目"
            results.append({
                "title": title,
                "content": section.strip(),
                "relevance_score": hits,
            })

    # 按相关度排序，最多返回 3 条
    results.sort(key=lambda x: x["relevance_score"], reverse=True)
    top_results = results[:3]

    return {
        "results": top_results,
        "total_found": len(results),
        "query": query,
    }


def _format_tax_answer(
    question: str,
    answer: str,
    citations: list,
    needs_professional: bool = False,
    notes: str = "",
) -> dict:
    """格式化税法答案为标准结构"""
    formatted = {
        "question": question,
        "answer": answer,
        "citations": citations,
        "needs_professional": needs_professional,
    }
    if notes:
        formatted["notes"] = notes
    if needs_professional:
        disclaimer = "建议咨询持证税务专业人士（CPA / EA / Tax Attorney）以获取针对您具体情况的建议。"
        formatted["disclaimer"] = disclaimer

    return formatted


class ResearchAgent(BaseAgent):
    """税法研究 Agent，回答税务问题并提供权威引用"""

    def __init__(self):
        super().__init__(name="ResearchAgent")

    def _dispatch_tool(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "search_tax_guidelines":
            return _search_knowledge_base(tool_input.get("query", ""))

        elif tool_name == "format_tax_answer":
            return _format_tax_answer(
                question=tool_input.get("question", ""),
                answer=tool_input.get("answer", ""),
                citations=tool_input.get("citations", []),
                needs_professional=tool_input.get("needs_professional", False),
                notes=tool_input.get("notes", ""),
            )

        else:
            return {"error": f"未知工具: {tool_name}"}

    def run(self, question: str) -> dict:
        """
        主入口：回答税法问题
        question: 用户的税法问题（支持中英文）
        返回：结构化答案 JSON
        """
        self.log(f"接收到问题: {question}")
        self.log("正在搜索税法知识库...")

        messages = [{"role": "user", "content": f"请回答以下税务问题：{question}"}]

        # 执行 tool-use 循环
        messages, final_text = self._run_tool_loop(
            messages=messages,
            tools=RESEARCH_TOOLS,
            system=RESEARCH_SYSTEM_PROMPT,
        )

        # 从消息历史中提取最后一次 format_tax_answer 的结果
        result = self._extract_answer_result(messages)

        if result:
            citations_count = len(result.get("citations", []))
            self.log(f"回答完成 ✓ | 引用 {citations_count} 条法律依据")
        else:
            self.log("问题回答完成")
            result = {"answer": final_text, "citations": [], "question": question}

        return result

    def _extract_answer_result(self, messages: list) -> dict:
        """从消息历史中提取最后一次 format_tax_answer 的结果"""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in reversed(content):
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            try:
                                data = json.loads(block.get("content", "{}"))
                                if "answer" in data and "citations" in data:
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

    print("=== ResearchAgent 独立测试 ===\n")

    agent = ResearchAgent()

    # 测试中文问题
    questions = [
        "我的家庭办公室可以抵扣多少税？",
        "2024 年 401(k) 缴费上限是多少？",
    ]

    for q in questions:
        print(f"\n问题：{q}")
        print("-" * 40)
        result = agent.run(q)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()
