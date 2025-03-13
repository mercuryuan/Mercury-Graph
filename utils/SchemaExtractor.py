import os.path
import sqlite3
from abc import ABC, abstractmethod
from typing import Dict, List
import config


class SchemaExtractor(ABC):
    """
    抽象基类，定义数据库模式提取接口。
    """

    @abstractmethod
    def extract_schema(self, db_name: str) -> Dict[str, List[str]]:
        """
        提取数据库模式，返回一个嵌套字典。
        第一层是表名，第二层是列名列表。
        """
        pass


class SQLiteSchemaExtractor(SchemaExtractor):
    """
    SQLite 数据库模式提取器。
    """

    DATASET_PATHS = {
        "spider": config.SPIDER_DATABASES_PATH,
        "bird": config.BIRD_TRAIN_DATABASES_PATH,
        "spider2": config.SPIDER_DATABASES_PATH,
    }

    def __init__(self, dataset_name: str):
        """
        初始化 SQLiteSchemaExtractor。
        :param dataset_name: 数据集名称。
        """
        if dataset_name not in self.DATASET_PATHS:
            raise ValueError(f"未知数据集: {dataset_name}")
        self.dataset_path = self.DATASET_PATHS[dataset_name]
        self.dataset_name = dataset_name

    def extract_schema(self, db_name: str) -> Dict[str, List[str]]:
        """
        提取 SQLite 数据库模式。
        :param db_name: 需要提取的数据库名称。
        :return: 数据库模式字典。
        """
        db_path = os.path.join(self.dataset_path, db_name, f"{db_name}.sqlite")
        schema = {}
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # 对于 bird 数据集，排除 sqlite_sequence 表
        if self.dataset_name == "bird":
            tables = [table for table in tables if table != "sqlite_sequence"]
        for table in tables:
            cursor.execute(f"PRAGMA table_info({quote_identifier(table)})")
            columns = [row[1] for row in cursor.fetchall()]  # 仅获取列名
            schema[table] = columns

        conn.close()
        return schema


# 预留的 BigQuery 和 Snowflake 具体类
class BigQuerySchemaExtractor(SchemaExtractor):
    """BigQuery 的模式提取器，待实现。"""
    pass


class SnowflakeSchemaExtractor(SchemaExtractor):
    """Snowflake 的模式提取器，待实现。"""
    pass
def quote_identifier(identifier):
    """
    引用标识符（表名或列名），防止包含空格或特殊字符时出错。

    :param identifier: 表名或列名
    :return: 引用后的标识符
    """
    return f'"{identifier}"'  # 使用双引号引用

if __name__ == "__main__":
    extractor = SQLiteSchemaExtractor("bird")
    schema = extractor.extract_schema("airline")
    print(schema)