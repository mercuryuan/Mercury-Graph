import json
from neo4j import GraphDatabase
import sqlite3
import random
from collections import defaultdict


class SchemaParser:
    def __init__(self, neo4j_uri, neo4j_user, neo4j_password, database_file):
        """
        初始化SchemaParser类，建立与Neo4j和SQLite数据库的连接。

        :param neo4j_uri: Neo4j数据库的连接地址
        :param neo4j_user: Neo4j数据库的用户名
        :param neo4j_password: Neo4j数据库的密码
        :param database_file: SQLite数据库文件路径
        """
        self.neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.database_file = database_file

    def close_connections(self):
        """
        关闭与Neo4j数据库的连接。
        """
        self.neo4j_driver.close()

    def parse_and_store_schema(self):
        """
        解析SQLite数据库的schema信息，并将其存储到Neo4j图数据库中。
        在存储前先清除Neo4j中之前已有的相关图结构数据，确保每次执行都是全新构建。

        :return: 解析后的schema信息（以字典形式表示，包含表、列、外键关系等）
        """
        self._clear_neo4j_database()
        schema = defaultdict(lambda: defaultdict(list))

        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            tables = self._get_all_tables(cursor)

            for table_name in tables:
                self._process_table(table_name, cursor, schema)

        return schema

    def _clear_neo4j_database(self):
        """
        清空Neo4j数据库中的所有节点和关系。
        """
        with self.neo4j_driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def _get_all_tables(self, cursor):
        """
        获取SQLite数据库中的所有表名。

        :param cursor: SQLite数据库游标
        :return: 表名列表
        """
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        return [table[0] for table in cursor.fetchall()]

    def _process_table(self, table_name, cursor, schema):
        """
        解析单个表的schema信息并存储到Neo4j。

        :param table_name: 表名
        :param cursor: SQLite数据库游标
        :param schema: 用于存储schema信息的字典
        """
        self._create_table_node_in_neo4j(table_name)
        schema[table_name]['columns'] = self._process_columns(table_name, cursor)
        schema[table_name]['foreign_keys'] = self._process_foreign_keys(table_name, cursor)

    def _process_columns(self, table_name, cursor):
        """
        解析表的列信息并存储到Neo4j。

        :param table_name: 表名
        :param cursor: SQLite数据库游标
        :return: 列信息列表
        """
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()

        column_info = []
        for column in columns:
            column_name, data_type = column[1], column[2]
            samples, attributes = self._get_column_samples_and_attributes(table_name, column_name, data_type)
            column_info.append((column_name, data_type, samples, attributes))
            self._create_column_node_and_relation_in_neo4j(table_name, column_name, data_type, samples, attributes)

        return column_info

    def _process_foreign_keys(self, table_name, cursor):
        """
        解析表的外键信息并存储到Neo4j。

        :param table_name: 表名
        :param cursor: SQLite数据库游标
        :return: 外键信息列表
        """
        cursor.execute(f"PRAGMA foreign_key_list({table_name})")
        foreign_keys = cursor.fetchall()

        foreign_key_info = []
        for fk in foreign_keys:
            from_column, to_table, to_column = fk[3], fk[2], fk[4]
            foreign_key_info.append((from_column, to_table, to_column))
            self._create_foreign_key_relations_in_neo4j(table_name, from_column, to_table, to_column)

        return foreign_key_info

    def _create_table_node_in_neo4j(self, table_name):
        """
        在Neo4j图数据库中创建表示表的节点。

        :param table_name: 表名
        """
        with self.neo4j_driver.session() as session:
            session.run("CREATE (:Table {name: $table_name})", table_name=table_name)

    def _create_column_node_and_relation_in_neo4j(self, table_name, column_name, data_type, samples, attributes):
        """
        在Neo4j图数据库中创建表示列的节点，并建立其与对应表节点的关系。

        :param table_name: 表名
        :param column_name: 列名
        :param data_type: 列的数据类型
        :param samples: 列的随机抽样数据
        :param attributes: 列的附加属性（如range或categories）
        """
        serialized_attributes = json.dumps(attributes)

        with self.neo4j_driver.session() as session:
            session.run(
                """
                MATCH (t:Table {name: $table_name})
                CREATE (c:Column {name: $column_name, data_type: $data_type, samples: $samples, attributes: $attributes})
                CREATE (t)-[:HAS_COLUMN]->(c)
                """,
                table_name=table_name, column_name=column_name, data_type=data_type,
                samples=samples, attributes=serialized_attributes
            )

    def _create_foreign_key_relations_in_neo4j(self, from_table, from_column, to_table, to_column):
        """
        在Neo4j图数据库中创建外键关系对应的节点和关系。

        :param from_table: 外键来源表
        :param from_column: 外键来源列
        :param to_table: 外键目标表
        :param to_column: 外键目标列
        """
        with self.neo4j_driver.session() as session:
            session.run(
                """
                MATCH (from_table:Table {name: $from_table})
                MATCH (to_table:Table {name: $to_table})
                MERGE (from_table)-[r:FOREIGN_KEY]->(to_table)
                ON CREATE SET r.from_table = $from_table, r.from_column = $from_column,
                              r.to_table = $to_table, r.to_column = $to_column
                ON MATCH SET r.from_table = $from_table, r.from_column = $from_column,
                             r.to_table = $to_table, r.to_column = $to_column
                """,
                from_table=from_table, from_column=from_column, to_table=to_table, to_column=to_column
            )

    def _get_column_samples_and_attributes(self, table_name, column_name, data_type):
        """
        随机抽样获取列的数据样本，并计算附加属性（范围或类别）。

        :param table_name: 表名
        :param column_name: 列名
        :param data_type: 列的数据类型
        :return: 列的随机抽样数据和附加属性
        """
        samples = []
        additional_attributes = {}

        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"SELECT {column_name} FROM {table_name} LIMIT 100;")
                rows = cursor.fetchall()
                values = [row[0] for row in rows if row[0] is not None]

                samples = random.sample(values, min(len(values), 3))

                if data_type.upper() in ["INTEGER", "REAL"]:
                    additional_attributes['range'] = [min(values), max(values)] if values else None
                elif len(set(values)) <= 5:
                    additional_attributes['categories'] = list(set(values))

            except Exception as e:
                print(f"Error processing column {column_name} in table {table_name}: {e}")

        return samples, additional_attributes


if __name__ == "__main__":
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "12345678"
    database_file = "E:/Mercury-Graph/Mercury-Graph/data/books/books.sqlite"

    parser = SchemaParser(neo4j_uri, neo4j_user, neo4j_password, database_file)
    schema = parser.parse_and_store_schema()
    parser.close_connections()
    print(schema)
