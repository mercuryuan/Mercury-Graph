import json
import os
import re

import config
from schema_linking.surfing_in_graph import SchemaGenerator
from utils.call_llm import LLMClient
from utils.dataloader import DataLoader
from utils.graphloader import GraphLoader
from utils.sql_executor import SQLiteExecutor


class QuestionExample:
    def __init__(self, qid, evidence, raw_data):

        self.qid = qid
        self.evidence = "### Evidence:\n" + evidence if evidence else ""
        self.question = raw_data["question"]
        self.reasoning = raw_data["reasoning"]
        self.keywords = raw_data["keyword"]
        self.keyword_hints = raw_data["keyword_hints"]
        if raw_data["schema_linking_results"].get("selected_reference_path"):
            formatted_paths = "\n".join(
                [f"{key}: {value}" for key, value in
                 raw_data["schema_linking_results"]["selected_reference_path"].items()]
            )
            self.selected_reference_path = "### Selected Reference Paths:\n" + formatted_paths
        else:
            self.selected_reference_path = ''

        self.schema_linking_results = raw_data["schema_linking_results"]
        self.selected_columns = raw_data["schema_linking_results"]["selected_columns"]
        self.schema_reasoning = raw_data["schema_linking_results"]["to_solve_the_question"]["reason"]
        self.to_solve = raw_data["schema_linking_results"]["to_solve_the_question"]


class SQLGenerator:
    def __init__(self, dataset_name, db_name):
        self.dataset_name = dataset_name
        self.db_name = db_name

    def generate_sql(self, example: QuestionExample):
        """
        遍历所有数据库和问题，生成 SQL
        """
        qid = example.qid
        question = example.question
        keywords = example.keywords
        keyword_hints = example.keyword_hints
        selected_columns = example.selected_columns
        selected_reference_path = example.selected_reference_path
        solvable_reason = example.schema_reasoning
        print(f"Question ID: {qid}")
        print(f"Question: {question}")
        print(f"Keywords: {keywords}")
        print(f"Keyword hints: {keyword_hints}")
        print(f"Selected columns: {selected_columns}")
        print(f"Selected reference path: {selected_reference_path}")
        print(f"Solvable reason: {solvable_reason}")

    def generate_sql_prompt(self, example: QuestionExample):
        """
        Generate a structured English prompt for SQL generation based on the QuestionExample instance.
        """
        question = example.question
        keywords = example.keywords
        keyword_hints = example.keyword_hints
        evidence = example.evidence
        schema_linking_results = example.schema_linking_results
        selected_columns = example.selected_columns
        selected_reference_path = example.selected_reference_path
        schema_reasoning = example.schema_reasoning
        sg = SchemaGenerator()
        schema = sg.generate_combined_description_for_selected({"schema_linking_results": schema_linking_results})

        # System Prompt
        system_prompt = """
### Task:
You are an expert assistant specializing in SQL query generation based on schema linking results and natural language questions.

You will be given structured information extracted from a database schema linking process, including:
- The original question
- Detected keywords and keyword matching hints
- Selected relevant columns
- Selected reference paths between tables
- A partial schema (only for selected columns and related tables)
- Reasoning traces about how to solve the question
- Supporting evidence (formulas, explanations)

Your task is to **generate a correct, concise, and executable SQL query** based strictly on the provided information.

You must strictly follow these rules:
1. Only use the provided tables and selected columns. **Do not create or assume any new tables or columns.**
2. Only use the provided selected reference paths to perform JOIN operations between tables. **Do not invent joins or assume additional relationships.**
3. The schema provided is **partial and based on the selected entities**, so trust only the tables and columns described.
4. Understand the question's intent carefully, including filtering, aggregation, grouping, ordering, and calculations.
5. Use keyword hints to accurately construct WHERE conditions.
6. Use reasoning traces and evidence to support correct table usage, filtering, and calculations.
7. Write clean, lowercase SQL code.
8. Avoid unnecessary subqueries, extra aliases, or complex nesting unless essential.

**Output Format Requirements:**
- Only output the final SQL query.
- Wrap the SQL inside a fenced code block using triple backticks and specify the language as sql, like this:

```sql
-- your final SQL query here
```
Do not add any explanation, comments, or other content outside the fenced code block.

If information is missing, reason cautiously based on provided evidence and schema reasoning, but never hallucinate. 
        """

        # User Prompt
        user_prompt = (
            "### Database Name:\n"
            f"{self.db_name}\n\n"

            "### Question:\n"
            f"{question}\n\n"

            f"{evidence}\n\n"

            f"{keyword_hints}\n"

            "### Selected Relevant Columns:\n"
            f"{json.dumps(selected_columns, indent=2)}\n\n"

            f"{selected_reference_path}\n\n"

            "### Schema:\n"
            f"{schema}\n\n"

            "### Solvable Reason:\n"
            f"{schema_reasoning if schema_reasoning else 'None'}"
            "\n\n"
            "### Please Return SQL:\n"
            "```sql\n"
        )

        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()}
        ]

        # print(system_prompt)
        # print(user_prompt)

        return messages


