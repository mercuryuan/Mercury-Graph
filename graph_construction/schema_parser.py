import csv
import json
import operator
import os
import sqlite3
import random
from collections import defaultdict, Counter
from datetime import datetime
from decimal import Decimal
import chardet
import numpy as np
from scipy.stats import norm, kstest
from neo4j import GraphDatabase

from src.neo4j_connector import get_driver

from datetime import datetime
from dateutil import parser

from datetime import date, datetime


def convert_date_string(date_str):
    """
    尝试将输入的日期字符串按照多种常见格式转换为datetime对象或date对象。

    :param date_str: 日期字符串
    :return: 转换后的datetime对象或date对象，如果转换失败则返回None
    """
    # 检查 date_str 是否为字符串类型，如果不是则尝试转换为字符串
    # print(date_str)
    if not isinstance(date_str, str):
        try:
            date_str = str(date_str)
        except Exception as e:
            print(f"无法将输入 {date_str} 转换为字符串类型，错误信息: {e}")
            return None

    date_formats = [
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
        '%d-%m-%Y %H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',  # 新增的日期时间格式
        '%Y/%m/%d %H:%M:%S.%f',  # 新增的日期时间格式
        '%Y.%m.%d %H:%M:%S.%f',  # 新增的日期时间格式
        '%m/%d/%Y %H:%M:%S.%f',  # 新增的日期时间格式
        '%m-%d-%Y %H:%M:%S.%f',  # 新增的日期时间格式
        '%d/%m/%Y %H:%M:%S.%f',  # 新增的日期时间格式
        '%d-%m-%Y %H:%M:%S.%f',  # 新增的日期时间格式
        '%Y'  # 仅年份的格式
    ]
    for format_str in date_formats:
        try:
            dt = datetime.strptime(date_str, format_str)
            # 如果格式是纯日期（没有时间部分），返回 date 对象
            if format_str in ['%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y', '%d-%m-%Y', '%Y']:
                if format_str == '%Y':
                    # 对于仅年份的格式，将其转换为该年的 1 月 1 日
                    return date(dt.year, 1, 1)
                return dt.date()
            return dt
        except ValueError:
            continue
    # print(f"无法将日期字符串 {date_str} 转换为有效的日期时间格式，请检查数据格式！(大概率是问题数据，建议跳过)")
    return None


def quote_identifier(identifier):
    """
    引用标识符（表名或列名），防止包含空格或特殊字符时出错。

    :param identifier: 表名或列名
    :return: 引用后的标识符
    """
    return f'"{identifier}"'  # 使用双引号引用


