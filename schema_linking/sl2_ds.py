import re
import json

import requests
from openai import OpenAI

import config
from schema_linking.surfing_in_graph import SchemaGenerator, Neo4jExplorer
from typing import List, Dict
from langchain_core.prompts import ChatPromptTemplate

from utils.call_llm import LLMClient
from utils.graphloader import GraphLoader
from schema_linking.validator import SLValidator


class SubgraphSelector:
    def __init__(self, dataset_name, db_name, question_data=None):
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.question_data = question_data
        self.evidence = "### Evidence:\n" + self.question_data.get("evidence", "") if \
            self.question_data and self.question_data.get("evidence") else ""
        self.explorer = Neo4jExplorer()
        self.schema_generator = SchemaGenerator()
        self.validator = SLValidator(dataset_name, db_name)
        # 使用openai
        self.client = LLMClient("openai", "gpt-4o")
        # # 使用deepseek
        # self.client = LLMClient("deepseek", "deepseek-chat")
        # 使用deepseek-reasoner
        # self.client = LLMClient(provider="deepseek", model="deepseek-reasoner")
        self.sl2_per_iterations = []

        self.schema_selection_prompt = ChatPromptTemplate.from_messages([
            ("system", """
You are an SQL schema expert. Follow these ABSOLUTE RULES:
1. Respond ONLY with valid JSON.
2. NEVER include any explanation outside the JSON structure.
3. STRICTLY adhere to the step-by-step process.

Your task is to select appropriate table nodes and the direct foreign key relationships from the provided subgraph.

The graph consists of:
- Table nodes connected via foreign key relationships.
- Column nodes that belong to specific table nodes.

As an expert in Text-to-SQL over graph-structured database schemas, your goal is to select:
- The relevant table nodes.
- The direct foreign key relationships that connect them.

IMPORTANT: Only select table nodes that are directly connected by foreign key relationships within the given subgraph. Do NOT select table nodes that are more than 1-hop away or indirectly connected through intermediate nodes.

Note: This is only one iteration in a multi-step process. Focus solely on nodes and edges within a 0-hop to 1-hop distance for this step.

⚠️ The current schema view is centered around the source table(s) connected via outgoing foreign keys, and includes only directly linked 1-hop tables. It does not represent the full schema.


"""),

            ("user", """### Task Requirements (MUST FOLLOW):
1. **Mandatory Starting Point**:
   - Begin with select_table(s) '{select_table}'
   - If '{select_table}' contains all necessary information to answer the `question`, set `is_solvable` to `true`.


2. **Expand to 1-hop neighboring tables (Only if necessary)**:
   - If '{select_table}' alone cannot provide enough information to answer the `question`, identify all neighboring tables that are **directly connected** to '{select_table}' via **foreign key relationships**.
   - From these neighboring tables, only select columns that are **relevant to the question**.
   - If a neighboring table is selected, **include the foreign key columns** that link the neighboring table to the '{select_table}'.

3. **Column Selection Rules**:
   - Select ONLY columns that are directly required to answer: "{question}".
   - Consider the keyword match results provided in "KEYWORD MATCH RESULTS" as potential strong signals of relevance.
   - Always include foreign key columns needed to form the reference path.
   - Prefer the **minimal** set of foreign keys necessary for the join.

4. **Validation Rules**:
   ❌ The output will be REJECTED if:
   - Analysis of '{select_table}' is missing
   - Any selected table violates the 1-hop constraint
   - Reference paths are hypothetical or indirect
   - Required foreign keys are omitted

### Step-by-Step Process:
1. Determine if '{select_table}' alone can answer the question.
2. If not:
   a) Identify valid 1-hop neighbors via schema foreign key relationships
   b) Select minimal and relevant columns (including required foreign keys)  
   c) Provide concise justification for each table selected

### Required JSON Format:
```json
{{
  "selected_columns": {{
    "<selected_table>": ["<column>", ...],
    ...
    "<neighbor_table>": ["<column>", "<foreign_key>", ...],
    ...
  }},
  "selected_reference_path": {{
  "<table1.column=table2.column>": "<why this reference_path is selected>"
    ...
  }},
  "reasoning": {{
    "<selected_table>": "<why table and columns were selected>",
    ...
    "<neighbor_table>": "<why this table is selected>"
    ...
  }},
  "to_solve_the_question": {{
    "is_solvable": <true/false>,
    "question": {question}
    "reason": "<Describe the information needed for the currently selected entity and if it corresponds to the problem one by one IN Detail>"
  }}
}}
```
### Database Name:
{db_name}

### Question:
{question}

{keyword_hints}
{evidence}

### Starting Table(s):
{select_table}

{result_from_last_round}
{hint}
### Database Schema:
{db_schema}

### Please provide the STRICTLY COMPLIANT JSON Response.
    """)
        ])

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

    def select_relevant_tables(self, db_schema: str, question: str, select_table: List[str], keyword_hints,
                               result_from_last_round='', hint='') -> Dict:
        # 生成提示词模板
        prompt_messages = self.schema_selection_prompt.format_messages(
            db_name=self.db_name,
            db_schema=db_schema,
            question=question,
            result_from_last_round=result_from_last_round,
            select_table=select_table,
            keyword_hints=keyword_hints,
            hint=hint,
            evidence=self.evidence
        )
        # # 打印人类提示
        # for msg in prompt_messages:
        #     if msg.type == "human":
        #         print(f"Human: {msg.content}")

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
        raw_response = self.client.chat(messages)

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
    gloder = GraphLoader()
    gloder.load_graph("bird", "cookbook")
    selected_table = ["Nutrition"]
    db_schema = sl2.generate_schema_description(selected_table)
    question = """What is the title of the recipe that is most likely to gain weight?
"""
    result_from_last_round = ''
    hint = ''
    final_prompt = sl2.schema_selection_prompt.format(
        db_name=sl2.db_name,
        db_schema=db_schema,
        question=question,
        result_from_last_round=result_from_last_round,
        select_table=selected_table,
        keyword_hints='假装有',
        hint=hint,
        evidence=sl2.evidence
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