class SQLResultSaver:
    def __init__(self, save_json_path: str, save_log_path: str):
        self.save_json_path = save_json_path
        self.save_log_path = save_log_path

        os.makedirs(os.path.dirname(save_json_path), exist_ok=True)

        # 如果文件不存在，初始化
        if not os.path.exists(save_json_path):
            with open(save_json_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2, ensure_ascii=False)
        if not os.path.exists(save_log_path):
            with open(save_log_path, "w", encoding="utf-8") as f:
                f.write("# SQL Generation Error Log\n\n")

    def save_success(self, record: dict):
        """保存一条成功记录到JSON"""
        with open(self.save_json_path, "r+", encoding="utf-8") as f:
            data = json.load(f)
            data.append(record)
            f.seek(0)
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.truncate()

    def save_error(self, qid: str, question: str, error_message: str):
        """保存一条错误记录到Markdown日志"""
        with open(self.save_log_path, "a", encoding="utf-8") as f:
            f.write(f"## QID: {qid}\n")
            f.write(f"**Question**: {question}\n\n")
            f.write(f"**Error**: {error_message}\n\n")
            f.write("---\n\n")


def extract_sql_from_response(response_text: str) -> str:
    """
    Extracts the SQL code from a LLM response wrapped inside a ```sql fenced code block.

    Args:
        response_text (str): The full text returned by the LLM.

    Returns:
        str: The extracted SQL query string.
    """
    match = re.search(r"```sql\s*(.*?)```", response_text, re.DOTALL | re.IGNORECASE)
    if match:
        sql_code = match.group(1).strip()
        return sql_code
    else:
        # If no fenced block found, fallback to full text
        return response_text.strip()


def save_sql_results(save_path: str, results: list):
    """
    保存SQL生成结果到json文件，只保存qid、question和sql。

    Args:
        save_path (str): 保存文件的路径，比如 'Results/bird_sql_results.json'
        results (list): 要保存的列表，每个元素是一个dict，例如：
                        {"qid": "123", "question": "...", "sql": "..."}
    """
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"已保存 {len(results)} 条SQL生成结果到 {save_path}")


def run():
    llm = LLMClient("deepseek", "deepseek-chat")
    dataset_name = "bird"

    save_json_path = os.path.join(config.SQL_GENERATION, f"{dataset_name}_sql_results.json")
    save_log_path = os.path.join(config.SQL_GENERATION, f"{dataset_name}_sql_errors.md")
    saver = SQLResultSaver(save_json_path, save_log_path)

    bird_loader = DataLoader("bird_dev")
    all_samples = bird_loader.filter_data()

    result_file = os.path.join(config.PROJECT_ROOT, "Results", f"{dataset_name}.json")
    if not os.path.exists(result_file):
        print(f"File {result_file} does not exist.")
        return

    with open(result_file, "r", encoding="utf-8") as f:
        schema_linking_results = json.load(f)

    graphloader = GraphLoader()
    for db_name, questions in schema_linking_results.items():
        graphloader.load_graph("bird", db_name)
        sql_generator = SQLGenerator(dataset_name, db_name)
        with SQLiteExecutor(dataset_name, db_name) as db:
            for qid, qdata in questions.items():
                sample = all_samples[int(qid)]
                evidence = sample.get("evidence", [])

                example = QuestionExample(qid, evidence, qdata)

                if example.qid != qid:
                    raise ValueError(f"Question ID mismatch: {example.qid} != {qid}")

                print(f"Question ID: {example.qid}")
                print(f"Question: {example.question}")

                try:
                    messages = sql_generator.generate_sql_prompt(example)
                    response = llm.chat(messages)
                    print(response)

                    sql = extract_sql_from_response(response)
                    print(sql)

                    if sql.strip():  # 成功提取到了SQL
                        saver.save_success({
                            "qid": qid,
                            "question": example.question,
                            "sql": sql
                        })
                    else:
                        raise ValueError("SQL extraction failed (empty result)")

                except Exception as e:
                    error_message = str(e)
                    print(f"Error for QID {qid}: {error_message}")
                    saver.save_error(qid, example.question, error_message)

                # break  # 可以控制每次跑多少个测试
            # break


if __name__ == '__main__':
    run()
