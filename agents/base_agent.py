"""
base_agent.py — 所有 Agent 的基类
使用 OpenAI 库对接 DeepSeek API（OpenAI 兼容格式）
提供：
  - tool-use agentic loop（OpenAI function calling 格式）
  - 流式输出支持
  - 统一日志打印
"""

import json
import os
from typing import Any

from openai import OpenAI

# DeepSeek 模型名
DEFAULT_MODEL = "deepseek-chat"

# DeepSeek API 地址
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class BaseAgent:
    """
    所有 Agent 的基类。
    子类需要实现 run() 方法，并调用 _run_tool_loop() 和 _stream_response()。
    """

    def __init__(self, name: str, model: str = DEFAULT_MODEL):
        self.name = name
        self.model = model
        # 初始化 OpenAI 客户端，指向 DeepSeek
        self.client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            base_url=DEEPSEEK_BASE_URL,
        )

    def log(self, msg: str) -> None:
        """打印带 Agent 名称前缀的日志"""
        print(f"[{self.name}] {msg}", flush=True)

    # ──────────────────────────────────────────────
    # 工具格式转换：Anthropic input_schema → OpenAI function calling
    # ──────────────────────────────────────────────
    @staticmethod
    def _to_openai_tools(tools: list) -> list:
        """
        将 Anthropic 格式的工具定义转换为 OpenAI function calling 格式
        Anthropic: {"name":..., "description":..., "input_schema":{...}}
        OpenAI:    {"type":"function", "function":{"name":..., "description":..., "parameters":{...}}}
        """
        openai_tools = []
        for t in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                },
            })
        return openai_tools

    def _run_tool_loop(
        self,
        messages: list,
        tools: list,
        system: str,
        max_iterations: int = 10,
    ) -> tuple[list, str]:
        """
        执行完整的 tool-use agentic loop（OpenAI function calling 格式）

        返回：
          (updated_messages, final_text)
          - updated_messages: 包含所有工具调用历史的消息列表
          - final_text: 最后一次 stop 的文字回复
        """
        # OpenAI 格式：system 作为第一条消息
        full_messages = [{"role": "system", "content": system}] + messages
        openai_tools = self._to_openai_tools(tools)
        iteration = 0

        # 首次 API 调用
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            tools=openai_tools,
            messages=full_messages,
        )

        # ── Tool Use 循环 ──
        while response.choices[0].finish_reason == "tool_calls" and iteration < max_iterations:
            iteration += 1
            msg = response.choices[0].message
            tool_calls = msg.tool_calls

            # 将 assistant 消息（含 tool_calls）追加到历史
            full_messages.append({
                "role": "assistant",
                "content": msg.content,  # 通常为 None
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # 执行每个工具调用，将结果追加
            for tc in tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                self.log(f"调用工具: {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:80]}...)")

                try:
                    result = self._dispatch_tool(tool_name, tool_input)
                except Exception as e:
                    result = {"error": str(e)}

                # OpenAI 工具结果格式：role="tool"
                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

                # 同步更新原始 messages（供调用方读取工具结果）
                messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tc.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        }
                    ],
                })

            # 继续调用
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                tools=openai_tools,
                messages=full_messages,
            )

        # 提取最终文字回复
        final_text = response.choices[0].message.content or ""

        # 将最终回复追加到 messages（供 _extract_*_result 使用）
        messages.append({"role": "assistant", "content": final_text})

        return messages, final_text

    def _stream_response(
        self,
        messages: list,
        system: str,
        tools: list = None,
    ) -> str:
        """
        流式输出最终回复（OpenAI stream 格式）
        返回完整的文字内容。
        """
        full_messages = [{"role": "system", "content": system}] + messages

        kwargs = {
            "model": self.model,
            "max_tokens": 8192,
            "messages": full_messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = self._to_openai_tools(tools)

        full_text = ""
        stream = self.client.chat.completions.create(**kwargs)

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                try:
                    print(delta.content, end="", flush=True)
                except UnicodeEncodeError:
                    safe = delta.content.encode("utf-8", errors="replace").decode("utf-8")
                    print(safe, end="", flush=True)
                full_text += delta.content

        print()  # 换行
        return full_text

    def _dispatch_tool(self, tool_name: str, tool_input: dict) -> Any:
        """工具分发，由子类覆盖实现"""
        raise NotImplementedError(f"{self.name} 未实现 _dispatch_tool()")

    def run(self, *args, **kwargs) -> Any:
        """Agent 主入口，由子类实现"""
        raise NotImplementedError(f"{self.name} 未实现 run()")
