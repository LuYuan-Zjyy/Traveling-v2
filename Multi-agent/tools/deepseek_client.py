"""
DeepSeek LLM 客户端
封装 OpenAI-compatible API, 支持 function calling (tool use)
使用流式(streaming)请求解决长响应连接中断问题
"""

import json
import time
from typing import Optional
from openai import OpenAI
from openai import APIConnectionError, APIError


class DeepSeekClient:
    """DeepSeek LLM 客户端, 支持普通对话和 Function Calling"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com",
                 model: str = "deepseek-chat", timeout: float = 300.0, max_retries: int = 5):
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )

    # ----------------------------------------------------------
    # 内部: 统一重试逻辑
    # ----------------------------------------------------------
    def _retry_call(self, fn, description: str = "API"):
        """通用重试包装器"""
        retry_delay = 2
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                return fn()
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                is_retryable = (
                    isinstance(e, (APIConnectionError, ConnectionError, OSError)) or
                    'connection' in error_str or
                    'peer closed' in error_str or
                    'incomplete' in error_str or
                    'timeout' in error_str or
                    'eof' in error_str
                )
                status_code = getattr(e, 'status_code', None)
                if status_code in (429, 500, 502, 503, 504):
                    is_retryable = True

                if is_retryable and attempt < self.max_retries - 1:
                    wait = retry_delay * (2 ** attempt)
                    print(f"   [!] {description} 连接错误, {wait}s 后重试 ({attempt + 1}/{self.max_retries})...")
                    time.sleep(wait)
                    continue
                raise last_exception

    # ----------------------------------------------------------
    # 普通对话 (使用 streaming 避免长响应断连)
    # ----------------------------------------------------------
    def chat(self, messages: list, temperature: float = 0.3,
             max_tokens: int = 4096) -> str:
        """普通对话 —— 流式接收, 彻底解决长回复断连"""
        def _do_stream():
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            chunks = []
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    chunks.append(delta.content)
            return "".join(chunks)

        return self._retry_call(_do_stream, description="chat")

    # ----------------------------------------------------------
    # 带工具调用的对话 (Function Calling, 不使用 streaming)
    # ----------------------------------------------------------
    def chat_with_tools(self, messages: list, tools: list,
                        temperature: float = 0.3, max_tokens: int = 4096) -> dict:
        """带工具调用的对话 (Function Calling)"""
        def _do_call():
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            message = response.choices[0].message

            result = {
                "content": message.content,
                "tool_calls": [],
                "raw_message": message,
            }

            if message.tool_calls:
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    result["tool_calls"].append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args,
                    })
            return result

        return self._retry_call(_do_call, description="chat_with_tools")

    # ----------------------------------------------------------
    # 工具: 从 LLM 回复中提取 JSON
    # ----------------------------------------------------------
    def extract_json(self, text: str) -> Optional[dict]:
        """从 LLM 回复中提取 JSON 对象"""
        import re
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None
