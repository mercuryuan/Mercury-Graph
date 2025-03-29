import json
import os
import time

import config
from graph_construction.graph_to_mschema import get_table_schema
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from tqdm import tqdm


class TableSchemaDescriber:
    def __init__(self, db_path: str, model_name: str = "gpt-3.5-turbo"):
        """
        初始化表结构描述生成工具。
        :param db_path: 数据库路径。
        :param model_name: 使用的 LLM 模型名称。
        """
        self.db_path = db_path
        self.llm = ChatOpenAI(model=model_name)
        self.output_dir = config.GENERATED_DESCRIPTIONS
        os.makedirs(self.output_dir, exist_ok=True)
        self.log_file = os.path.join(config.SCHEMA_ENRICHER, "Database_Description_Process.log")
        self.conversation_history = []  # 存储全局对话历史
        self._is_system_added = False  # 标记是否已添加系统消息

    def get_schema(self, table_name: str = None):
        """
        获取数据库的表结构信息。
        :param table_name: 需要描述的表名（可选）。
        :return: (db_name, table_list, table_name, table_schema)
        """
        return get_table_schema(self.db_path, table_name, show_tables=False)

    def generate_prompt(self, table_name: str, table_schema: str) -> list:
        """
        生成描述表结构的多轮对话提示词。
        :param table_name: 需要描述的表名。
        :param table_schema: 该表的表结构信息。
        :return: 生成的对话消息列表。
        """
        user_message = f"""Table Name: {table_name}
        Table Schema:  
        {table_schema}

        Please output the result in the following JSON format:  

        ```json
        {{
            "{table_name}": [
                {{
                    "columns": {{
                        "column_name1": "description of column1",
                        "column_name2": "description of column2"
                    }},
                    "table_description": "The overall description of the table is to be generated"
                }}
            ]
        }}
        ```"""
        return [{"role": "user", "content": user_message}]

    def call_llm(self, messages: list) -> str:
        """
        调用 LLM 进行多轮对话，并维护上下文历史。
        调用LLM（混合模式：system + 所有assistant回复 + 最新user消息）
        :param messages: 本次对话的新消息列表。
        :return: LLM 生成的 JSON 格式描述。
        """
        # 首次调用时添加系统消息
        if not self._is_system_added:
            system_msg = {
                "role": "system",
                "content": """
### You are a professional database modeling expert. Based on the following table schema, generate detailed descriptions for each column.

1. **Exact Name Matching**
   - Use column/table names exactly as shown in schema (case-sensitive)
   - Never modify or translate names

2. **Strict JSON Format**
   - Output must precisely match specified JSON structure
   - No syntax deviations (commas, brackets, quotes)

3. **Pure Semantic Descriptions**
   - Describe ONLY the business meaning of column names
   - If there was a description, do not omit the original meaning, but maintain the style.
   - contain necessary details：
   * "Sex": "The gender of the student, represented by a single character."

4. **Table Description Synthesis**
   - State core business purpose
   - Derive from column descriptions

5. **Concise Professional Style**
   - ≤15 words per description
   - Active voice
   - Easily understandable by non-technical users

6. **Canonical Definition Format**
   - Start every description with "The"
   - Example: "The gender of the student..."
   - FORBIDDEN PHRASES:
     * "This column represents..."
     * "The table contains..."

7. **Style Unification**
   - Maintain consistent:
     * Sentence structures
     * Terminology
     * Phrasing patterns
   - Critical for semantic similarity matching

8. **Historical Consistency**
   - When available:
     * Reuse terminology from past descriptions
     * Match existing patterns
     * Maintain conceptual alignment
   - Example: If "ID" was "The unique identifier...", keep this format

### Validation Checklist:
✓ Name casing ✓ JSON structure ✓ No tech details
✓ "The"-style ✓ Length limits ✓ Historical alignment
    """
            }
            self.conversation_history.insert(0, system_msg)
            self._is_system_added = True

        # === 核心修改点 ===
        # 构造有效历史：system + 所有assistant消息 + 最新user消息
        effective_history = [
                                msg for msg in self.conversation_history
                                if msg["role"] in ["system", "assistant"]
                            ] + messages[-1:]  # 只取messages的最后一条（最新user消息）

        # 原始历史仍然完整记录（用于调试）
        self.conversation_history.extend(messages)

        # # 调试信息（显示实际使用的历史）
        # self.log(f"\n[DEBUG] 有效对话历史 (共 {len(effective_history)} 条):")
        # for i, msg in enumerate(effective_history, 1):
        #     role = msg["role"]
        #     content_preview = msg["content"][:80].replace("\n", " ")
        #     self.log(f"  {i}. {role}: {content_preview}...")

        # 调用LLM（传入精简后的历史）
        response = self.llm.invoke(effective_history).content.strip()

        # 记录完整历史（包含本次交互）
        self.conversation_history.append({"role": "assistant", "content": response})
        return self.clean_response(response)

    @staticmethod
    def clean_response(response: str) -> str:
        """
        清理 LLM 的输出，确保 JSON 格式正确。
        :param response: LLM 原始输出。
        :return: 清理后的 JSON 字符串。
        """
        response = response.strip()
        if response.startswith("```json"):
            response = response.replace("```json", "", 1).strip()
        if response.endswith("```"):
            response = response[:-3].strip()
        response = response.replace("\t", "").replace("\r", "")
        return response

    def save_description(self, db_name: str, table_name: str, description: str):
        """
        保存表描述到 JSON 文件。
        :param db_name: 数据库名称。
        :param table_name: 表名。
        :param description: 生成的表描述。
        """
        file_path = os.path.join(self.output_dir, f"{db_name}.json")
        new_data = json.loads(description)

        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            existing_data.update(new_data)
        else:
            existing_data = new_data

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)

    def describe_table(self, table_name: str):
        """生成表的列描述并保存（带上下文）"""
        try:
            db_name, _, _, table_schema = self.get_schema(table_name)
            messages = self.generate_prompt(table_name, table_schema)
            description = self.call_llm(messages)  # 调用时会自动维护历史
            self.save_description(db_name, table_name, description)
        except Exception as e:
            self.log(f"❌ 处理表 {table_name} 失败: {e}")
            self.conversation_history = []  # 出错时清空历史（可选）

    def describe_database(self):
        """
        遍历数据库中的所有表，并为每个表生成描述。
        使用进度条显示处理进度，并对失败的表进行最多 3 次重试。
        """

        db_name, table_list, _, _ = self.get_schema()
        start_time = time.time()  # 记录开始时间
        start_timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_time))

        self.log(f"[{start_timestamp}] 🚀 开始处理数据库: {db_name}, 包含 {len(table_list)} 张表")

        for table_name in tqdm(table_list, desc=f"Processing {db_name} Tables"):
            attempt = 0
            success = False

            while attempt < 3 and not success:
                try:
                    _, _, table_name, table_schema = self.get_schema(table_name)
                    messages = self.generate_prompt(table_name, table_schema)
                    description = self.call_llm(messages)
                    self.save_description(db_name, table_name, description)
                    self.log(f"✅ 成功处理表: {table_name}")
                    success = True
                except json.JSONDecodeError as e:
                    self.log(f"❌ 解析 JSON 失败: {table_name}, 尝试 {attempt + 1}/3, 错误: {e}")
                except Exception as e:
                    self.log(f"❌ 处理表失败: {table_name}, 尝试 {attempt + 1}/3, 错误: {e}")
                finally:
                    attempt += 1
                    time.sleep(1)  # 避免短时间内频繁调用

        end_time = time.time()  # 记录结束时间
        end_timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
        elapsed_time = end_time - start_time

        self.log(f"[{end_timestamp}] 🎉 数据库 {db_name} 处理完成！耗时: {elapsed_time:.2f} 秒")

    def log(self, message: str):
        """
        记录日志到文件，并打印。
        :param message: 需要记录的日志内容。
        """
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(message + "\n")
        print(message)

    import time
    from tqdm import tqdm
    import json


# 示例调用
if __name__ == "__main__":
    # db_path = "../../graphs_repo/spider/bike_1"
    # db_path = os.path.join(config.GRAPHS_REPO, "bird", "shakespeare")
    db_path = os.path.join(config.GRAPHS_REPO, "bird", "books")
    describer = TableSchemaDescriber(db_path)
    # 处理单表
    # describer.describe_table("Student")
    # 处理当前TableSchemaDescriber所在的数据库
    describer.describe_database()
