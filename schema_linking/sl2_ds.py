import re
import json

import requests
from openai import OpenAI

import config
from schema_linking.surfing_in_graph import SchemaGenerator, Neo4jExplorer
from typing import List, Dict
from langchain_core.prompts import ChatPromptTemplate
from validator import SLValidator


class SubgraphSelector:
    def __init__(self, dataset_name, db_name):
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.explorer = Neo4jExplorer()
        self.schema_generator = SchemaGenerator()
        self.validator = SLValidator(dataset_name, db_name)
        self.api_key = config.DEEPSEEK_API  # 替换为实际API Key
        self.base_url = "https://api.deepseek.com"  # 确认实际API地址
        self.client = OpenAI(
            api_key=config.DEEPSEEK_API,
            base_url="https://api.deepseek.com"  # 修正base_url
        )

        self.schema_selection_prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are an SQL schema expert. Follow these ABSOLUTE RULES:
            1. Respond ONLY with valid JSON.
            2. NEVER explain your reasoning outside the JSON structure.
            3. STRICTLY adhere to the step-by-step process.
            \nYour task is to perform a text2sql operation using a database schema represented as a graph. In this graph, table nodes are connected via foreign key relationships, and column nodes belong to table nodes.
            \nBased on the given question and the database schema, select the appropriate table nodes and the direct foreign key relationships connecting them. Note that the selected table nodes must be directly connected via foreign key relationships, not indirectly through intermediary nodes.
            \nYou will be provided with a subgraph containing nodes within a 0-hop to 1-hop distance. Your task is to select appropriate table nodes and direct foreign key relationships from this provided subgraph.
            \nThis round of selection is only one iteration, so do not choose table nodes that are more than 1-hop away."

"""),

            ("user", """### Task Requirements (MUST FOLLOW):
1. **Mandatory Starting Point**:
   - Begin with select_table(s) '{select_table}'
   - If '{select_table}' contains all necessary information to answer the `question`, set `is_solvable` to `true`.


2. **Expand to 1-hop neighboring tables (Only if necessary)**:
   - If '{select_table}' alone cannot provide enough information to answer the `question`, identify all neighboring tables that are **directly connected** to '{select_table}' via **foreign key relationships**.
   - From these neighboring tables, only select columns that are **relevant to the question**.
   - If a neighboring table is selected, **include the foreign key columns** that link the neighboring table to the '{select_table}'.

3. **Column Selection Criteria**:
   - Select ONLY columns directly needed to answer: "{question}"
   - If a column is needed for a foreign key relationship, include it
   - For foreign keys, prefer the minimal set needed for joining

4. **Output Validation**:
   - Your response WILL BE REJECTED if:
     * Missing '{select_table}' analysis
     * Violating 1-hop rule
     * Via hypothetical reference paths
     * Omitting required foreign keys

### Step-by-Step Process:
1. Analyze if '{select_table}' suffices for the `question`
2. If expanding:
   a) Identify 1-hop neighbors via schema relationships
   b) Select essential columns + foreign keys
   c) Provide concise reasoning per table

### Required JSON Format:
```json
{{
  "selected_columns": {{
    "<selected_table>": ["<column>", ...],  /* REQUIRED unless empty */
    ...
    "<neighbor_table>": ["<column>", "<foreign_key>", ...],
    ...
  }},
  "selected_reference_path": {{
  "<table1.column=table2.column>": "<why this reference_path is needed>"
    ...
  }},
  "reasoning": {{
    "<selected_table>": "<why columns were selected/discarded>",
    ...
    "<neighbor_table>": "<why this table is needed>"
    ...
  }},
  "to_solve_the_question": {{
    "is_solvable": <true/false>,
    "question": {question}
    "reason": "<Describe the information needed for the currently selected entity and if it corresponds to the problem one by one IN Detail>"
  }}
}}
```

### Question:
{question}

### Starting Table(s):
{select_table}

