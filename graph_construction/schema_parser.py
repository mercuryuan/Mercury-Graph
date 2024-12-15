import json
import sqlite3
import random
from collections import defaultdict

from neo4j import GraphDatabase


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

    def _clear_neo4j_database(self):
        """
        清空Neo4j数据库中的所有节点和关系。
        """
        with self.neo4j_driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def parse_and_store_schema(self):
        """
        解析SQLite数据库的schema信息，并将其存储到Neo4j图数据库中。
        每次运行清空Neo4j数据库中的所有节点和关系。
        :return: 解析后的schema信息（以字典形式表示，包含表、列、外键关系等）
        """
        self._clear_neo4j_database()
        schema = defaultdict(lambda: defaultdict(list))
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            # 获取所有表名
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            for table in tables:
                table_name = table[0]
                # 在Neo4j中创建表节点
                self._create_table_node_in_neo4j(table_name)
                # 获取表的字段信息
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                for column in columns:
                    column_name = column[1]
                    data_type = column[2]
                    samples, additional_attributes = self._get_column_samples_and_attributes(table_name, column_name, data_type)
                    schema[table_name]['columns'].append((column_name, data_type, samples, additional_attributes))
                    # 在Neo4j中创建列节点，并与对应的表节点建立关系
                    self._create_column_node_and_relation_in_neo4j(table_name, column_name, data_type, samples, additional_attributes)
                # 获取表的外键关系（如果有）
                cursor.execute(f"PRAGMA foreign_key_list({table_name})")
                foreign_keys = cursor.fetchall()
                for foreign_key in foreign_keys:
                    from_column = foreign_key[3]
                    to_table = foreign_key[2]
                    to_column = foreign_key[4]
                    schema[table_name]['foreign_keys'].append((from_column, to_table, to_column))
                    # 在Neo4j中创建外键关系对应的节点和关系
                    self._create_foreign_key_relations_in_neo4j(table_name, from_column, to_table, to_column)
        return schema

    def _create_table_node_in_neo4j(self, table_name):
        """
        在Neo4j图数据库中创建表示表的节点。

        :param table_name: 表名
        """
        with self.neo4j_driver.session() as session:
            session.run("CREATE (:Table {name: $table_name})", table_name=table_name)

    def _create_column_node_and_relation_in_neo4j(self, table_name, column_name, data_type, samples, additional_attributes):
        """
        在Neo4j图数据库中创建表示列的节点，并建立其与对应表节点的关系。

        :param table_name: 表名
        :param column_name: 列名
        :param data_type: 列的数据类型
        :param samples: 列的随机抽样数据
        :param additional_attributes: 列的附加属性字典
        """
        additional_attributes_str = json.dumps(additional_attributes)
        with self.neo4j_driver.session() as session:
            session.run("""
                MATCH (t:Table {name: $table_name})
                CREATE (c:Column {name: $column_name, data_type: $data_type, samples: $samples, additional_attributes: $additional_attributes_str})
                CREATE (t)-[:HAS_COLUMN]->(c)
            """, table_name=table_name, column_name=column_name, data_type=data_type, samples=samples, additional_attributes_str=additional_attributes_str)


    def _create_foreign_key_relations_in_neo4j(self, from_table, from_column, to_table, to_column):
        """
        在Neo4j图数据库中创建外键关系对应的节点和关系。
        确保表节点之间只有一条表示外键的关系边，具有指定属性。

        :param from_table: 外键来源表
        :param from_column: 外键来源列
        :param to_table: 外键目标表
        :param to_column: 外键目标列
        """
        with self.neo4j_driver.session() as session:
            session.run("""
                MATCH (from_table:Table {name: $from_table})
                MATCH (to_table:Table {name: $to_table})
                MERGE (from_table)-[r:FOREIGN_KEY]->(to_table)
                ON CREATE SET r.from_table = $from_table, r.from_column = $from_column,
                              r.to_table = $to_table, r.to_column = $to_column
                ON MATCH SET r.from_table = $from_table, r.from_column = $from_column,
                             r.to_table = $to_table, r.to_column = $to_column
            """, from_table=from_table, from_column=from_column, to_table=to_table, to_column=to_column)

    def _get_column_samples_and_attributes(self, table_name, column_name, data_type):
        """
        随机抽样获取列的数据样本，并计算附加属性（范围或类别等多种属性）。

        :param table_name: 表名
        :param column_name: 列名
        :param data_type: 列的数据类型
        :return: 列的随机抽样数据和按照特定命名规则组织的附加属性字典
        """
        samples = []
        additional_attributes = {}
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(f"SELECT {column_name} FROM {table_name} LIMIT 100;")
                rows = cursor.fetchall()
                values = [row[0] for row in rows if row[0] is not None]

                # 获取随机样本
                samples = random.sample(values, min(len(values), 3))

                # 数值型列（INTEGER、REAL）相关属性
                if data_type.upper() in ["INTEGER", "REAL"]:
                    additional_attributes['numeric_range'] = [min(values), max(values)] if values else None
                    additional_attributes['numeric_distribution_type'] = self._get_distribution_type(values)
                    additional_attributes['numeric_mode'] = self._get_mode(values)
                    additional_attributes['numeric_null_ratio'] = len([v for v in values if v is None]) / len(rows) if rows else 0
                    additional_attributes['numeric_completeness'] = (len(values) / len(rows)) if rows else 0

                # 类别型列（可根据实际情况进一步明确具体类型，这里简单示例）相关属性
                elif data_type.upper() in ["TEXT", "VARCHAR"] and len(set(values)) <= 5:
                    additional_attributes['category_categories'] = list(set(values))
                    additional_attributes['category_average_char_length'] = self._get_average_char_length(values) if values else 0
                    additional_attributes['category_word_frequency'] = self._get_word_frequency(values) if values else {}
                    additional_attributes['category_null_ratio'] = len([v for v in values if v is None]) / len(rows) if rows else 0
                    additional_attributes['category_completeness'] = (len(values) / len(rows)) if rows else 0

                # 时间类型列（如DATE、DATETIME等，可根据实际数据库中的时间类型调整）相关属性
                elif data_type.upper() in ["DATE", "DATETIME"]:
                    additional_attributes['time_span'] = self._get_time_span(values) if values else None
                    additional_attributes['time_periodicity'] = self._get_periodicity(values) if values else ""
                    additional_attributes['time_null_ratio'] = len([v for v in values if v is None]) / len(rows) if rows else 0
                    additional_attributes['time_completeness'] = (len(values) / len(rows)) if rows else 0

            except Exception as e:
                print(f"Error processing column {column_name} in table {table_name}: {e}")

        return samples, additional_attributes

    def _get_distribution_type(self, values):
        """
        简单判断数值型数据的分布类型（示例，可进一步完善）。

        :param values: 数值列表
        :return: 分布类型字符串，如"normal"（正态分布）、"uniform"（均匀分布）等
        """
        # 这里只是简单示例，实际可通过更复杂的统计方法判断，比如绘制直方图观察形态等
        if len(values) < 10:
            return ""
        return "uniform" if max(values) - min(values) == len(values) - 1 else ""

    def _get_mode(self, values):
        """
        获取数值型或类别型数据的众数。

        :param values: 数据列表
        :return: 众数（可能存在多个众数情况，这里简单返回一个示例）
        """
        from collections import Counter
        if values:
            count_dict = Counter(values)
            max_count = max(count_dict.values())
            modes = [k for k, v in count_dict.items() if v == max_count]
            return modes[0] if modes else None
        return None

    def _get_average_char_length(self, values):
        """
        计算文本型数据的平均字符长度。

        :param values: 文本数据列表
        :return: 平均字符长度
        """
        if values:
            total_length = sum(len(v) for v in values)
            return total_length / len(values)
        return 0

    def _get_word_frequency(self, values):
        """
        统计文本型数据的词频。

        :param values: 文本数据列表
        :return: 词频字典，格式为{"word": frequency}
        """
        from collections import Counter
        all_words = " ".join(values).split()
        return dict(Counter(all_words))

    def _get_time_span(self, values):
        """
        计算时间类型数据的时间跨度。

        :param values: 时间数据列表
        :return: 时间跨度描述字符串（示例，可按需求调整格式）
        """
        if values:
            from datetime import datetime
            min_time = min(values)
            max_time = max(values)
            time_diff = max_time - min_time
            return f"{time_diff.days} days"
        return None

    def _get_periodicity(self, values):
        """
        简单判断时间类型数据的周期规律（示例，可进一步完善）。

        :param values: 时间数据列表
        """
        # 这里只是简单示例，实际可通过更复杂的时间序列分析方法判断，如自相关分析等
        if len(values) < 10:
            return ""
        return "monthly" if all((v.month - values[0].month) % 12 == 0 for v in values[1:]) else ""


if __name__ == "__main__":
    # Neo4j数据库连接配置
    neo4j_uri = "bolt://localhost:7687"  # 根据实际情况修改
    neo4j_user = "neo4j"  # 根据实际情况修改
    neo4j_password = "12345678"  # 根据实际情况修改
    database_file = "E:/Mercury-Graph/Mercury-Graph/data/books/books.sqlite"

    parser = SchemaParser(neo4j_uri, neo4j_user, neo4j_password, database_file)
    schema = parser.parse_and_store_schema()
    parser.close_connections()
    print(schema)