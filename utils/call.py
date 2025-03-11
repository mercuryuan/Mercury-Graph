import openai
import os


class ChatGPTAPIWrapper:
    def __init__(self):
        """
        初始化ChatGPT API包装类，优先从环境变量中获取API密钥，若不存在则后续需手动设置。
        """
        api_key = os.environ.get('OPENAI_API_KEY')
        if api_key:
            openai.api_key = api_key
        else:
            print("未从环境变量中获取到OpenAI API密钥，请确保设置了环境变量 'OPENAI_API_KEY' 或者手动设置API密钥。")

    def generate_response(self, messages, model="gpt-3.5-turbo", temperature=0.5):
        """
        调用ChatGPT API生成回复。

        :param messages: 对话消息列表，格式为[{"role": "user", "content": "你的提问内容"},...]，可以包含多轮对话历史
        :param model: 使用的模型名称，默认是gpt-3.5-turbo，也可以选择其他可用模型
        :param temperature: 控制生成回复的随机性，取值范围0到1，接近0表示更确定性的回复，接近1表示更具随机性的回复
        :return: ChatGPT生成的回复内容（字符串形式）
        """
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=temperature
            )
            return response['choices'][0]['message']['content']
        except openai.error.OpenAIError as e:
            print(f"调用ChatGPT API时出错: {e}")
            return None


if __name__ == "__main__":
    chat_gpt_api = ChatGPTAPIWrapper()
    if not openai.api_key:
        api_key = input("请输入你的OpenAI API密钥: ")
        openai.api_key = api_key
    messages = [{"role": "user", "content": "请帮我分析一下这个句子：The book on the table is interesting."}]
    response = chat_gpt_api.generate_response(messages)
    print(response)
