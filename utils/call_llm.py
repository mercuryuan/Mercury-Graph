# llm_client.py

from openai import OpenAI
import config


class LLMClient:
    def __init__(self, provider="openai", model="gpt-4o", temperature=0):
        """
        初始化 LLMClient

        :param provider: "openai" 或 "deepseek"
        :param model: 使用的模型名称，如 "gpt-4o" 或 "deepseek-chat"
        :param temperature: LLM 的生成温度
        """
        self.provider = provider.lower()
        self.model = model
        self.temperature = temperature

        if self.provider == "openai":
            self.client = OpenAI()
        elif self.provider == "deepseek":
            self.client = OpenAI(
                api_key=config.DEEPSEEK_API,
                base_url="https://api.deepseek.com"
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    def chat(self, messages, stream=False):
        """
        与模型进行对话

        :param messages: 消息列表，格式为 [{"role": "user", "content": "Hello"}]
        :param stream: 是否流式输出
        :return: 返回模型生成的回复内容
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            stream=stream
        )

        if stream:
            return response  # 如果是流式，返回整个 response 对象用于逐步读取
        else:
            return response.choices[0].message.content


if __name__ == '__main__':
    # 初始化 OpenAI 客户端
    # client = LLMClient(provider="openai", model="gpt-4o", temperature=0)

    # 初始化 DeepSeek 客户端
    client = LLMClient(provider="deepseek", model="deepseek-chat", temperature=0)

    # 定义消息
    messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ]

    # 调用 LLM 接口
    response = client.chat(messages)
    print(response)
