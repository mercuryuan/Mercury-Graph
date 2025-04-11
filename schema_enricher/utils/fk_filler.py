import json
import os
import re
from datetime import datetime
from typing import Dict

import config
from graph_construction.neo4j_data_migration import export_all
from graph_construction.schema_parser import generate_fk_hash
from schema_linking.validator import SLValidator
from schema_linking.surfing_in_graph import SchemaGenerator, Neo4jExplorer
from src.neo4j_connector import get_driver
from utils.graphloader import GraphLoader
from utils.sql_executor import SQLiteExecutor
from utils.call_llm import LLMClient


class FKFiller:
    def __init__(self, db_name, database_name, llm_provider="deepseek", llm_model="deepseek-reasoner"):
        self.dataset = db_name
        self.database_name = database_name
        gloader = GraphLoader()
        gloader.load_graph(self.dataset, self.database_name)
        self.driver = get_driver()
        self.validator = SLValidator(db_name, database_name)
        # 顺序非常关键，先加载图，再初始化 SchemaGenerator，否则sg使用的是缓存
        self.sg = SchemaGenerator()
        self.llm = LLMClient(llm_provider, llm_model)
        self.preprocess_json_path = os.path.join(config.SCHEMA_ENRICHER, "fk_in_preprocess.json")
        self.preprocess_md_path = os.path.join(config.SCHEMA_ENRICHER, "preprocess.md")

    def save_json(self, new_data: dict, filename: str):
        # 如果文件存在，先读取原数据
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    existing_data = {}
        else:
            existing_data = {}

        # 合并逻辑：逐层更新（适用于 {db: {schema: {path: xxx}}} 这种结构）
        for db, schemas in new_data.items():
            if db not in existing_data:
                existing_data[db] = {}
            for schema, content in schemas.items():
                if schema not in existing_data[db]:
                    existing_data[db][schema] = {}
                existing_data[db][schema].update(content)

        # 写回文件
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=4, ensure_ascii=False)

    def append_to_md(self, content: str):
        """
        向 markdown 日志文件中追加内容。
        - 若 with_timestamp=True，会在前面加上时间戳（只用于处理起始记录）
        - 标题类内容（以 # 开头）不会加时间戳
        """
        filename = self.preprocess_md_path
        content = content.strip()

        content = f"{content}"

        with open(filename, 'a', encoding='utf-8') as f:
            f.write(content + "\n")

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
        with SQLiteExecutor(self.dataset, self.database_name) as executor:
            result = executor.query(sql)
        return result

    def generate_match_rate_sql(self, join_condition: str) -> str:
        left_part, right_part = join_condition.split("=")
        left_table, left_column = left_part.strip().split(".")
        right_table, right_column = right_part.strip().split(".")

        # 对表名进行合法性处理
        left_table = self.quote_identifier(left_table)
        right_table = self.quote_identifier(right_table)
        # 对列名进行合法性处理
        left_column = self.quote_identifier(left_column)
        right_column = self.quote_identifier(right_column)

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

    def quote_identifier(self, name: str) -> str:
        if "-" in name or " " in name or not name.isidentifier():
            return f'"{name}"'
        return name

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

