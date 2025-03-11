import json
import os
import time
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
        self.output_dir = "./generated_descriptions"
        os.makedirs(self.output_dir, exist_ok=True)
        self.log_file = "./Database_Description_Process.log"

    def get_schema(self, table_name: str = None):
        """
        获取数据库的表结构信息。
        :param table_name: 需要描述的表名（可选）。
        :return: (db_name, table_list, table_name, table_schema)
        """
        return get_table_schema(self.db_path, table_name, show_tables=True)

    def generate_prompt(self, table_name: str, table_schema: str) -> str:
        """
        生成描述表结构的提示词。
        :param table_name: 需要描述的表名。
        :param table_schema: 该表的表结构信息。
        :return: 生成的提示词字符串。
        """
        prompt_template = """
You are a professional database modeling expert. Based on the following table schema, generate detailed descriptions for each column.

Table Schema:  
{table_schema}

Generation Requirements:  
1. Use `{table_name}` as the table name.  
2. Column names must match the table schema exactly.  
3. The output must strictly follow the specified JSON format.  
4. Column descriptions should only explain the meaning of the column names and should not include data types, constraints, or other information explicitly stated in the schema.  
5. Derive an overall table description based on the generated column descriptions.  
6. Keep the descriptions concise, professional, and easy to understand.  

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
```
"""
        prompt = PromptTemplate(template=prompt_template, input_variables=["table_schema", "table_name"])
        return prompt.format(table_schema=table_schema, table_name=table_name)

    def call_llm(self, prompt: str) -> str:
        """
        调用 LLM 生成表描述。
        :param prompt: 生成的提示词。
        :return: LLM 生成的 JSON 格式描述。
        """
        response = self.llm.invoke(prompt).content.strip()
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
        """
        生成表的列描述并保存。
        :param table_name: 需要描述的表名。
        """
        try:
            db_name, table_list, table_name, table_schema = self.get_schema(table_name)
            print(table_list)
            prompt = self.generate_prompt(table_name, table_schema)
            # 预览生成的提示词
            print(prompt)
            description = self.call_llm(prompt)
            self.save_description(db_name, table_name, description)
        except json.JSONDecodeError as e:
            print(f"解析 JSON 失败: {e}")
        except Exception as e:
            print(f"发生错误: {e}")

    def log(self, message: str):
        """
        记录日志到文件，并打印。
        :param message: 需要记录的日志内容。
        """
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(message + "\n")
        print(message)

    def describe_database(self):
        """
        遍历数据库中的所有表，并为每个表生成描述。
        使用进度条显示处理进度，并对失败的表进行最多 3 次重试。
        """
        db_name, table_list, _, _ = self.get_schema()

        self.log(f"开始处理数据库: {db_name}, 包含 {len(table_list)} 张表")

        for table_name in tqdm(table_list, desc="Processing Tables"):
            attempt = 0
            success = False

            while attempt < 3 and not success:
                try:
                    _, _, table_name, table_schema = self.get_schema(table_name)
                    prompt = self.generate_prompt(table_name, table_schema)
                    description = self.call_llm(prompt)
                    self.save_description(db_name, table_name, description)
                    self.log(f"成功处理表: {table_name}")
                    success = True
                except json.JSONDecodeError as e:
                    self.log(f"解析 JSON 失败: {table_name}, 尝试 {attempt + 1}/3, 错误: {e}")
                except Exception as e:
                    self.log(f"处理表失败: {table_name}, 尝试 {attempt + 1}/3, 错误: {e}")
                finally:
                    attempt += 1
                    time.sleep(1)  # 避免短时间内频繁调用

        self.log("数据库描述任务完成")


# 示例调用
if __name__ == "__main__":
    db_path = "../graphs_repo/spider/activity_1"
    describer = TableSchemaDescriber(db_path)
    # describer.describe_database()
    describer.describe_table("Student")