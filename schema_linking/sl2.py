import re
import json
from schema_linking.surfing_in_graph import SchemaGenerator, Neo4jExplorer
from typing import List, Dict
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from validator import SLValidator


class SubgraphSelector:
    def __init__(self):
        self.explorer = Neo4jExplorer()
        self.schema_generator = SchemaGenerator()
        self.validator = SLValidator()
        # 创建大语言模型实例
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0)

        self.schema_selection_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an SQL schema expert. Follow these ABSOLUTE RULES:
1. Respond ONLY with valid JSON
2. NEVER explain your reasoning outside the JSON structure
3. STRICTLY adhere to the step-by-step process"""),

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

    def select_relevant_tables(self, db_schema: str, question: str, select_table: List[str],
                               result_from_last_round='') -> Dict:
        # Build the processing chain
        chain = self.schema_selection_prompt | self.llm

        # 输出提示
        final_prompt = self.schema_selection_prompt.format(
            db_schema=db_schema,
            question=question,
            result_from_last_round=result_from_last_round,
            select_table=select_table
        )
        print("Final Prompt:\n", final_prompt)

        # Get raw response from the model
        raw_response = chain.invoke({
            "db_schema": db_schema,
            "question": question,
            "select_table": select_table,
            "result_from_last_round": result_from_last_round
        }).content

        # Extract and parse JSON from the response
        try:
            return self.extract_json(raw_response)
        except Exception as e:
            print(f"JSON parsing failed: {str(e)}")
            print(f"Raw response: {raw_response}")
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
                elif i == 1:
                    schema.append(sg.generate_combined_description(t, "brief", selected_table))
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


if __name__ == '__main__':
    sl2 = SubgraphSelector()

    selected_table = ["course"]
    db_schema = sl2.generate_schema_description(selected_table)
    question = """Find the name of students who have taken the prerequisite course of the course with title International Finance.
"""
    sql = """SELECT DISTINCT T1.player_name FROM Player AS T1 JOIN Player_Attributes AS T2 ON T1.player_api_id = T2.player_api_id WHERE T2.overall_rating  >  ( SELECT avg(overall_rating) FROM Player_Attributes )"""
    result_from_last_round = ''
    final_prompt = sl2.schema_selection_prompt.format(
        db_schema=db_schema,
        question=question,
        result_from_last_round=result_from_last_round,
        select_table=selected_table
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
    # "Identify course ID for 'International Finance' from the course table.":<true/false>,
    # 'Determine the prerequisite course ID for this course from the prereq table.':<true/false>,
    # 'Use the takes table to find students who have taken the prerequisite course.':<true/false,
    # 'Retrieve the names of these students from the student table.':<true/false>
