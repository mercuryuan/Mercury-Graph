import json
import operator
import sqlite3
import random
from collections import defaultdict, Counter
from datetime import datetime

import numpy as np
from scipy.stats import norm, kstest
from neo4j import GraphDatabase

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
                    samples, additional_attributes = self._get_column_samples_and_attributes(table_name, column_name,
                                                                                             data_type)
                    schema[table_name]['columns'].append((column_name, data_type, samples, additional_attributes))
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
        return schema

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

    def _create_column_node_and_relation_in_neo4j(self, table_name, column_name, data_type, samples,
                                                  additional_attributes):
        """
        在Neo4j图数据库中创建表示列的节点，并建立其与对应表节点的关系。
        将additional_attributes扁平化处理，每个属性单独作为列节点的属性存储。

        :param table_name: 表名
        :param column_name: 列名
        :param data_type: 列的数据类型
        :param samples: 列的随机抽样数据
        :param additional_attributes: 列的附加属性字典
        """
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
            session.run(f"""
                MATCH (t:Table {{name: ${'table_name'}}})
                CREATE (c:Column {{ {property_str} }})
                CREATE (t)-[:HAS_COLUMN]->(c)
            """, table_name=table_name, **props)


    def _create_foreign_key_relations_in_neo4j(self, from_table, from_column, to_table, to_column):
        """
        在Neo4j图数据库中创建外键关系对应的节点和关系。
        确保表节点之间只有一条表示外键的关系边，具有指定属性，新增关联列信息格式的属性，
        同时对to_table节点添加referenced_path属性，对to_table的to_column节点添加referenced_by属性。

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
                MERGE (from_table)-[r:FOREIGN_KEY]->(to_table)
                ON CREATE SET r.from_table = $from_table, r.from_column = $from_column,
                              r.to_table = $to_table, r.to_column = $to_column,
                              r.reference_path = $reference_path
                ON MATCH SET r.from_table = $from_table, r.from_column = $from_column,
                             r.to_table = $to_table, r.to_column = $to_column,
                             r.reference_path = $reference_path
                // 设置to_table节点的referenced_path属性
                SET to_table.referenced_path = $reference_path
                // 使用WITH语句进行过渡，将to_table传递到下一个语句块
                WITH to_table
                MATCH (to_table)-[:HAS_COLUMN]->(to_column_node:Column {name: $to_column})
                SET to_column_node.referenced_by = coalesce(to_column_node.referenced_by, []) + [$from_table + '.' + $from_column]
            """, from_table=from_table, from_column=from_column, to_table=to_table, to_column=to_column,
                        reference_path=reference_path)

    def _get_column_samples_and_attributes(self, table_name, column_name, data_type):
        """
        随机抽样获取列的数据样本，并计算附加属性（范围或类别等多种属性），
        为所有类型的列节点添加数据条数属性，对于非id主键的数值型数据添加平均数等相关属性，
        新增根据数据库设计判断列是否为主键或外键并统一添加相应属性到key_type的功能。

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
                samples = random.sample(values, min(len(values), 5))

                # 添加所有类型通用的属性：数据条数
                additional_attributes['data_count'] = len(values) if values else 0

                # 查询列是否为主键
                is_primary_key = self._is_primary_key(table_name, column_name)
                # 查询列是否为外键
                is_foreign_key = self._is_foreign_key(table_name, column_name)

                # 数值型列（INTEGER、REAL）相关属性
                if data_type.upper() in ["INTEGER", "REAL"]:
                    additional_attributes['numeric_range'] = [min(values), max(values)] if values else None
                    # additional_attributes['numeric_distribution_type'] = self._get_distribution_type(values)
                    additional_attributes['numeric_mode'] = self._get_mode(values)
                    additional_attributes['numeric_null_ratio'] = len([v for v in values if v is None]) / len(
                        rows) if rows else 0
                    additional_attributes['numeric_completeness'] = (len(values) / len(rows)) if rows else 0
                    # 添加平均数属性
                    if values:
                        additional_attributes['numeric_mean'] = np.mean(values)
                    else:
                        additional_attributes['numeric_mean'] = None

                # 类别型列（可根据实际情况进一步明确具体类型，这里简单示例）相关属性
                elif data_type.upper() in ["TEXT", "VARCHAR"]:
                    if len(set(values)) <= 6:
                        additional_attributes['category_categories'] = list(set(values))
                    additional_attributes['average_char_length'] = self._get_average_char_length(
                        values) if values else 0
                    # 词频属性处理，转换为JSON字符串
                    word_frequency_dict = self._get_word_frequency(values) if values else {}
                    additional_attributes['word_frequency'] = json.dumps(word_frequency_dict)
                    additional_attributes['null_ratio'] = len([v for v in values if v is None]) / len(
                        rows) if rows else 0
                    additional_attributes['completeness'] = (len(values) / len(rows)) if rows else 0

                # 时间类型列（如DATE、DATETIME等，可根据实际数据库中的时间类型调整）相关属性
                elif data_type.upper() in ["DATE", "DATETIME"]:
                    additional_attributes['time_span'] = self._get_time_span(values) if values else None
                    # additional_attributes['time_periodicity'] = self._get_periodicity(values) if values else ""
                    additional_attributes['time_null_ratio'] = len([v for v in values if v is None]) / len(
                        rows) if rows else 0
                    additional_attributes['time_completeness'] = (len(values) / len(rows)) if rows else 0

                # 根据查询结果添加key_type属性（仅针对主键或外键列）
                key_type = []
                if is_primary_key:
                    key_type.append("primary_key")
                if is_foreign_key:
                    key_type.append("foreign_key")
                if key_type:
                    additional_attributes['key_type'] = key_type

            except Exception as e:
                print(f"Error processing column {column_name} in table {table_name}: {e}")

        return samples, additional_attributes

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

    # def _get_distribution_type(self, values):
    #     """
    #     判断数值型数据的分布类型，支持识别正态分布、均匀分布、离散均匀分布以及顺序递增（类似自增ID）等常见类型，
    #     并针对text2sql任务定制合适的名称用于区分，方便后续使用（示例，可根据实际情况进一步完善）。
    #
    #     :param values: 数值列表
    #     :return: 分布类型字符串，如"normal"（正态分布）、"uniform"（均匀分布）、"discrete_uniform"（离散均匀分布）、"sequential"（顺序递增）等
    #     """
    #     if len(values) < 10:
    #         return ""
    #
    #     try:
    #         # 尝试将输入的数值列表转换为numpy数组，方便后续计算
    #         values_np = np.array(values)
    #
    #         # 判断是否接近均匀分布
    #         range_value = max(values_np) - min(values_np)
    #         if range_value == len(values_np) - 1:
    #             return "uniform"
    #
    #         # 判断是否接近离散均匀分布（假设数据为整数且等间隔）
    #         sorted_values = np.sort(values_np)
    #         diff = np.diff(sorted_values)
    #         if np.all(diff == diff[0]) and len(set(sorted_values)) == len(values_np):
    #             return "discrete_uniform"
    #
    #         # 判断是否为顺序递增的数据（类似自增ID）
    #         if np.all(np.diff(sorted_values) == 1) and len(set(values_np)) == len(values_np):
    #             return "sequential"
    #
    #         # 使用Kolmogorov-Smirnov检验来初步判断是否接近正态分布
    #         _, p_value = kstest(values_np, 'norm')
    #         if p_value > 0.05:
    #             # 可以进一步结合均值、标准差以及可视化（如绘制直方图与正态分布曲线对比等，这里暂不详细实现可视化部分）来辅助判断
    #             mean = np.mean(values_np)
    #             std = np.std(values_np)
    #             if (mean - 3 * std) < min(values_np) and max(values_np) < (mean + 3 * std):
    #                 return "normal"
    #
    #     except Exception as e:
    #         print(f"Error in determining distribution type: {e}")
    #
    #     return "无法识别到分布模式"

    from collections import Counter

    def _get_mode(self, values):
        """
        获取数值型或类别型数据的众数，全面考虑数据库数据中可能出现的多种情况，准确返回众数结果（支持返回多个众数情况）。

        :param values: 数据列表
        :return: 众数列表，如果不存在众数则返回空列表
        """
        if not values:
            return []

        # 使用Counter统计每个元素出现的次数
        count_dict = Counter(values)
        max_count = max(count_dict.values())
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

    def _get_word_frequency(self, values):
        """
        统计文本型数据的词频，仅展示出现频率较高的部分词汇，并按频率从高到低排序展示。

        :param values: 文本数据列表
        :return: 词频字典，格式为{"word": frequency}，包含高频词且按频率排序
        """
        if not values:
            return {}
        all_words = " ".join(values).split()
        word_count_dict = Counter(all_words)
        # 设置一个频率阈值，只保留高于此阈值的词频信息，这里示例设为3次及以上
        min_frequency = 3
        filtered_word_count_dict = {word: count for word, count in word_count_dict.items() if count >= min_frequency}
        # 按照词频从高到低对字典进行排序，返回一个有序字典（在Python 3.7+中字典默认有序，这里使用OrderedDict确保兼容性）
        sorted_word_count_dict = dict(
            sorted(filtered_word_count_dict.items(), key=operator.itemgetter(1), reverse=True))
        return sorted_word_count_dict

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

    # def _get_periodicity(self, values):
    #     """
    #     简单判断时间类型数据的周期规律（示例，可进一步完善），兼容多种日期时间格式的数据。
    #
    #     :param values: 时间数据列表
    #     """
    #     if len(values) < 10:
    #         return ""
    #     datetime_values = [convert_date_string(v) for v in values if convert_date_string(v) is not None]
    #     if datetime_values:
    #         return "monthly" if all((v.month - datetime_values[0].month) % 12 == 0 for v in datetime_values[1:]) else ""
    #     return ""


if __name__ == "__main__":
    # Neo4j数据库连接配置
    neo4j_uri = "bolt://localhost:7687"  # 根据实际情况修改
    neo4j_user = "neo4j"  # 根据实际情况修改
    neo4j_password = "12345678"  # 根据实际情况修改
    database_file = "../data/bird/books/books.sqlite"
    # database_file = "E:/spider/database/soccer_1/soccer_1.sqlite"
    # database_file = "../data/e_commerce.sqlite"

    parser = SchemaParser(neo4j_uri, neo4j_user, neo4j_password, database_file)
    schema = parser.parse_and_store_schema()
    parser.close_connections()
    print(schema)
