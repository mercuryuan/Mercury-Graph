import json
import operator
import sqlite3
import random
from collections import defaultdict, Counter
from datetime import datetime
import numpy as np
from scipy.stats import norm, kstest
from neo4j import GraphDatabase
import pandas as pd  # 新增，用于处理DataFrame

DATE_FORMATS = [
    '%Y-%m-%d',
    '%Y/%m/%d',
    '%Y.%m.%d',
    '%m/%d/%Y',
    '%m-%d-%Y',
    '%d/%m/%Y',
    '%d-%m-%Y',
    '%Y-%m-%d %H:%M:%S',
    '%Y/%m/%d %H:%M:%S',
    '%Y.%m.%d %H:%M:%S',
    '%m/%d/%Y %H:%M:%S',
    '%m-%d-%Y %H:%M:%S',
    '%d/%m/%Y %H:%M:%S',
    '%d-%m-%Y %H:%M:%S'
]


def convert_date_string(date_str):
    """
    尝试将输入的日期字符串按照多种常见格式转换为datetime对象。

    :param date_str: 日期字符串
    :return: 转换后的datetime对象，如果转换失败则返回None
    """
    for format_str in DATE_FORMATS:
        try:
            return datetime.strptime(date_str, format_str)
        except ValueError:
            continue
    print(f"无法将日期字符串 {date_str} 转换为有效的日期时间格式，请检查数据格式！")
    return None


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
        :return: 解析后的schema信息（以字典形式表示，包含表、列、外键关系等），同时返回包含属性信息的DataFrame
        """
        self._clear_neo4j_database()
        schema = defaultdict(lambda: defaultdict(list))
        all_columns_info = []  # 用于存储所有列的信息，以便后续构建DataFrame

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
                    samples = self._get_column_samples(table_name, column_name)
                    values = [row[0] for row in cursor.fetchall() if row[0] is not None]  # 获取完整数据值列表

                    # 判断列类型并获取相应附加属性
                    if data_type.upper() in ["INTEGER", "REAL"]:
                        additional_attributes = self._get_numeric_attributes(table_name, column_name, values)
                    elif data_type.upper() in ["TEXT", "VARCHAR"]:
                        additional_attributes = self._get_text_attributes(table_name, column_name, values)
                    elif data_type.upper() in ["DATE", "DATETIME"]:
                        additional_attributes = self._get_time_attributes(table_name, column_name, values)
                    else:
                        additional_attributes = {}

                    # 判断是否为主键或外键，添加key_type属性（仅针对主键或外键列）
                    key_type = []
                    if self._is_primary_key(table_name, column_name):
                        key_type.append("primary_key")
                    if self._is_foreign_key(table_name, column_name):
                        key_type.append("foreign_key")
                    if key_type:
                        additional_attributes['key_type'] = key_type

                    # 添加数据条数属性（所有类型列）
                    additional_attributes['data_count'] = len(values) if values else 0

                    schema[table_name]['columns'].append((column_name, data_type, samples, additional_attributes))
                    all_columns_info.append({
                        "table_name": table_name,
                        "column_name": column_name,
                        "data_type": data_type,
                        "samples": samples,
                        "attributes": additional_attributes
                    })

                    # 在Neo4j中创建列节点，并与对应的表节点建立关系
                    self._create_column_node_and_relation_in_neo4j(table_name, column_name, data_type, samples,
                                                                   additional_attributes)
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

        # 将所有列信息转换为DataFrame
        columns_df = pd.DataFrame(all_columns_info)
        return schema, columns_df

    import sqlite3

    def _create_table_node_in_neo4j(self, table_name):
        """
        在Neo4j图数据库中创建表示表的节点，并根据实际情况为表节点添加主键和外键属性。
        属性名为primary_key和foreign_key，主键外键如果只有一个就单独为主外键名称，若有多个才返回键列表，若没有则不添加属性。

        :param table_name: 表名
        """
        primary_key_columns = self._get_primary_key_columns(table_name)
        foreign_key_columns = self._get_foreign_key_columns(table_name)

        properties = {"name": table_name}
        if primary_key_columns:
            properties["primary_key"] = primary_key_columns if len(primary_key_columns) > 1 else primary_key_columns[0]
        if foreign_key_columns:
            properties["foreign_key"] = foreign_key_columns if len(foreign_key_columns) > 1 else foreign_key_columns[0]

        property_str = ', '.join(f"{key}: ${key}" for key in properties)
        query = f"CREATE (:Table {{ {property_str} }})"

        with self.neo4j_driver.session() as session:
            session.run(query, **properties)

    def _get_primary_key_columns(self, table_name):
        """
        获取指定表的主键列信息（以SQLite为例）。

        :param table_name: 表名
        :return: 主键列名列表，如果是单个主键则返回只包含该列名的列表，无主键返回空列表
        """
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns_info = cursor.fetchall()
            primary_key_columns = []
            for column_info in columns_info:
                if column_info[5] != 0:  # 假设第6个元素（索引为5）表示是否为主键，1为主键，0为非主键，不同数据库该位置可能不同
                    primary_key_columns.append(column_info[1])  # 第2个元素（索引为1）是列名
            return primary_key_columns

    def _get_foreign_key_columns(self, table_name):
        """
        获取指定表的外键列信息（以SQLite为例）。

        :param table_name: 表名
        :return: 外键列名列表，如果是单个外键则返回只包含该列名的列表，无外键返回空列表
        """
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            foreign_keys = cursor.fetchall()
            foreign_key_columns = [fk[3] for fk in foreign_keys]  # 第4个元素（索引为3）是本地列名，对应外键列
            return foreign_key_columns

    import sqlite3

    def _create_column_node_and_relation_in_neo4j(self, table_name, column_name, data_type, samples,
                                                  additional_attributes):
        """
        在Neo4j图数据库中创建表示列的节点，并建立其与对应表节点的关系。
        将additional_attributes扁平化处理，每个属性单独作为列节点的属性存储，
        同时为关系添加属性，以区别列节点是普通列、主键列、外键列、还是同时作为主键和外键。

        :param table_name: 表名
        :param column_name: 列名
        :param data_type: 列的数据类型
        :param samples: 列的随机抽样数据
        :param additional_attributes: 列的附加属性字典
        """
        # 查询列是否为主键
        is_primary_key = self._is_primary_key(table_name, column_name)
        # 查询列是否为外键
        is_foreign_key = self._is_foreign_key(table_name, column_name)

        with self.neo4j_driver.session() as session:
            props = {
                "name": column_name,
                "data_type": data_type,
                "samples": samples
            }
            # 扁平化处理additional_attributes字典，将每个键值对添加到props字典中
            for key, value in additional_attributes.items():
                props[key] = value

            property_str = ', '.join([f"{key}: ${key}" for key in props])

            # 根据主键和外键情况确定关系的属性值
            relation_type = ""
            if is_primary_key and is_foreign_key:
                relation_type = "primary_and_foreign_key"
            elif is_primary_key:
                relation_type = "primary_key"
            elif is_foreign_key:
                relation_type = "foreign_key"
            else:
                # relation_type = "normal_column"
                relation_type = "——"

            session.run(f"""
                MATCH (t:Table {{name: ${'table_name'}}})
                CREATE (c:Column {{ {property_str} }})
                CREATE (t)-[r:HAS_COLUMN {{relation_type: '{relation_type}'}}]->(c)
            """, table_name=table_name, **props, relation_type=relation_type)

    def _create_foreign_key_relations_in_neo4j(self, from_table, from_column, to_table, to_column):
        """
        在Neo4j图数据库中创建外键关系对应的节点和关系。
        针对两个表之间可能存在的多外键引用情况，为每一条外键关系都创建一条关系边，具有指定属性，
        新增关联列信息格式的属性，同时对to_table节点添加referenced_path属性，对to_table的to_column节点添加referenced_by属性，
        对from_table节点添加main_reference_path属性，对from_table的from_column节点添加referenced_to属性。

        :param from_table: 外键来源表
        :param from_column: 外键来源列
        :param to_table: 外键目标表
        :param to_column: 外键目标列
        """
        if to_column is None:
            # 获取to_table的主键列信息（以SQLite为例，通过PRAGMA查询，不同数据库需相应调整）
            with sqlite3.connect(self.database_file) as conn:
                cursor = conn.cursor()
                cursor.execute(f"PRAGMA table_info({to_table})")
                columns_info = cursor.fetchall()
                primary_key_column = None
                for column_info in columns_info:
                    if column_info[5] == 1:  # 假设第6个元素（索引为5）表示是否为主键，1为主键，0为非主键，不同数据库该位置可能不同
                        primary_key_column = column_info[1]  # 第2个元素（索引为1）是列名
                        break
                to_column = primary_key_column
        reference_path = f"{from_table}.{from_column}->{to_table}.{to_column}"
        with self.neo4j_driver.session() as session:
            session.run("""
                MATCH (from_table:Table {name: $from_table})
                MATCH (to_table:Table {name: $to_table})
                MERGE (from_table)-[r:FOREIGN_KEY {
                from_table: $from_table,
                from_column: $from_column,
                to_table: $to_table,
                to_column: $to_column,
                reference_path: $reference_path
            }]->(to_table)
                // 设置to_table节点的referenced_path属性
                SET to_table.referenced_by = $reference_path
                // 设置from_table节点的main_reference_path属性
                SET from_table.reference_to = $reference_path
                // 使用WITH语句进行过渡，传递相关节点数据到下一个语句块
                WITH from_table, to_table
                MATCH (from_table)-[:HAS_COLUMN]->(from_column_node:Column {name: $from_column})
                SET from_column_node.referenced_to = coalesce(from_column_node.referenced_to, []) + [$to_table + '.' + $to_column]
                // 添加WITH语句进行过渡，将to_table和from_table传递到下一个MATCH语句所在块
                WITH to_table, from_table
                MATCH (to_table)-[:HAS_COLUMN]->(to_column_node:Column {name: $to_column})
                SET to_column_node.referenced_by = coalesce(to_column_node.referenced_by, []) + [$from_table + '.' + $from_column]
            """, from_table=from_table, from_column=from_column, to_table=to_table, to_column=to_column,
                        reference_path=reference_path)

    def _get_column_samples(self, table_name, column_name):
        """
        随机抽样获取列的数据样本。

        :param table_name: 表名
        :param column_name: 列名
        :return: 列的随机抽样数据
        """
        samples = []
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            try:
                # 查询列数据，最多取100条记录
                cursor.execute(f"SELECT {column_name} FROM {table_name} LIMIT 100;")
                rows = cursor.fetchall()
                values = [row[0] for row in rows if row[0] is not None]

                # 获取随机样本，最多取5条（如果数据量小于等于5则取全部）
                samples = random.sample(values, min(len(values), 5))
            except Exception as e:
                print(f"Error getting samples for column {column_name} in table {table_name}: {e}")
        return samples

    def _is_primary_key(self, table_name, column_name):
        """
        判断指定表中的指定列是否为主键，通过查询数据库元数据（以SQLite为例）。

        :param table_name: 表名
        :param column_name: 列名
        :return: True如果是主键，False否则
        """
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns_info = cursor.fetchall()
            for column_info in columns_info:
                if column_info[1] == column_name:  # 第2个元素（索引为1）是列名
                    return bool(column_info[5])  # 第6个元素（索引为5）表示是否为主键，1为主键，0为非主键，不同数据库该位置可能不同
        return False

    def _is_foreign_key(self, table_name, column_name):
        """
        判断指定表中的指定列是否为外键，通过查询数据库元数据（以SQLite为例）。

        :param table_name: 表名
        :param column_name: 列名
        :return: True如果是外键，False否则
        """
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            foreign_keys = cursor.fetchall()
            for foreign_key in foreign_keys:
                if foreign_key[3] == column_name:  # 第4个元素（索引为3）是本地列名，对应外键列
                    return True
        return False

    def _get_numeric_attributes(self, table_name, column_name, values):
        """
        计算数值型列的附加属性（平均数、众数、空值比例等）。

        :param table_name: 表名
        :param column_name: 列名
        :param values: 列的数据值列表
        :return: 数值型列的附加属性字典
        """
        additional_attributes = {}
        is_id_column = "id" in column_name.lower()
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            try:
                # 查询列的所有数据，用于计算如空值比例、完整性等指标
                cursor.execute(f"SELECT {column_name} FROM {table_name}")
                rows = cursor.fetchall()
                if not is_id_column:
                    additional_attributes['numeric_mode'] = self._get_mode(values)
                    additional_attributes['numeric_null_ratio'] = len([v for v in values if v is None]) / len(
                        rows) if rows else 0
                    additional_attributes['numeric_completeness'] = (len(values) / len(rows)) if rows else 0
                    if values:
                        additional_attributes['numeric_mean'] = np.mean(values)
                    else:
                        additional_attributes['numeric_mean'] = None
                additional_attributes['numeric_range'] = [min(values), max(values)] if values else None
            except Exception as e:
                print(f"Error processing numeric attributes for column {column_name} in table {table_name}: {e}")
        return additional_attributes

    def _get_text_attributes(self, table_name, column_name, values):
        """
        计算文本型列的附加属性（词频、平均字符长度、类别等）。

        :param table_name: 表名
        :param column_name: 列名
        :param values: 列的数据值列表
        :return: 文本型列的附加属性字典
        """
        additional_attributes = {}
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            try:
                # 查询列的所有数据，用于计算如空值比例、完整性等指标
                cursor.execute(f"SELECT {column_name} FROM {table_name}")
                rows = cursor.fetchall()

                if len(set(values)) <= 6:
                    additional_attributes['category_categories'] = list(set(values))
                additional_attributes['average_char_length'] = self._get_average_char_length(values) if values else 0
                word_frequency_dict = self._get_word_frequency(values) if values else {}
                additional_attributes['word_frequency'] = json.dumps(word_frequency_dict)
                additional_attributes['null_ratio'] = len([v for v in values if v is None]) / len(rows) if rows else 0
                additional_attributes['completeness'] = (len(values) / len(rows)) if rows else 0
            except Exception as e:
                print(f"Error processing text attributes for column {column_name} in table {table_name}: {e}")
        return additional_attributes

    def _get_time_attributes(self, table_name, column_name, values):
        """
        计算时间型列的附加属性（时间跨度、空值比例等）。

        :param table_name: 表名
        :param column_name: 列名
        :param values: 列的数据值列表
        :return: 时间型列的附加属性字典
        """
        additional_attributes = {}
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            try:
                # 查询列的所有数据，用于计算如空值比例、完整性等指标
                cursor.execute(f"SELECT {column_name} FROM {table_name}")
                rows = cursor.fetchall()

                datetime_values = [convert_date_string(v) for v in values if convert_date_string(v) is not None]
                if datetime_values:
                    min_time = min(datetime_values)
                    max_time = max(datetime_values)
                    time_diff = max_time - min_time
                    additional_attributes['time_span'] = f"{time_diff.days} days"
                additional_attributes['time_null_ratio'] = len([v for v in values if v is None]) / len(
                    rows) if rows else 0
                additional_attributes['time_completeness'] = (len(values) / len(rows)) if rows else 0
            except Exception as e:
                print(f"Error processing time attributes for column {column_name} in table {table_name}: {e}")
        return additional_attributes

def parse_and_store_schema(self):
    """
    解析SQLite数据库的schema信息，并将其存储到Neo4j图数据库中。
    每次运行清空Neo4j数据库中的所有节点和关系。
    :return: 解析后的schema信息（以字典形式表示，包含表、列、外键关系等），同时返回包含属性信息的DataFrame
    """
    self._clear_neo4j_database()
    schema = defaultdict(lambda: defaultdict(list))
    all_columns_info = []  # 用于存储所有列的信息，以便后续构建DataFrame

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
                samples = self._get_column_samples(table_name, column_name)
                values = [row[0] for row in cursor.fetchall() if row[0] is not None]  # 获取完整数据值列表

                # 判断列类型并获取相应附加属性
                if data_type.upper() in ["INTEGER", "REAL"]:
                    additional_attributes = self._get_numeric_attributes(table_name, column_name, values)
                elif data_type.upper() in ["TEXT", "VARCHAR"]:
                    additional_attributes = self._get_text_attributes(table_name, column_name, values)
                elif data_type.upper() in ["DATE", "DATETIME"]:
                    additional_attributes = self._get_time_attributes(table_name, column_name, values)
                else:
                    additional_attributes = {}

                # 判断是否为主键或外键，添加key_type属性（仅针对主键或外键列）
                key_type = []
                if self._is_primary_key(table_name, column_name):
                    key_type.append("primary_key")
                if self._is_foreign_key(table_name, column_name):
                    key_type.append("foreign_key")
                if key_type:
                    additional_attributes['key_type'] = key_type

                # 添加数据条数属性（所有类型列）
                additional_attributes['data_count'] = len(values) if values else 0

                schema[table_name]['columns'].append((column_name, data_type, samples, additional_attributes))
                all_columns_info.append({
                    "table_name": table_name,
                    "column_name": column_name,
                    "data_type": data_type,
                    "samples": samples,
                    "attributes": additional_attributes
                })

                # 在Neo4j中创建列节点，并与对应的表节点建立关系
                self._create_column_node_and_relation_in_neo4j(table_name, column_name, data_type, samples,
                                                               additional_attributes)
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

    # 将所有列信息转换为DataFrame
    columns_df = pd.DataFrame(all_columns_info)
    return schema, columns_df


if __name__ == "__main__":
    # Neo4j数据库连接配置
    neo4j_uri = "bolt://localhost:7687"  # 根据实际情况修改
    neo4j_user = "neo4j"  # 根据实际情况修改
    neo4j_password = "12345678"  # 根据实际情况修改
    database_file = "../data/bird/books/books.sqlite"
    # database_file = "E:/spider/database/soccer_1/soccer_1.sqlite"
    # database_file = "../data/spider/e_commerce.sqlite"
    # database_file = "../data/spider/medicine_enzyme_interaction/medicine_enzyme_interaction.sqlite"

    parser = SchemaParser(neo4j_uri, neo4j_user, neo4j_password, database_file)
    schema, columns_df = parser.parse_and_store_schema()  # 接收DataFrame
    parser.close_connections()
    print(schema)
    print(columns_df)  # 打印DataFrame，可根据需求进一步分析、保存等操作