{result_from_last_round}
{hint}
### Database Schema:
{db_schema}

### Please provide the STRICTLY COMPLIANT JSON Response.
    """)
        ])

    # 修改后的 API 调用方法
    def _call_deepseek(self, messages):
        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                response_format={"type": "json_object"},  # 强制JSON模式
                temperature=0,
                max_tokens=2000  # 确保足够长度
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"API Error: {str(e)}")
            return None

    def extract_json(self, text: str) -> Dict:
        """Extract JSON content from the given text."""
        try:
            # Try parsing the text directly
            return json.loads(text)
        except Exception:
            # Use regex to extract JSON content if direct parsing fails
            matches = re.findall(r'\{.*\}', text, re.DOTALL)
            if matches:
                return json.loads(matches[0])
            raise ValueError("No valid JSON found in response")

    def select_relevant_tables(self, db_schema: str, question: str, select_table: List[str],
                               result_from_last_round='', hint='') -> Dict:
        # 生成提示词模板
        prompt_messages = self.schema_selection_prompt.format_messages(
            db_schema=db_schema,
            question=question,
            result_from_last_round=result_from_last_round,
            select_table=select_table,
            hint=hint
        )

        # 转换角色格式
        role_mapping = {
            "human": "user",
            "ai": "assistant",
            "system": "system"
        }
        messages = [{
            "role": role_mapping[msg.type],
            "content": msg.content
        } for msg in prompt_messages]

        # 调用API
        raw_response = self._call_deepseek(messages)

        if not raw_response:
            return {"selected_columns": {}, "reasoning": {}}

        try:
            return self.extract_json(raw_response)
        except Exception as e:
            print(f"JSON解析失败: {str(e)}")
            print(f"原始响应: {raw_response}")
            return {"selected_columns": {}, "reasoning": {}}

    def generate_schema_description(self, selected_table):
        # 从 Neo4jExplorer 实例中获取多跳子图
        explorer = Neo4jExplorer()
        sg = SchemaGenerator()
        n_hop_list = explorer.bfs_subgraph(selected_table)
        schema = []
        for i, hop in enumerate(n_hop_list):
            if i <= 1:
                schema.append(f"-----------------{i} hop-------------------")
            for t in hop:
                if i == 0:
                    schema.append(sg.generate_combined_description(t, "brief"))
                    # schema.append(sg.generate_combined_description(t, "full"))
                elif i == 1:
                    schema.append(sg.generate_combined_description(t, "brief", selected_table))
                    # schema.append(sg.generate_combined_description(t, "full", selected_table))
                # else:
                #     schema.append(sg.generate_combined_description(t, "minimal"))
        return "\n".join(schema)

    def generate_result_from_last_round(self, result: str):
        """
        生成上一轮的结果,作为提示的一部分
        :param result:
        :return:
        """
        return "### Result from last round:\n" + result

    def generate_hint(self, hint: str):
        """
        :param hint:
        :return:
        """
        return "### Recommendation table(s):\n" + hint


if __name__ == '__main__':
    sl2 = SubgraphSelector("bird", "cookbook")

    selected_table = ["Nutrition"]
    db_schema = sl2.generate_schema_description(selected_table)
    question = """What is the title of the recipe that is most likely to gain weight?
"""
    result_from_last_round = ''
    hint = ''
    final_prompt = sl2.schema_selection_prompt.format(
        db_schema=db_schema,
        question=question,
        result_from_last_round=result_from_last_round,
        select_table=selected_table,
        hint=hint
    )
    print("Final Prompt:\n", final_prompt)
    result = sl2.select_relevant_tables(db_schema, question, selected_table)
    print(json.dumps(result, indent=2))
    selected_table = result["selected_columns"]
    is_valid = sl2.validator.validate_entities(selected_table)
    print(is_valid)
    filter_valid_tables = sl2.validator.filter_valid_tables(selected_table)
    result["selected_columns"] = filter_valid_tables
    print(json.dumps(result, indent=2))
