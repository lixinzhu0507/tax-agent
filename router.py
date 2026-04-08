"""
router.py — 任务路由器
使用 DeepSeek API（OpenAI 兼容）分析用户输入，判断任务类型
返回：{"task": "document|research|anomaly|report", "input": "...", "file_path": null}
"""

import json
import os

from openai import OpenAI

from prompts import ROUTER_SYSTEM_PROMPT

# DeepSeek API 配置
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"

# 路由分类工具（OpenAI function calling 格式）
ROUTER_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_task",
        "description": "分析用户输入，判断任务类型并返回路由信息",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "enum": ["document", "research", "anomaly", "report"],
                    "description": (
                        "任务类型：\n"
                        "- document: 处理税务文件（PDF/图片），提取字段\n"
                        "- research: 回答税法问题\n"
                        "- anomaly: 检测交易数据异常（CSV）\n"
                        "- report: 生成完整分析报告"
                    ),
                },
                "input": {
                    "type": "string",
                    "description": "用户的原始输入内容",
                },
                "file_path": {
                    "type": "string",
                    "description": "文件路径（如有），否则为 null",
                },
                "reasoning": {
                    "type": "string",
                    "description": "分类依据的简短说明",
                },
            },
            "required": ["task", "input"],
        },
    },
}


class Router:
    """任务路由器：分析输入并决定调用哪个 Agent"""

    def __init__(self):
        self.client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url=DEEPSEEK_BASE_URL,
        )
        self.model = DEFAULT_MODEL

    def route(
        self,
        user_input: str,
        file_path: str = None,
        has_transactions: bool = False,
        want_report: bool = False,
    ) -> dict:
        """
        分析用户输入，返回路由结果
        返回：{"task": "...", "input": "...", "file_path": "...", "reasoning": "..."}
        """
        # ── 优先处理显式 CLI 参数 ──
        if want_report:
            return {
                "task": "report",
                "input": user_input,
                "file_path": file_path,
                "reasoning": "--report 参数明确请求生成报告",
            }

        if file_path:
            suffix = file_path.lower().rsplit(".", 1)[-1] if "." in file_path else ""
            if suffix == "csv":
                return {
                    "task": "anomaly",
                    "input": user_input,
                    "file_path": file_path,
                    "reasoning": "文件扩展名为 .csv，路由到异常检测",
                }
            elif suffix in ("pdf", "png", "jpg", "jpeg", "tiff"):
                return {
                    "task": "document",
                    "input": user_input,
                    "file_path": file_path,
                    "reasoning": f"文件扩展名为 .{suffix}，路由到文件处理",
                }

        if has_transactions:
            return {
                "task": "anomaly",
                "input": user_input,
                "file_path": file_path,
                "reasoning": "--transactions 参数，路由到异常检测",
            }

        # ── 快速关键词路由（避免不必要的 API 调用）──
        lower = user_input.lower()
        tax_question_keywords = [
            "抵扣", "扣除", "税率", "申报", "退税", "免税", "缴税", "税法",
            "deduct", "tax rate", "irs", "irc", "form", "credit", "withhold",
            "可以", "能否", "如何", "多少", "是否", "怎么",
        ]
        if "?" in user_input or "？" in user_input or any(kw in lower for kw in tax_question_keywords):
            report_keywords = ["生成报告", "分析报告", "generate report", "full report"]
            if not any(kw in lower for kw in report_keywords):
                return {
                    "task": "research",
                    "input": user_input,
                    "file_path": None,
                    "reasoning": "检测到税务问题关键词，路由到税法研究",
                }

        # ── 使用 DeepSeek AI 进行智能分类 ──
        print(f"[Router] 正在识别任务类型...", flush=True)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=256,
                tools=[ROUTER_TOOL],
                # 强制调用指定工具
                tool_choice={"type": "function", "function": {"name": "classify_task"}},
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_input},
                ],
            )

            # 提取工具调用结果
            msg = response.choices[0].message
            if msg.tool_calls:
                tc = msg.tool_calls[0]
                result = json.loads(tc.function.arguments)
                result.setdefault("file_path", file_path)
                result.setdefault("reasoning", "AI 分类")
                return result

        except Exception as e:
            print(f"[Router] 分类失败，使用默认路由: {e}", flush=True)

        # fallback：默认路由到研究
        return {
            "task": "research",
            "input": user_input,
            "file_path": file_path,
            "reasoning": "分类失败，默认路由到税法研究",
        }


# ──────────────────────────────────────────────
# 独立测试
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import dotenv
    dotenv.load_dotenv()

    router = Router()

    test_cases = [
        ("我的家庭办公室可以抵扣多少税？", None, False, False),
        ("处理这份 W-2 文件", "w2_sample.pdf", False, False),
        ("检查交易记录", "transactions.csv", False, False),
        ("生成完整报告", None, True, True),
        ("Can I deduct home office expenses?", None, False, False),
    ]

    print("=== Router 路由测试 ===\n")
    for user_input, file_path, has_tx, want_report in test_cases:
        result = router.route(user_input, file_path, has_tx, want_report)
        print(f"输入: {user_input!r}")
        print(f"路由: task={result['task']}, file_path={result.get('file_path')}")
        print(f"依据: {result.get('reasoning')}")
        print()