class SchemaParser:
    def __init__(self, driver, database_file=None):
        """
        初始化SchemaParser类，建立与Neo4j和SQLite数据库的连接。

        :param neo4j_uri: Neo4j数据库的连接地址
        :param neo4j_user: Neo4j数据库的用户名
        :param neo4j_password: Neo4j数据库的密码
        :param database_file: SQLite数据库文件路径
        """
        # 创建 Neo4j 驱动连接
        self.neo4j_driver = driver
        self.database_file = database_file

    def close_connections(self):
        """
        关闭与Neo4j数据库的连接。
        """
        self.neo4j_driver.close()

    def clear_neo4j_database(self):
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
        self.clear_neo4j_database()
        schema = defaultdict(lambda: defaultdict(list))
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            # 获取所有表名
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            for table in tables:
                table_name = table[0]
                row_count = self._get_table_row_count(table_name)
                # 在Neo4j中创建表节点
                self._create_table_node_in_neo4j(table_name)
                # 获取表的字段信息
                cursor.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
                columns = cursor.fetchall()
                for column in columns:
                    column_name = column[1]
                    data_type = column[2]
                    # 如果表的行数小于等于100,000
                    if row_count <= 100000:
                        # 对列进行抽样，并计算列的附加属性
                        samples, additional_attributes = self._get_column_samples_and_attributes(table_name,
                                                                                                 column_name,
                                                                                                 data_type)
                    # 如果表的行数大于100,000
                    else:
                        # 对列进行抽样，但抽样数量限制为100,000
                        samples, additional_attributes = self._get_column_samples_and_attributes(table_name,
                                                                                                 column_name,
                                                                                                 data_type, 100000)

                    schema[table_name]['columns'].append((column_name, data_type, samples, additional_attributes))
                    # 在Neo4j中创建列节点，并与对应的表节点建立关系
                    self._create_column_node_and_relation_in_neo4j(table_name, column_name, data_type, samples,
                                                                   additional_attributes)
            for table in tables:
                table_name = table[0]
                # 获取表的外键关系（如果有）
                cursor.execute(f"PRAGMA foreign_key_list({quote_identifier(table_name)})")
                foreign_keys = cursor.fetchall()
                for foreign_key in foreign_keys:
                    from_column = foreign_key[3]
                    to_table = foreign_key[2]
                    to_column = foreign_key[4]
                    schema[table_name]['foreign_keys'].append((from_column, to_table, to_column))
                    # 在Neo4j中创建外键关系对应的节点和关系
                    self._create_foreign_key_relations_in_neo4j(table_name, from_column, to_table, to_column)
        return schema

    import sqlite3

    def _create_table_node_in_neo4j(self, table_name):
        """
        在Neo4j图数据库中创建表示表的节点，并根据实际情况为表节点添加主键、外键、包含的列名列表、表的数据条数以及列数等属性。
        属性名为primary_key、foreign_key、columns、row_count、column_count，主键外键如果只有一个就单独为主外键名称，若有多个才返回键列表，若没有则不添加相应属性。
        新增功能：对名为sqlite_sequence的表不进行节点创建。

        :param table_name: 表名
        """
        if table_name == "sqlite_sequence":
            return  # 如果表名是sqlite_sequence，直接返回，不进行后续创建节点的操作

        # 提取数据库名称
        database_name = self.extract_database_name(self.database_file)

        # 获取表的主键、外键、列名列表、行数和列数
        primary_key_columns = self._get_primary_key_columns(table_name)
        foreign_key_columns = self._get_foreign_key_columns(table_name)
        columns = self._get_table_columns(table_name)  # 获取表包含的列名列表
        row_count = self._get_table_row_count(table_name)  # 获取表的数据条数
        column_count = len(columns) if columns else 0  # 获取表的列数

        # 构造表节点的属性字典
        properties = {
            "name": table_name,
            "database_name": database_name  # 添加数据库名称属性
        }
        if primary_key_columns:
            properties["primary_key"] = primary_key_columns if len(primary_key_columns) > 1 else primary_key_columns[0]
        if foreign_key_columns:
            properties["foreign_key"] = foreign_key_columns if len(foreign_key_columns) > 1 else foreign_key_columns[0]
        if columns:
            properties["columns"] = columns
        if row_count is not None:
            properties["row_count"] = row_count
        if column_count > 0:
            properties["column_count"] = column_count

        # 构造Cypher查询语句
        property_str = ', '.join(f"{key}: ${key}" for key in properties)
        query = f"CREATE (:Table {{ {property_str} }})"

        # 执行Cypher查询
        with self.neo4j_driver.session() as session:
            session.run(query, **properties)

    def _get_table_columns(self, table_name):
        """
        获取指定表包含的所有列名列表。

        :param table_name: 表名
        :return: 列名列表
        """
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
            columns_info = cursor.fetchall()
            columns = [column_info[1] for column_info in columns_info]
        return columns

    def _get_table_row_count(self, table_name):
        """
        获取指定表的数据条数。

        :param table_name: 表名
        :return: 表的数据条数，如果获取失败返回None
        """
        try:
            with sqlite3.connect(self.database_file) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {quote_identifier(table_name)}")
                row_count = cursor.fetchone()[0]
                return row_count
        except Exception as e:
            print(f"获取表 {table_name} 数据条数时出错: {e}")
            return None

    def _get_primary_key_columns(self, table_name):
        """
        获取指定表的主键列信息（以 SQLite 为例）。

        :param table_name: 表名
        :return: 主键列名列表，如果是单个主键则返回只包含该列名的列表，无主键返回空列表
        """
        try:
            with sqlite3.connect(self.database_file) as conn:
                cursor = conn.cursor()
                sql_statement = f"PRAGMA table_info({quote_identifier(table_name)})"
                cursor.execute(sql_statement)
                columns_info = cursor.fetchall()
                primary_key_columns = []
                for column_info in columns_info:
                    if column_info[5] != 0:  # 假设第 6 个元素（索引为 5）表示是否为主键，1 为主键，0 为非主键，不同数据库该位置可能不同
                        primary_key_columns.append(column_info[1])  # 第 2 个元素（索引为 1）是列名
                return primary_key_columns
        except sqlite3.Error as e:
            print(f"Error occurred while executing SQL statement: {sql_statement}")
            print(f"Error message: {e}")
            return []

    def _get_foreign_key_columns(self, table_name):
        """
        获取指定表的外键列信息（以 SQLite 为例）。

        :param table_name: 表名
        :return: 外键列名列表，如果是单个外键则返回只包含该列名的列表，无外键返回空列表
        """
        try:
            with sqlite3.connect(self.database_file) as conn:
                cursor = conn.cursor()
                sql_statement = f"PRAGMA foreign_key_list({quote_identifier(table_name)})"
                cursor.execute(sql_statement)
                foreign_keys = cursor.fetchall()
                foreign_key_columns = [fk[3] for fk in foreign_keys]  # 第 4 个元素（索引为 3）是本地列名，对应外键列
                return foreign_key_columns
        except sqlite3.Error as e:
            print(f"Error occurred while executing SQL statement: {sql_statement}")
            print(f"Error message: {e}")
            return []

    def read_column_description_csv(self, table_name):
        """
        从对应的CSV文件中读取指定表的列描述信息。
        特别地，当表名为 "sqlite_sequence" 时，直接返回空列表。

        :param table_name: 表名
        :return: 包含列描述信息的字典列表，每个字典包含'original_column_name'、'column_name'、
                 'column_description'、'data_format'、'value_description'等键值对
        """
        # 获取 database_file 的目录部分
        if table_name == "sqlite_sequence":
            return []
        dir_path = os.path.dirname(self.database_file)
        file_path = os.path.join(dir_path, "database_description", f"{table_name}.csv")  # 假设文件路径格式如此，可根据实际调整
        column_descriptions = []
        try:
            # 先尝试使用 utf-8-sig 编码打开文件
            with open(file_path, 'r', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    expected_keys = ['original_column_name', 'column_name', 'column_description', 'data_format',
                                     'value_description']
                    if all(key in row for key in expected_keys):
                        column_descriptions.append(row)
                    else:
                        print(f"行数据 {row} 缺少预期键，已跳过该数据")
                return column_descriptions
        except UnicodeDecodeError:
            # 编码错误时，动态检测文件编码
            try:
                with open(file_path, 'rb') as raw_file:
                    raw_data = raw_file.read()
                    detected_encoding = chardet.detect(raw_data)['encoding']
                with open(file_path, 'r', encoding=detected_encoding) as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        expected_keys = ['original_column_name', 'column_name', 'column_description', 'data_format',
                                         'value_description']
                        if all(key in row for key in expected_keys):
                            column_descriptions.append(row)
                        else:
                            print(f"行数据 {row} 缺少预期键，已跳过该数据")
                    return column_descriptions
            except Exception as e:
                print(f"读取文件时发生错误，尝试动态编码检测后仍失败: {e}")
                return []
        except FileNotFoundError:
            # 先注释掉
            print(f"未找到表 {table_name} 对应的列描述文件 {file_path}")
            return []

    def _create_column_node_and_relation_in_neo4j(self, table_name, column_name, data_type, samples,
                                                  additional_attributes):
        """
        在Neo4j图数据库中创建表示列的节点，并建立其与对应表节点的关系。
        将additional_attributes扁平化处理，每个属性单独作为列节点的属性存储，
        同时为关系添加属性，以区别列节点是普通列、主键列、外键列、还是同时作为主键和外键。
        新增功能：添加从列描述文件中读取的column_name、column_description、value_description属性（当描述不为空时添加）。

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

        # 读取列描述文件获取当前列的详细描述信息
        column_descriptions = self.read_column_description_csv(table_name)
        column_desc = None
        for desc in column_descriptions:
            try:
                if desc["original_column_name"] == column_name:
                    column_desc = desc
                    break
            except KeyError:
                print(f"字典中缺少original_column_name键，对应数据可能有问题，当前字典为：{desc}")
                continue

        with self.neo4j_driver.session() as session:
            props = {
                "name": column_name,
                "data_type": data_type,
                "samples": samples
            }
            # 扁平化处理additional_attributes字典，将每个键值对添加到props字典中
            for key, value in additional_attributes.items():
                props[key] = value

            # 根据列描述信息添加相应属性（当描述不为空时添加）
            if column_desc:
                if column_desc["column_description"]:
                    props["column_description"] = column_desc["column_description"].replace('\n', '') # 去掉换行符
                if column_desc["value_description"]:
                    props["value_description"] = column_desc["value_description"]

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
                relation_type = "normal_column"
                # 这个值只是为了便于观察
                # relation_type = "——"

            session.run(f"""
                            MATCH (t:Table {{name: ${'table_name'}}})
                            CREATE (c:Column {{ {property_str} }})
                            CREATE (t)-[r:HAS_COLUMN {{relation_type: '{relation_type}'}}]->(c)
                        """, table_name=table_name, **props, relation_type=relation_type)

    def _create_foreign_key_relations_in_neo4j(self, from_table, from_column, to_table, to_column):
        # 如果未指定目标列，则获取目标表的主键列
        if to_column is None:
            with sqlite3.connect(self.database_file) as conn:
                cursor = conn.cursor()
                cursor.execute(f"PRAGMA table_info({to_table})")
                columns_info = cursor.fetchall()
                primary_key_column = None
                for column_info in columns_info:
                    if column_info[5] == 1:  # 假设第6个元素（索引为5）表示是否为主键
                        primary_key_column = column_info[1]  # 第2个元素（索引为1）是列名
                        break
                to_column = primary_key_column

        # 构造外键引用路径
        reference_path = f"{from_table}.{from_column}->{to_table}.{to_column}"

        with self.neo4j_driver.session() as session:
            # result = session.run("""
            #     MATCH (from_table:Table {name: $from_table})
            #     MATCH (to_table:Table {name: $to_table})
            #     RETURN from_table, to_table
            # """, from_table=from_table, to_table=to_table)
            #
            # records = result.data()
            # if not records:
            #     print(f"未找到表节点: {from_table} 或 {to_table}，无法创建外键关系。")
            #     return

            session.run("""
                MATCH (from_table:Table {name: $from_table})
                MATCH (to_table:Table {name: $to_table})
                // 创建外键关系
                MERGE (from_table)-[r:FOREIGN_KEY {
                    from_table: $from_table,
                    from_column: $from_column,
                    to_table: $to_table,
                    to_column: $to_column,
                    reference_path: $reference_path
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
                        reference_path=reference_path)

    import numpy as np
    from decimal import Decimal

    def _get_column_samples_and_attributes(self, table_name, column_name, data_type, sample_size=None):
        """
        随机抽样获取列的数据样本，并计算附加属性（范围或类别等多种属性）。
        实现为所有类型的列节点添加数据条数属性，对于非id主键的数值型数据添加平均数等相关属性，
        同时根据数据库设计判断列是否为主键或外键并统一添加相应属性到key_type。
        对传入的数据类型进行统一处理，正确识别类似VARCHAR(50)这种带长度限定的数据类型为对应的基础类型（文本类型），以便后续属性计算。
        新增列是否可为空和列是否可重复的属性。

        :param table_name: 表名
        :param column_name: 列名
        :param data_type: 列的数据类型（可能包含类似VARCHAR(50)带长度限定的格式）
        :return: 列的随机抽样数据和按照特定命名规则组织的附加属性字典
        """
        samples = []
        additional_attributes = {}
        # 处理数据类型，去除括号及里面的长度限定部分，统一为基础类型名称
        base_data_type = data_type.split('(')[0].upper()

        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            # 查询列数据
            if sample_size is not None:
                # 如果指定了抽样个数，则限制查询结果
                query = f"SELECT {quote_identifier(column_name)} FROM {quote_identifier(table_name)} LIMIT {sample_size};"
            else:
                # 否则查询全部数据
                query = f"SELECT {quote_identifier(column_name)} FROM {quote_identifier(table_name)} ;"

            cursor.execute(query)
            rows = cursor.fetchall()
            all_values = [row[0] for row in rows]

            # 过滤空值（包括 None、空字符串和仅含空格的字符串）
            def is_empty(value):
                return value is None or (isinstance(value, str) and value.strip() == "")

            non_null_values = [v for v in all_values if not is_empty(v)]

            # 数据完整性统计
            null_count = len(all_values) - len(non_null_values)
            additional_attributes['null_count'] = null_count
            # 计算数据完整性并以百分比形式存储
            additional_attributes['data_integrity'] = "{:.0f}%".format(
                len(non_null_values) / len(all_values) * 100) if all_values else "100%"

            # if null_count > 0:
            #     print(f"过滤掉了 {table_name} 中 {column_name} 的 {null_count} 个空值数据")

            # 获取随机样本，最多取6条（如果数据量小于等于5则取全部）
            samples = random.sample(non_null_values, min(len(non_null_values), 6))

            # 为所有类型列节点添加抽样个数属性
            additional_attributes['sample_count'] = len(non_null_values) if non_null_values else 0

            # 查询列是否可为空
            is_nullable = self._is_column_nullable(table_name, column_name)
            additional_attributes['is_nullable'] = is_nullable

            # 查询列是否为主键
            is_primary_key = self._is_primary_key(table_name, column_name)
            # 查询列是否为外键
            is_foreign_key = self._is_foreign_key(table_name, column_name)

            numeric_types = [
                "INTEGER", "INT", "SMALLINT", "BIGINT", "TINYINT", "MEDIUMINT",  # 整数类型
                "REAL", "FLOAT", "DOUBLE",  # 浮点数类型
                "DECIMAL", "NUMERIC",  # 高精度小数类型
                "BOOLEAN"  # 布尔类型
            ]
            text_types = [
                "TEXT", "VARCHAR", "CHAR", "NCHAR", "NVARCHAR", "NTEXT",  # 常见文本类型
                "CLOB", "TINYTEXT", "MEDIUMTEXT", "LONGTEXT",  # 大文本类型
                "JSON", "XML"  # 结构化文本类型
            ]

            if base_data_type in numeric_types:
                # 过滤掉非数值型数据
                valid_values = [v for v in non_null_values if isinstance(v, (int, float)) and v != '']
                filtered_count = len(non_null_values) - len(valid_values)
                if filtered_count > 0:
                    print(f"过滤掉了 {table_name} 中 {column_name} 的 {filtered_count} 个非数值数据")

                try:
                    # 计算数值范围
                    additional_attributes['numeric_range'] = [min(valid_values),
                                                              max(valid_values)] if valid_values else None

                    is_id_column = "id" in column_name.lower()
                    if not is_id_column:
                        # 计算众数
                        mode = self._get_mode(valid_values)
                        # 若次数大于1次的众数存在，则将其添加到附加属性中
                        if mode:
                            additional_attributes['numeric_mode'] = mode

                        # 计算平均值
                        if valid_values:
                            try:
                                if base_data_type in ["DECIMAL", "NUMERIC"]:
                                    additional_attributes['numeric_mean'] = float(
                                        np.mean([float(Decimal(str(v))) for v in valid_values]))
                                elif base_data_type == "BOOLEAN":
                                    additional_attributes['numeric_mean'] = float(
                                        np.mean([int(v) for v in valid_values]))
                                else:
                                    additional_attributes['numeric_mean'] = float(np.mean(valid_values))
                            except Exception as e:
                                print(f"计算平均值时出错: {e}")
                                print(f"表名: {table_name}, 列名: {column_name}")
                                additional_attributes['numeric_mean'] = None
                        else:
                            additional_attributes['numeric_mean'] = None
                except Exception as e:
                    print(f"计算数值范围时出错: {e}")
                    print(f"表名: {table_name}, 列名: {column_name}")
                    additional_attributes['numeric_range'] = None

            elif base_data_type in text_types:
                # 如果唯一值数量小于等于 6，将其视为类别型数据
                if len(set(non_null_values)) <= 6:
                    additional_attributes['text_categories'] = list(set(non_null_values))

                # 计算平均字符长度
                additional_attributes['average_char_length'] = self._get_average_char_length(
                    non_null_values) if non_null_values else 0

                # 计算词频属性，并转换为 JSON 字符串
                word_frequency_dict = self._get_word_frequency(non_null_values) if non_null_values else {}
                additional_attributes['word_frequency'] = json.dumps(word_frequency_dict, ensure_ascii=False)

            elif base_data_type in ["DATE", "DATETIME", "TIMESTAMP"]:
                additional_attributes['time_span'] = self._get_time_span(non_null_values) if non_null_values else None
                time_attributes = self.calculate_time_attributes(non_null_values)
                additional_attributes.update(time_attributes)

            # 根据主键或外键查询结果添加key_type属性（仅针对主键或外键列）
            key_type = []
            if is_primary_key:
                key_type.append("primary_key")
            if is_foreign_key:
                key_type.append("foreign_key")
            if key_type:
                additional_attributes['key_type'] = key_type

        return samples, additional_attributes

    def _is_column_nullable(self, table_name, column_name):
        """
        判断列是否可为空。

        :param table_name: 表名
        :param column_name: 列名
        :return: True 表示列可为空，False 表示列不允许为空
        """
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
            columns_info = cursor.fetchall()
            for column_info in columns_info:
                if column_info[1] == column_name:  # 第2个元素（索引为1）是列名
                    notnull = column_info[3]  # 第4个元素（索引为3）表示是否允许为空，0 表示允许为空，1 表示不允许为空
                    return not notnull  # 当 notnull 为 0 时返回 True，为 1 时返回 False
        return None

    def _is_primary_key(self, table_name, column_name):
        """
        判断指定表中的指定列是否为主键，通过查询数据库元数据（以SQLite为例）。

        :param table_name: 表名
        :param column_name: 列名
        :return: True如果是主键，False否则
        """
        with sqlite3.connect(self.database_file) as conn:
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({quote_identifier(table_name)})")
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
            cursor.execute(f"PRAGMA foreign_key_list({quote_identifier(table_name)})")
            foreign_keys = cursor.fetchall()
            for foreign_key in foreign_keys:
                if foreign_key[3] == column_name:  # 第4个元素（索引为3）是本地列名，对应外键列
                    return True
        return False

    from collections import Counter
    from decimal import Decimal

    def _get_mode(self, values):
        """
        获取数值型或类别型数据的众数，全面考虑数据库数据中可能出现的多种情况，准确返回众数结果（支持返回多个众数情况）。

        :param values: 数据列表
        :return: 众数列表，如果不存在众数则返回空列表
        """
        if not values:
            return []

        # 处理高精度数值类型（如 DECIMAL）
        if all(isinstance(v, Decimal) for v in values):
            values = [float(v) for v in values]  # 将 Decimal 转换为 float 以便统计

        # 处理布尔类型
        if all(isinstance(v, bool) for v in values):
            values = [int(v) for v in values]  # 将布尔值转换为整数以便统计

        # 使用 Counter 统计每个元素出现的次数
        count_dict = Counter(values)
        max_count = max(count_dict.values())
        if max_count <= 1:
            return []
        # 找出所有出现次数等于最大次数的元素，即众数
        modes = [k for k, v in count_dict.items() if v == max_count]

        return modes

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

    from collections import Counter
    import operator

    import json

    def _get_word_frequency(self, values, top_k=10, by_word=False):
        """
        统计文本型数据的词频，支持按词语或整个值为单位统计，并返回前 top_k 个高频词。

        :param values: 文本数据列表，函数将对该列表中的文本数据进行词频统计。若列表为空，则直接返回空字典。
        :param top_k: 返回的高频词数量，默认值为 10。在统计完成后，函数将按照词频从高到低排序，尝试取前 top_k 个高频词作为结果。
        :param by_word: 是否以词语为单位统计词频，默认值为 False。
            - 若为 True，则会将文本数据拆分为单个词语，以每个词语为单位统计词频。
            - 若为 False，则以整个文本值为单位统计词频。
        :return: 词频字典，格式为 {"word": frequency}，包含前 top_k 个高频词且按频率从高到低排序。
            特殊情况：从第一个频率为 1 的词开始，最多保留三个频率为 1 的词，且词频为 1 的词长度不能超过 20。
        """
        # 检查输入的文本数据列表是否为空
        if not values:
            return {}

        # 统计词频
        if by_word:
            # 以词语为单位统计
            # 将文本数据列表中的所有文本连接成一个长字符串，再按空格拆分为单个单词
            all_words = " ".join(values).split()
            word_count_dict = Counter(all_words)
        else:
            # 以整个值为单位统计
            word_count_dict = Counter(values)

        # 按照词频从高到低排序
        sorted_word_count_dict = dict(
            sorted(word_count_dict.items(), key=operator.itemgetter(1), reverse=True)
        )

        result = {}
        one_freq_count = 0
        found_one_freq = False

        for word, freq in sorted_word_count_dict.items():
            if len(result) >= top_k:
                break
            if freq == 1:
                found_one_freq = True
                if len(word) <= 20 and one_freq_count < 3:
                    result[word] = freq
                    one_freq_count += 1
            else:
                if not found_one_freq:
                    result[word] = freq

        return result

    def _get_time_span(self, values):
        """
        计算时间类型数据的时间跨度，兼容多种日期时间格式的数据。

        :param values: 时间数据列表
        :return: 时间跨度描述字符串（示例，可按需求调整格式）
        """
        if values:
            datetime_values = [convert_date_string(v) for v in values if convert_date_string(v) is not None]
            if datetime_values:
                min_time = min(datetime_values)
                max_time = max(datetime_values)
                time_diff = max_time - min_time
                return f"{time_diff.days} days"
        return None

    def calculate_time_attributes(self, values):
        """
        计算给定时间数据列表中的最早时间和最晚时间属性，根据不同时间数据类型进行针对性处理。

        参数:
        values (list): 包含时间数据的列表，时间数据格式可能多样，例如 '2025-01-01'（date类型）、'2025-01-01 12:30:00'（datetime类型）、
                       '1983-12-29T00:00:00'（类似timestamp格式等）等。

        返回:
        dict: 包含最早时间（'earliest_time'）和最晚时间（'latest_time'）属性的字典，如果输入列表为空则对应属性值为 None。
        """
        parsed_values = []
        for v in values:
            if isinstance(v, str):
                if "T" in v:
                    # 处理类似timestamp格式
                    try:
                        parsed = parser.isoparse(v)
                    except ValueError:
                        parsed = None
                else:
                    # 处理普通日期时间格式
                    parsed = convert_date_string(v)
            elif isinstance(v, datetime):
                parsed = v
            elif isinstance(v, date):
                parsed = v  # 保留 date 对象
            else:
                parsed = None

            if parsed:
                parsed_values.append(parsed)

        if parsed_values:
            # 根据类型决定格式化方式
            def format_value(value):
                if isinstance(value, date) and not isinstance(value, datetime):
                    return value.strftime('%Y-%m-%d')  # 只格式化日期部分
                else:
                    return value.strftime('%Y-%m-%d %H:%M:%S')  # 格式化日期和时间部分

            time_attributes = {
                'earliest_time': format_value(min(parsed_values)),
                'latest_time': format_value(max(parsed_values))
            }
        else:
            time_attributes = {
                'earliest_time': None,
                'latest_time': None
            }

        return time_attributes

    def extract_dataset_name(self, database_file):
        possible_datasets = ['bird', 'spider', 'BIRD']
        for dataset_name in possible_datasets:
            if dataset_name in database_file:
                return dataset_name
        return None

    def extract_database_name(self, database_file):
        """
        从给定的数据库文件路径中提取数据库名称。

        :param database_file: 数据库文件的路径
        :return: 数据库名称（不带路径和扩展名）
        """
        # 使用 os.path.basename 获取文件名（带扩展名）
        file_name = os.path.basename(database_file)
        # 使用 os.path.splitext 去除扩展名
        database_name = os.path.splitext(file_name)[0]
        return database_name


if __name__ == "__main__":
    # Neo4j数据库连接配置
    neo4j_uri = "bolt://localhost:7689"  # 根据实际情况修改
    neo4j_user = "neo4j"  # 根据实际情况修改
    neo4j_password = "12345678"  # 根据实际情况修改
    # database_file = "../data/bird/books/books.sqlite"
    database_file = "../data/bird/shakespeare/shakespeare.sqlite"
    # database_file = "E:/spider/database/baseball_1/baseball_1.sqlite"
    # database_file = "E:/spider/database/book_2/book_2.sqlite"
    # database_file = "E:/spider/database/soccer_1/soccer_1.sqlite"
    # database_file = "../data/spider/e_commerce.sqlite"
    # database_file = "../data/spider/medicine_enzyme_interaction/medicine_enzyme_interaction.sqlite"
    # database_file = "../data/bird/app_store/app_store.sqlite" # csv描述表名对应不上
    # database_file = "E:/BIRD_train/train/train_databases/bike_share_1/bike_share_1.sqlite" # 百万级数据，对生成有效率上的挑战
    # database_file = "E:/BIRD_train/train/train_databases/car_retails/car_retails.sqlite"  # 自引用情况
    # database_file = "E:/BIRD_train/train/train_databases/donor/donor.sqlite" # 百万级数据，论文表有长文本
    # database_file = "E:/BIRD_train/train/train_databases/talkingdata/talkingdata.sqlite" # DATETIME类型有问题数据的
    # database_file = "E:/BIRD_train/train/train_databases/mondial_geo/mondial_geo.sqlite"
    # database_file = "E:/BIRD_train/train/train_databases/ice_hockey_draft/ice_hockey_draft.sqlite"
    # database_file = "E:/BIRD_train/train/train_databases/address/address.sqlite"
    # 创建 Neo4j 驱动连接
    neo4j_driver = get_driver()
    parser = SchemaParser(neo4j_driver, database_file)
    # try:
    parser.parse_and_store_schema()
    print("Schema parsing and storing completed successfully.")
    # except Exception as e:
    #     print("Error occurred during schema parsing and storing:", e)
    parser.close_connections()
    # print(parser.extract_database_name(database_file))