### Attention:
In some cases, the database may contain no data, rendering the SQL validation results inconclusive. 
In such situations, you should rely primarily on the question,the logical structure and semantics of the database schema to determine whether the proposed connection is justified.

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
        components_str = '\n'.join([str(component) for component in components])
        schema = self.generate_descriptions_for_connected_components()
        system_prompt = """
### Task Description:
Given a database with multiple tables (potentially containing disconnected components, i.e., subsets of tables not fully linked), 
analyze and select the most confident foreign key relationships between these components to propose missing connections, 
ensuring the entire database schema becomes fully connected.

### Input Data Format:
-Current known connected components (e.g., [[table_name1], [table_name2], [table_name3, table_name4]]).
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
"""
        user_prompt = f"""
### Current Known Connected Components:
{components_str}

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

### Attention:
In some cases, the database may contain no data, rendering the SQL validation results inconclusive. 
In such situations, you should rely primarily on the logical structure and semantics of the database schema to determine whether the proposed connection is justified.

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

    def generate_descriptions_for_connected_components(self, detail_level="brief"):
        """
        生成数据库中所有联通分量的描述
        :return:
        """
        # 获取联通分量
        connected_components = self.sg.explorer.obtain_all_connected_components_in_database()
        # print(connected_components)
        components = []
        count = 1
        for component in connected_components:
            description = []
            for table in component:
                description.append(self.sg.generate_combined_description(table, detail_level))
            components.append(f"## Component {count}: {component}\n" + "\n".join(description))
            count += 1
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
        deepseek = self.llm
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
        """
        # 加一条带时间戳的处理开始记录
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.append_to_md(f"# {self.dataset} - {self.database_name}")
        self.append_to_md(f"### `{timestamp}`")

        # 统计初始联通分量
        components = self.sg.explorer.obtain_all_connected_components_in_database()
        if len(components) == 1:
            self.append_to_md("### 初始状态：数据库连通，无需补全外键")
        else:
            self.append_to_md(f"### ⚠️初始状态：数据库中存在 {len(components)} 个不连通的组件，开始尝试补全外键")
            components_str = '  \n'.join(['`' + str(component) + '`' for component in components])
            self.append_to_md(f"#### 初始联通分量：  \n{components_str}")
        # 尝试推理缺失外键
        result = self.get_possible_missing_fk_for_disconnected_component()

        if not result:
            print("无需补全外键")
        else:
            print(json.dumps(result, indent=4))
            # 记录result
            self.append_to_md(f"#### LLM推荐补全外键路径：{json.dumps(result, indent=4)}")
            # 过滤掉已经存在的外键
            result = self.find_unexist_foreign_keys(result)
            if not result:
                self.append_to_md("#### Ⓜ️所有推荐的外键路径均已存在")
                # 统计初始联通分量
                components = self.sg.explorer.obtain_all_connected_components_in_database()
                components_str = '  \n'.join(['`' + str(component) + '`' for component in components])
                self.append_to_md(f"#### 最终联通分量：  \n{components_str}")
                return
            # 记录过滤掉已存在的外键path
            self.append_to_md(f"#### 过滤掉已存在的外键路径：{json.dumps(result, indent=4)}")

            for path in result:
                try:
                    left_table, left_column = path.split("=")[0].strip().split(".")
                    right_table, right_column = path.split("=")[1].strip().split(".")

                    # 生成并发送 prompt 给 LLM 判断外键合理性
                    messages = self.generate_prompt_for_potential_fk(path)
                    deepseek = self.llm
                    decision = deepseek.chat(messages)

                    decision = self.extract_json(decision)
                    reason = decision["reason"]

                    if decision["fk_is_needed"]:
                        # 在neo4j中创建外键path
                        self.create_foreign_key(left_table, left_column, right_table, right_column, "preprocess")
                        # 记录日志到md
                        self.append_to_md(f"#### ✅ 添加了 `{path}`")
                        self.append_to_md(f"#### Reason : `{reason}`")
                    else:
                        self.append_to_md(f"#### ❌ 未添加 `{path}`")
                        self.append_to_md(f"#### Reason : `{reason}`")

                    # 追加决策到 JSON 文件
                    fk = {self.dataset: {self.database_name: {
                        path: decision
                    }}}
                    print(json.dumps(fk, indent=4))
                    self.save_json(fk, self.preprocess_json_path)

                except Exception as e:
                    print(f"Error processing path {path}: {e}")
                    self.append_to_md(f"#### ❌ 处理 `{path}` 时出错: {e}")

            # 最终联通性状态
            final_components = self.sg.explorer.obtain_all_connected_components_in_database()
            if len(final_components) == 1:
                self.append_to_md("### ✅补全外键后：数据库已连通")
            else:
                components_str = '  \n'.join(['`' + str(component) + '`' for component in final_components])
                self.append_to_md(f"### 最终联通分量：  \n{components_str}")
                self.append_to_md(f"### 补全外键后：仍存在 {len(final_components)} 个不连通的组件❌")
            # 存储到Neo4j图结构中
            # 导出存储schema graph
            exp_path = os.path.join(config.GRAPHS_REPO, self.dataset, self.database_name)
            export_all(exp_path)
            print(f"✅ 新外键成功导出到{exp_path}！")


# 用法示例
if __name__ == "__main__":
    # datasets = "spider"
    datasets = "bird"
    database = "imdb"
    database = "soccer_1"
    # database = "student_1"
    # database = "legislator"
    database = "music_platform_2"
    # database = "works_cycles"

    # 创建对象，用于外键存在性验证、执行sql验证
    processor = FKFiller(datasets, database)
    # 初始化deepseek
    deepseek = processor.llm
    # # 初始化gpt-4o
    # deepseek = LLMClient()
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
    # result = processor.extract_json(deepseek.chat(messages))
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
    result = processor.execute_sql(processor.generate_match_rate_sql("runs.max_rowid=reviews.rowid"))
    print(result)
    print(processor.execute_validation_sql("runs.max_rowid=reviews.rowid"))

    # 查看当前数据库中所有联通分量的描述
    # print(processor.generate_descriptions_for_connected_components())
    # # 查看提交给LLM的提示
    # print(processor.generate_prompt_in_preprocess())

    # 为当前数据库预先筛选最有可能的缺失外键关系，使得数据库最终联通
    # processor.preprocess()
    # # 用chat再来一遍
    # processor = FKFiller(datasets, database, llm_model="deepseek-chat")
    # processor.preprocess()
