import json
import re
from typing import Dict

from graph_construction.schema_parser import generate_fk_hash
from schema_linking.validator import SLValidator
from schema_linking.surfing_in_graph import SchemaGenerator
from src.neo4j_connector import get_driver
from utils.sql_executor import SQLiteExecutor
from utils.call_llm import LLMClient


class FKFiller:
    def __init__(self, db_name, schema_name):
        self.validator = SLValidator(db_name, schema_name)
        self.sg = SchemaGenerator()
        self.db_name = db_name
        self.schema_name = schema_name
        self.driver = get_driver()

    def find_unexist_foreign_keys(self, selected_reference_path):
        """分析并返回不存在的外键路径列表"""
        unexist_fks = []
        for p in selected_reference_path:
            if not self.validator.is_fk_exists(p):
                unexist_fks.append(p)
        return unexist_fks

    def generate_fk_descriptions(self, fk_path):
        """根据外键路径生成两表的描述"""
        left_table, left_column = fk_path.split("=")[0].strip().split(".")
        right_table, right_column = fk_path.split("=")[1].strip().split(".")
        left_desc = self.sg.generate_combined_description_for_fk(left_table, left_column)
        right_desc = self.sg.generate_combined_description_for_fk(right_table, right_column)

        return left_desc, right_desc

    def execute_sql(self, sql: str):
        with SQLiteExecutor(self.db_name, self.schema_name) as executor:
            result = executor.query(sql)
        return result

    def generate_match_rate_sql(self, join_condition: str) -> str:
        left_part, right_part = join_condition.split("=")
        left_table, left_column = left_part.strip().split(".")
        right_table, right_column = right_part.strip().split(".")

        sql = f"""
        SELECT
            COUNT(*) AS total_records,
            COUNT(r.{right_column}) AS matched_records,
            COUNT(*) - COUNT(r.{right_column}) AS unmatched_records,
            ROUND(COUNT(r.{right_column}) * 100.0 / COUNT(*), 2) AS match_percentage
        FROM {left_table} l
        LEFT JOIN {right_table} r ON l.{left_column} = r.{right_column};
        """.strip()

        return sql

    def execute_validation_sql(self, join_condition: str) -> str:
        # 生成 SQL 查询
        sql = self.generate_match_rate_sql(join_condition)

        # 执行 SQL 查询并获取结果
        result = self.execute_sql(sql)

        # 初始化默认值
        total_records = matched_records = unmatched_records = 0
        match_percentage = 0.0
        match_percentage_is_none = False

        if result and isinstance(result[0], (list, tuple)):
            total_records = result[0][0] or 0
            matched_records = result[0][1] or 0
            unmatched_records = result[0][2] or 0

            # 防止 match_percentage 为 None
            if result[0][3] is None:
                match_percentage_is_none = True
            else:
                match_percentage = result[0][3]

        # 构建文字描述
        description = f"""
### Join Match Rate Validation
According to the path, the matching rate of the left and right tables is as follows:
- total records: {total_records}
- matched records: {matched_records}
- unmatched records: {unmatched_records}
- match percentage: {"N/A" if match_percentage_is_none else f"{match_percentage}%"}
"""

        # 添加基于匹配率的建议
        if match_percentage_is_none:
            description += "The match percentage could not be calculated, likely due to no records in the left table or join failure."
        elif match_percentage > 90:
            description += "The match rate is high, indicating that the connection conditions are reasonable."
        elif match_percentage > 50:
            description += "The match rate is medium, there may be some mismatches, please verify further."
        else:
            description += "The match rate is low, it is recommended to check whether there are any abnormalities in the connection conditions or data."

        return description

    def generate_prompt_in_inference(self, question: str, fk_path: str):
        """
        推理中为数据库不存在的外键连接生成判断是否合理的prompt
        :return:
        """
        left_desc, right_desc = self.generate_fk_descriptions(fk_path)
        validation_result = self.execute_validation_sql(fk_path)
        # print(left_desc, right_desc)
        # print(validation_result)
        system_prompt = """
### Task Description:
You are a database domain expert with strong skills in evaluating the justification of foreign key connections based on natural language questions, database schema patterns, and join match rate validation results (SQL execution outcomes).
When solving the problem: "{question}", a proposed foreign key path is encountered. 
This path is not explicitly defined as a foreign key in the database schema. 
Your task is to assess whether this connection is logically justified."""
        user_prompt = f"""
### Question:
{question}

### Proposed Foreign Key Path:
{fk_path}

### Table Descriptions:
{left_desc}

{right_desc}
{validation_result}

### Instructions:
1. Analyze whether the proposed foreign key connection is logically justified based on the question, database schema, and validation results.
2. If the connection is justified, determine whether a formal foreign key constraint should be established.
3. Focus primarily on the database schema and SQL validation outcomes; use the question as contextual guidance.
4. Return your assessment in the following JSON format.

### Output JSON Format:
```json
{{
  "is_justified": <true | false>,
  "reason": "<Your reasoning for whether the connection is logically justified>",
  "fk_is_needed": <true | false>,
  "fk_reason": "<Your reasoning for whether a formal foreign key constraint should be added>"
}}
```
### Please Return the JSON Response ONLY:
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return messages

    def generate_prompt_in_preprocess(self):
        """
        推理前为数据库补全外键，生成补全外键的提示
        :return:
        """
        components = self.sg.explorer.obtain_all_connected_components_in_database()
        schema = self.generate_descriptions_for_connected_components()
        system_prompt = """
