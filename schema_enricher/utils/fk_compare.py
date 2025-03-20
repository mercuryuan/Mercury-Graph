import json
import os.path
import config
from utils.case_corrector import align_case
from utils.dataloader import DataLoader
from utils.schema_extractor import SQLiteSchemaExtractor


def extract_foreign_keys(dataset_name, db_name):
    file_path = os.path.join(config.GRAPHS_REPO, dataset_name, db_name, "relationships.json")
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return set()
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON from {file_path}.")
        return set()

    foreign_keys = set()
    for item in data:
        if item["type"] == "FOREIGN_KEY":
            properties = item["properties"]
            tables = frozenset({
                (properties["from_table"], properties["from_column"]),
                (properties["to_table"], properties["to_column"])
            })
            foreign_keys.add(tables)

    return foreign_keys


def extract_fk_from_sql(dataset, database, sql):
    from utils.sql_parser import SqlParserTool
    tool = SqlParserTool(dataset, database)
    try:
        entities, relationships = tool.extract_entities_and_relationships(sql)
        tables = entities['tables']
        columns = entities['columns']
        join_conditions = relationships['joins']
    except Exception as e:
        print(f"Error: Failed to parse SQL. {e}")
        return set()

    extracted_fks = set()
    # 进行表名和列名的修正
    schema_extractor = SQLiteSchemaExtractor(dataset)
    schema = schema_extractor.extract_schema(database)
    _,_, join_conditions, _ = align_case(tables, columns, join_conditions, schema)
    for join in join_conditions:
        on_clause = join["on"]
        try:
            left, right = map(str.strip, on_clause.split("="))
            left_table, left_column = map(str.strip, left.split("."))
            right_table, right_column = map(str.strip, right.split("."))
            # 去除多余的引号
            left_column = left_column.strip("'")
            right_column = right_column.strip("'")
            tables = frozenset({(left_table, left_column), (right_table, right_column)})
            extracted_fks.add(tables)
        except ValueError:
            print(f"Error: Invalid ON clause format in {on_clause}.")

    return extracted_fks


def compare_foreign_keys(dataset_name, db_name, sql):
    """
    对比 SQL 中涉及的外键与数据库中真实存在的外键
    :param dataset_name: 数据集名称
    :param db_name: 数据库名称
    :param sql: SQL 查询语句
    :return: 包含三种信息的字典：
             - 'existing_fks': SQL 中存在且数据库中也存在的外键
             - 'missing_fks': SQL 中存在但数据库中不存在的外键
             - 'unused_fks': 数据库中存在但 SQL 中未使用的外键
    """
    real_fks = extract_foreign_keys(dataset_name, db_name)
    sql_fks = extract_fk_from_sql(dataset_name, db_name, sql)

    existing_fks = sql_fks.intersection(real_fks)
    missing_fks = sql_fks - real_fks
    unused_fks = real_fks - sql_fks
    return {
        'existing_fks': existing_fks,
        'missing_fks': missing_fks,
        'unused_fks': unused_fks
    }


# 示例调用
if __name__ == "__main__":
    dataset_name = "bird"
    db_name = "books"
    dataloader = DataLoader(dataset_name)
    data = dataloader.filter_data(db_name,fields=["sql"],show_count=True)
    for d in data:
        sql = d["sql"]
        result = compare_foreign_keys(dataset_name, db_name, sql)
        print("分析的sql为："+sql)
        # print("existing_fks:", result['existing_fks'])
        print("missing_fks:", result['missing_fks'])
