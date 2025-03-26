from typing import List, Dict
import json
import re

from utils.dataloader import DataLoader
from schema_linking.surfing_in_graph import SchemaGenerator
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 创建大语言模型实例
llm = ChatOpenAI(model="gpt-4", temperature=0)

schema_selection_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert in database schema reasoning. Respond ONLY with JSON format."""),
    ("user", """
### Task Description: {task_description}

### Database Schema:
{db_schema}

### Question:
{question}

Generate response in the following JSON format:
{{
  "selected_entity": ["table1", "table2"],
  "reason": ["reason1", "reason2"]
}}

Guidelines:
1. Select maximum 5 relevant tables
2. Only include tables with high confidence
3. Maintain parallel structure between selected_entity and reason arrays
4. Return ONLY the JSON object without additional commentary
    """)
])


def extract_json(text: str) -> Dict:
    """从文本中提取JSON内容"""
    try:
        # 尝试直接解析
        return json.loads(text)
    except:
        # 使用正则表达式匹配JSON内容
        matches = re.findall(r'\{.*\}', text, re.DOTALL)
        if matches:
            return json.loads(matches[0])
        raise ValueError("No valid JSON found in response")


def select_relevant_tables(task_description: str, db_schema: str, question: str) -> Dict:
    # 构建处理链
    chain = schema_selection_prompt | llm

    # 获取原始响应
    raw_response = chain.invoke({
        "task_description": task_description,
        "db_schema": db_schema,
        "question": question
    }).content

    # 提取并解析JSON
    try:
        return extract_json(raw_response)
    except Exception as e:
        print(f"JSON解析失败: {str(e)}")
        print(f"原始响应: {raw_response}")
        return {"selected_entity": [], "reason": []}


# 示例使用
if __name__ == "__main__":
    task_description = "Identify relevant database entities for SQL query generation."

    # 加载数据并初始化模式生成器
    dl = DataLoader("spider")
    data = dl.filter_data("geo", ["db_id", "sql", "question"])[0]
    sg = SchemaGenerator()

    # 生成数据库模式描述
    db_schema = "\n".join(
        sg.generate_combined_description(table) for table in sg.tables
    )

    # 执行表选择
    result = select_relevant_tables(
        task_description,
        db_schema,
        data["question"]
    )

    print("Selected tables:", result.get("selected_entity", []))
    print("Reasons:", result.get("reason", []))