### Task Description:
Given a database with multiple tables (potentially containing disconnected components, i.e., subsets of tables not fully linked), 
analyze and select the most confident foreign key relationships between these components to propose missing connections, 
ensuring the entire database schema becomes fully connected.

### Input Data Format:
-Current known connected components (e.g., [['trip'], ['weather'], ['station', 'status']]).
-Structure of each component (column names, data types, sample values, PK/FK descriptions, etc.).

### Output JSON Format:
```json
{{
  "TableA.ColumnX=TableB.ColumnY": "<Reasoning for the proposed connection>",
  ...
}}
```

### Analysis Steps (Execute Step-by-Step):
1. Identify Potential Foreign Keys
*Check if fields across tables meet:
--Semantic alignment (e.g., station_id likely links to station.id).
--Data type compatibility (e.g., INTEGER ↔ INTEGER).
--Value overlap (do sample values suggest a viable relationship?).
*Prioritize PK-FK pairs or unique key associations.
2. Assess Confidence Level
*Rate each candidate connection (High/Medium/Low) based on:
--Naming consistency (e.g., user_id ↔ id).
--Data validation (e.g., do start_station_id samples exist in station.id?).
--Business logic (e.g., "weather data should align with trip dates/locations").
3. Resolve Connectivity
*Ensure all components merge into a single connected graph via FKs.
*If multiple solutions exist, pick the minimal additions with highest confidence.
4. Output Results
*Return proposed FK relationships in JSON with brief rationale.
}}
```

### Example Output:
{{
    "trip.start_station_id=station.id": "Semantic match (station_id → id), data type consistency (INTEGER), and station.id is a PK.",
    "weather.zip_code=trip.zip_code": "ZIP codes likely indicate shared geographic scope; data types match (INTEGER)."
}}
"""
        user_prompt = f"""
### Current Known Connected Components:
{components}

### Components Structure(DIVIDED BY HORIZONTAL LINES):
{schema}
### Please Return the JSON Response ONLY:
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        print(system_prompt)
        print(user_prompt)
        return messages

    def generate_prompt_for_potential_fk(self, path: str):
        """
        为数据库不存在的外键path生成判断是否合理的prompt
        :return:
        """
        left_desc, right_desc = self.generate_fk_descriptions(path)
        validation_result = self.execute_validation_sql(path)
        # print(left_desc, right_desc)
        # print(validation_result)
        system_prompt = """
### Task Description:
You are a database domain expert with strong skills in evaluating the justification of foreign key connections based on database schema patterns, and join match rate validation results (SQL execution outcomes).
The database tables currently form multiple disconnected components, resulting in a non-connected graph structure. 
To achieve full connectivity in the database, completing this path is highly recommended by the LLM. 
This path is not explicitly defined as a foreign key in the database schema. 
Your task is to assess whether this connection is logically justified."""
        user_prompt = f"""

### Proposed Foreign Key Path:
{path}

### Table Descriptions:
{left_desc}

{right_desc}
{validation_result}

### Instructions:
1. Analyze whether the proposed foreign key connection is logically justified based on database schema, and validation results.
2. If the connection is justified, determine whether a formal foreign key constraint should be established.
3. Focus primarily on the database schema and SQL validation outcomes; use the question as contextual guidance.
4. Return your assessment in the following JSON format.

### Output JSON Format:
```json
{{
  "fk_is_needed": <true | false>,
  "reason": "<Your reasoning for whether a formal foreign key constraint logically should be added>"
}}
```
### Please Return the JSON Response ONLY:
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        print(system_prompt)
        print(user_prompt)
        return messages

    def generate_descriptions_for_connected_components(self):
        """
        生成数据库中所有联通分量的描述
        :return:
        """
        # 获取联通分量
        connected_components = self.sg.explorer.obtain_all_connected_components_in_database()
        # 按个数排序
        connected_components = sorted(connected_components, key=len, reverse=False)
        print(connected_components)
        components = []
        for component in connected_components:
            description = []
            for table in component:
                description.append(self.sg.generate_combined_description(table, "brief"))
            components.append("\n".join(description))
        return "\n----------------------------independent component-----------------------------\n".join(components)

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

    def create_foreign_key(self, from_table, from_column, to_table, to_column, status):
        """
        在neo4j中创建外键约束
        :param left_table:
        :param left_column:
        :param right_table:
        :param right_column:
        :param status: 标识创建fk在预处理阶段还是推理过程中，参数是"preprocess"或者"inference"
        :return:
        """
        if status not in ["preprocess", "inference"]:
            raise ValueError("status must be either 'preprocess' or 'inference'")
        try:
            # 构造外键引用路径
            reference_path = f"{from_table}.{from_column}={to_table}.{to_column}"
            # 生成唯一无序外键ID
            fk_hash = generate_fk_hash(from_table, from_column, to_table, to_column)
            with self.driver.session() as session:
                session.run("""
                            MATCH (from_table:Table {name: $from_table})
                            MATCH (to_table:Table {name: $to_table})
                            // 创建外键关系
                            MERGE (from_table)-[r:FOREIGN_KEY {
                                from_table: $from_table,
                                from_column: $from_column,
                                to_table: $to_table,
                                to_column: $to_column,
                                reference_path: $reference_path,
                                fk_hash: $fk_hash,
                                status: $status
                            }]->(to_table)

                            // 更新目标表的 referenced_by 属性
                            SET to_table.referenced_by = coalesce(to_table.referenced_by, []) + [$reference_path]

                            // 更新来源表的 reference_to 属性
                            SET from_table.reference_to = coalesce(from_table.reference_to, []) + [$reference_path]

                            // 处理来源列的 referenced_to 属性
                            WITH from_table, to_table
                            MATCH (from_table)-[:HAS_COLUMN]->(from_column_node:Column {name: $from_column})
                            SET from_column_node.referenced_to = coalesce(from_column_node.referenced_to, []) + [$to_table + '.' + $to_column]

                            // 处理目标列的 referenced_by 属性
                            WITH to_table, from_table
                            MATCH (to_table)-[:HAS_COLUMN]->(to_column_node:Column {name: $to_column})
                            SET to_column_node.referenced_by = coalesce(to_column_node.referenced_by, []) + [$from_table + '.' + $from_column]
                        """, from_table=from_table, from_column=from_column, to_table=to_table, to_column=to_column,
                            reference_path=reference_path, fk_hash=fk_hash, status=status)
        except Exception as e:
            print(f"Error creating foreign key: {e}")

    def get_possible_missing_fk_for_disconnected_component(self) -> Dict:
        """
        为当前数据库中不连通的组件筛选可能的外键连接，
        并返回可能的外键连接及其理由
        如果数据库中没有不连通的组件，返回空字典
        :return:
        """
        # 采用ds-R1进行严密推理
        deepseek = LLMClient("deepseek", "deepseek-reasoner")
        # 判断本数据库是否有多个联通分量
        components = self.sg.explorer.obtain_all_connected_components_in_database()
        if len(components) == 1:
            return {}
        else:
            messages = self.generate_prompt_in_preprocess()
            result = deepseek.chat(messages)
            result = self.extract_json(result)
            return result

    def preprocess(self):
        """
        对数据库进行预处理，为数据库补全外键
        :return:
        """
        # 得到分析结果
        result = self.get_possible_missing_fk_for_disconnected_component()
        # 若为空字典，则说明数据库原先就联通，无需补全
        if result == {}:
            print("无需补全外键")
        else:
            print(json.dumps(result))
            for path in result:
                left_table, left_column = path.split("=")[0].strip().split(".")
                right_table, right_column = path.split("=")[1].strip().split(".")
                # 为数据库补全外键
                # 生成LLM是否判断外键的prompt
                messages = self.generate_prompt_for_potential_fk(path)
                deepseek = LLMClient("deepseek", "deepseek-reasoner")
                decision = deepseek.chat(messages)
                print(decision)
                decision = self.extract_json(decision)
                if decision["fk_is_needed"]:
                    self.create_foreign_key(left_table, left_column, right_table, right_column, "preprocess")
                    print(f"添加了{path}")
                else:
                    print(f"不添加{path}")


# 用法示例
if __name__ == "__main__":
    # 创建对象，用于外键存在性验证、执行sql验证
    processor = FKFiller("spider", "soccer_1")
    # 初始化deepseek
    llm = LLMClient("deepseek", "deepseek-chat")
    llm = LLMClient("deepseek", "deepseek-reasoner")
    # # 初始化gpt-4o
    # llm = LLMClient()
    # result = """{
    #     "selected_reference_path": {
    #         "country.Province = province.Name": "To link deserts to their respective countries"
    #     }
    # }"""
    # result = json.loads(result)
    # # 获取所有无效的外键路径
    # unexist_fks = processor.find_unexist_foreign_keys(result["selected_reference_path"])
    #
    # question = """How many businesses were founded after 1960 in a nation that wasn't independent?"""
    # messages = processor.generate_prompt_in_inference(question, "organization.Country = politics.Country")
    #
    # result = processor.extract_json(llm.chat(messages))
    # print(json.dumps(result, indent=2))
    # print(result["is_justified"])

    # 生成每个无效外键路径的描述
    # for fk in unexist_fks:
    #     left_desc, right_desc = processor.generate_fk_descriptions(fk)
    #     print(f"需要判断的外键: {fk}")
    #     # print(f"Left table description: {left_desc}")
    #     # print(f"Right table description: {right_desc}"
    #     # 生成SQL查询
    #     print(processor.execute_validation_sql(fk))
    # print("\n".join(processor.generate_fk_descriptions("country.Province = province.Name")))

    # 创建外键
    # processor.create_foreign_key("time_slot", "time_slot_id", "section", "time_slot_id", "preprocess")

    # 查看path的匹配程度

    # # 执行 SQL 查询并获取结果
    # result = processor.execute_sql(processor.generate_match_rate_sql("author.oid=organization.oid"))
    # print(result)
    # print(processor.execute_validation_sql("author.oid=organization.oid"))

    # 为当前数据库预先筛选最有可能的缺失外键关系，使得数据库最终联通
    processor.preprocess()
