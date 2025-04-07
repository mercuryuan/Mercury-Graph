from typing import List, Dict
import json
import re
from utils.dataloader import DataLoader
from schema_linking.surfing_in_graph import SchemaGenerator
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI


class TableSelector:
    def __init__(self):
        self.schema_generator = SchemaGenerator()
        # 创建大语言模型实例
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)

        self.schema_selection_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert in database schema reasoning. Respond ONLY with JSON format."""),
            ("user", """
### Task Description: 
Identify relevant database entities for SQL query generation.

### Database Schema:
{db_schema}

### Question:
{question}

Generate response in the following JSON format:
{{
  "selected_entity": ["table1", "table2"],
  "reasoning": {{
    "<selected_table>": "<why columns were selected/discarded>",
    ...
  }},
  "the steps of decomposed the question": ["step1", "step2",...]
}}

Guidelines:
1. Select maximum 5 relevant tables,order by confidence
2. Only include tables with high confidence
3. Maintain parallel structure between selected_entity and reason arrays
4. Return ONLY the JSON object without additional commentary
    """)
        ])

    def extract_json(self, text: str) -> Dict:
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

    def select_relevant_tables(self, db_schema: str, question: str) -> Dict:
        # 构建处理链
        chain = self.schema_selection_prompt | self.llm

        # 获取原始响应
        raw_response = chain.invoke({
            "db_schema": db_schema,
            "question": question
        }).content

        # 提取并解析JSON
        try:
            return self.extract_json(raw_response)
        except Exception as e:
            print(f"JSON解析失败: {str(e)}")
            print(f"原始响应: {raw_response}")
            return {"selected_entity": [], "reason": []}


# 示例使用
if __name__ == "__main__":
    ts = TableSelector()

    # 加载数据并初始化模式生成器
    dl = DataLoader("spider")
    data = dl.filter_data("geo", ["db_id", "sql", "question"])[0]
    sg = SchemaGenerator()

    # 生成数据库模式描述
    db_schema = "\n".join(
        sg.generate_combined_description(table) for table in sg.tables
    )
    question = """Of the 4 root beers that Frank-Paul Santangelo purchased on 2014/7/7, how many of them were in cans?
"""

    final_prompt = ts.schema_selection_prompt.format(
        db_schema=db_schema,
        question=question
    )
    print("Final Prompt:\n", final_prompt)
    # 执行表选择
    result = ts.select_relevant_tables(
        db_schema,
        question
    )

    print("Selected tables:", result.get("selected_entity", []))
    print("Reasons:", result.get("reason", []))
    print("the steps of decomposed the question:", result.get("the steps of decomposed the question", []))
