import os.path
import re
import time

import sqlglot
from neo4j.graph import Relationship, Node
from sqlglot.expressions import Table, Column, Join, Where
from sqlglot import parse_one, exp
from sqlglot.optimizer import build_scope
from sqlglot.optimizer.qualify import qualify

from src.neo4j_connector import get_driver
from utils.schema_extractor import SQLiteSchemaExtractor
from utils.case_corrector import align_case
import config


class SqlParserTool:
    """
    SqlParserTool类用于解析SQL语句，并提取其中的表、列、连接关系等相关信息，同时提供了展示这些信息的功能。
    """

    def __init__(self, dataset_name, db_name, name_correction=True,dialect = "mysql"):
        """
        初始化SqlParserTool类，传入已建立的Neo4j数据库连接对象。

        参数:
            neo4j_driver (GraphDatabase.driver): Neo4j数据库的驱动对象。
        """
        self.neo4j_driver = get_driver()
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.dialect = dialect
        self.name_correction = name_correction  # 将name_correction作为类属性
        extractor = SQLiteSchemaExtractor(dataset_name)
        self.schema = extractor.extract_schema(db_name)
        if self.name_correction:
            self.log_file = os.path.join(config.PROJECT_ROOT, "sql_parser",
                                         f"{dataset_name}_analysis/{db_name}.log")
        else:
            self.log_file = os.path.join(config.PROJECT_ROOT, "sql_parser",
                                         f"{dataset_name}_analysis_with_correction/{db_name}.log")

    def close_neo4j_connection(self):
        """
        关闭与Neo4j数据库的连接。
        """
        self.neo4j_driver.close()

    from sqlglot import parse_one, exp
    from sqlglot.optimizer.qualify import qualify
    from sqlglot.optimizer.scope import build_scope

    def extract_table_info(self,expression):
        """
        提取 SQL 查询中的表信息和别名映射，确保 unique_tables 记录唯一表信息。
        规则：如果表有别名，则使用别名；如果没有，则使用表名本身。

        参数:
            expression (sqlglot.Expression): 解析后的 SQL AST。

        返回:
            tuple: (别名到表名的映射字典, 仅包含唯一表定义的集合)
        """
        # 进行列限定，确保列名带上表前缀
        qualify(expression)

        # 构建作用域树，提取作用域中的表和别名信息
        scope_tree = build_scope(expression)

        # 提取别名映射
        alias_to_table = {
            alias: source.name
            for scope in scope_tree.traverse()
            for alias, (_, source) in scope.selected_sources.items()
            if isinstance(source, exp.Table)
        }

        # 提取唯一表信息
        unique_tables = set()
        for table in expression.find_all(exp.Table):
            table_name = table.name
            alias = table.alias_or_name
            unique_tables.add((table_name, alias))

        return alias_to_table, unique_tables

    def extract_column_info(self,expression, alias_to_table):
        """
        提取 SQL 查询中的列信息，并基于表别名映射字典进行转换。

        参数:
            expression (sqlglot.Expression): 解析后的 SQL AST。
            alias_to_table (dict): 表名与别名的映射字典。

        返回:
            set: 包含 (表名, 列名) 的元组集合。
        """
        # 确保列名前缀带上表名
        qualify(expression)

        # 解析作用域
        scope_tree = build_scope(expression)

        columns = set()

        for column in expression.find_all(exp.Column):
            table_name = column.table
            column_name = column.name

            # 解析表别名
            table_name = alias_to_table.get(table_name, table_name)

            # 仅记录确定的 (表名, 列名) 组合
            if table_name and column_name:
                columns.add((table_name, column_name))

        return columns

    def extract_join_relationships(self,expression, alias_to_table):
        """
        提取 SQL 查询中的 JOIN 关系，并格式化 ON 条件，去除不必要的反引号。

        参数:
            expression (sqlglot.Expression): 解析后的 SQL AST。
            alias_to_table (dict): 表名与别名的映射字典。

        返回:
            list: 包含 JOIN 关系信息字典的列表，每个字典包含连接类型、连接表、连接条件等信息。
        """
        joins = []

        for join in expression.find_all(exp.Join):
            join_type = join.kind  # INNER, LEFT, RIGHT, FULL 等

            # 获取左表和右表
            left_table = alias_to_table.get(join.this.alias_or_name, join.this.name)
            right_expr = join.args.get("this")
            right_table = alias_to_table.get(right_expr.alias_or_name, right_expr.name) if right_expr else None

            # 处理 ON 条件
            on_condition = join.args.get("on")
            on_condition_str = self.format_condition(on_condition) if on_condition else None

            # 替换 ON 条件中的别名，并去掉反引号
            if on_condition_str:
                for alias, table_name in alias_to_table.items():
                    on_condition_str = re.sub(rf"`?{alias}`?\.", f"{table_name}.", on_condition_str)

            joins.append({
                "join_type": join_type,
                "left_table": left_table,
                "right_table": right_table,
                "on": on_condition_str
            })

        return joins

    def format_condition(self,condition):
        """
        格式化 SQL JOIN 的 ON 条件，使其更具可读性。

        参数:
            condition (sqlglot.Expression 或其他类型): JOIN 条件表达式。

        返回:
            str: 格式化后的条件字符串，如果不是 Expression 类型则直接返回字符串。
        """
        if isinstance(condition, exp.Expression):
            return condition.sql(dialect=self.dialect)  # 这里可以换成你需要的 SQL 方言
        else:
            sql_str = str(condition)

            # 去除所有反引号
        sql_str = re.sub(r"`", "", sql_str)

        return sql_str

    def extract_where_conditions(self,expression, alias_to_table):
        """
        提取 SQL 查询中的 WHERE 条件，并替换别名为表名。

        参数:
            expression (sqlglot.Expression): 解析后的 SQL AST。
            alias_to_table (dict): 表名与别名的映射字典。

        返回:
            list: 包含 WHERE 条件 SQL 字符串的列表。
        """
        conditions = []

        where_clause = expression.find(exp.Where)
        if where_clause:
            condition_str = where_clause.this.sql(dialect="mysql")

            # 替换别名为表名
            for alias, table_name in alias_to_table.items():
                condition_str = condition_str.replace(f"{alias}.", f"{table_name}.")

            conditions.append(condition_str)

        return conditions

    def extract_entities_and_relationships(self, sql):

        """
        主函数，整合各部分信息提取功能，返回表和列信息以及关系信息。
        参数:
            sql (str): 要解析的SQL语句字符串。
        返回:
            tuple: 包含表和列信息的字典以及关系信息的字典的元组。
        """
        # sql处理双引号为单引号
        sql = sql.replace('"', "'")
        expression = sqlglot.parse_one(sql)
        alias_to_table, tables = self.extract_table_info(expression)
        columns = self.extract_column_info(expression, alias_to_table)
        joins = self.extract_join_relationships(expression, alias_to_table)
        conditions = self.extract_where_conditions(expression,alias_to_table)

        entities = {"tables": tables, "columns": columns}
        relationships = {"joins": joins, "conditions": conditions}

        return entities, relationships

    def format_entities_by_table(self, entities):
        """
        将提取到的实体信息按照表为单位进行格式化输出，展示每个表涉及的列信息。
        参数:
            entities (dict): 包含表和列信息的字典，格式如{"tables": [...], "columns": [...]}。
        返回:
            str: 格式化后的实体信息字符串。
        """
        table_entities = {table_info[0]: [] for table_info in entities["tables"]}

        for column_info in entities["columns"]:
            table_name = column_info[0]
            if table_name in table_entities:
                table_entities[table_name].append(column_info[1])

        result = ["涉及的数据库实体："]
        count = 1
        for table_name, columns in table_entities.items():
            result.append(f"{count}. 表 {table_name}")
            result.extend(f" - {column}" for column in columns)
            count += 1

        return "\n".join(result)

    def sql2subgraph(self, entities, relationships):
        """
        将 SQL 查询解析的数据库实体和关系信息转化为 Neo4j 子图查询语句。

        此函数主要完成以下任务：
        1. 将数据库的表和列建模为图数据库的节点和关系。
        2. 使用 `HAS_COLUMN` 关系描述表和其列之间的从属关系。
        3. 使用 `FOREIGN_KEY` 关系描述表与表之间的外键关联。
        4. 自动为关系（从属关系和外键关系）命名唯一的别名，并在查询语句中返回所有节点和关系。
        """
        # 提取表和列信息
        tables = entities['tables']
        columns = entities['columns']
        joins = relationships['joins']
        # 是否进行表名和列名的修正
        if self.name_correction:
            tables, columns, joins, modified = align_case(tables, columns, joins, self.schema)
            if modified:
                print("名称差异修正🐞")
                self.log("名称差异修正🐞")

        match_clauses = []
        return_table_clauses = []
        return_column_clauses = []
        return_relationship_clauses = []
        relationship_clauses = []

        # 为每个表生成 MATCH 子句和列的从属关系
        relationship_counter = 1
        table_alias_map = {}
        table_column_counters = {}  # 为每个表单独维护列计数器

        for table_name, alias in tables:
            table_alias = alias if alias else table_name
            table_alias_map[table_name] = table_alias
            table_column_counters[table_alias] = 1  # 初始化该表的列计数器

            # 表的 MATCH 子句
            match_clauses.append(f"(t{table_alias}:Table {{name: '{table_name}'}})")
            return_table_clauses.append(f"t{table_alias}")

            # 列的 MATCH 子句
            table_columns = [col_name for tbl_name, col_name in columns if tbl_name == table_name]
            for col_name in table_columns:
                column_counter = table_column_counters[table_alias]
                match_clauses.append(
                    f"(t{table_alias})-[r{relationship_counter}:HAS_COLUMN]->(c{table_alias}_{column_counter}:Column {{name: '{col_name}'}})"
                )
                return_column_clauses.append(f"c{table_alias}_{column_counter}")
                return_relationship_clauses.append(f"r{relationship_counter}")
                relationship_counter += 1
                table_column_counters[table_alias] += 1

        # 处理外键关系
        foreign_key_counter = 1
        for join in joins:
            on_condition = join['on']
            left_table, left_column = on_condition.split('=')[0].strip().split('.')
            right_table, right_column = on_condition.split('=')[1].strip().split('.')

            left_alias = table_alias_map[left_table]
            right_alias = table_alias_map[right_table]

            relationship_clauses.append(
                f"(t{left_alias})-[f{foreign_key_counter}:FOREIGN_KEY]-(t{right_alias})"
            )
            return_relationship_clauses.append(f"f{foreign_key_counter}")
            foreign_key_counter += 1

        # 组合 MATCH 子句
        match_query = "MATCH " + ",\n      ".join(match_clauses + relationship_clauses)

        # 组合 RETURN 子句
        return_query = "RETURN " + ", ".join(
            return_table_clauses + return_column_clauses + return_relationship_clauses
        )

        # 拼接完整的查询语句
        query = f"{match_query}\n{return_query}"

        return query

    def validate_cypher_query(self, cypher_query):
        """
        验证Cypher查询语句是否可以在Neo4j中执行，并记录日志。
        参数:
            cypher_query (str): 要验证的Cypher查询语句字符串。
        返回:
            bool: 是否验证通过
        """
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(cypher_query)

                # 初始化统计值
                node_count = 0
                relationship_count = 0
                table_count = 0
                column_count = 0
                column_relationship_count = 0
                foreign_key_relationship_count = 0

                # 统计节点和关系的数量
                for record in result:
                    for value in record.values():
                        if isinstance(value, Node):
                            node_count += 1
                            labels = value.labels
                            if 'Table' in labels:
                                table_count += 1
                            if 'Column' in labels:
                                column_count += 1
                        elif isinstance(value, Relationship):
                            relationship_count += 1
                            if value.type == 'HAS_COLUMN':
                                column_relationship_count += 1
                            elif value.type == 'FOREIGN_KEY':
                                foreign_key_relationship_count += 1

                # 检查查询结果
                if node_count == 0 or relationship_count == 0:
                    message = "Cypher查询验证失败❌：查询到的实体总数为 0，请检查数据是否正确导入。"
                    self.log(message)
                    print(message)
                    return False

                # 记录成功日志
                message = (f"Cypher查询验证通过✅ | 总节点数: {node_count} | 总关系数: {relationship_count} | "
                           f"表节点数: {table_count} | 列节点数: {column_count} | "
                           f"HAS_COLUMN数: {column_relationship_count} | FOREIGN_KEY数: {foreign_key_relationship_count}")
                self.log(message)
                print(message)
                return True
        except Exception as e:
            message = f"Cypher查询验证失败❌，错误信息：{e}"
            self.log(message)
            return False

    def log(self, message: str, log_file=None):
        """ 记录日志信息到指定文件，不再打印到控制台 """
        if log_file is None:
            log_file = self.log_file
        # 创建日志文件所在的目录
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        with open(log_file, "a", encoding="utf-8") as log:
            log.write(message + "\n")

    def display_parsing_result(self, sql, question=None, db_id=None, output_mode="full_output"):
        """
        集中处理解析结果的输出和日志记录，支持三种不同的输出模式。

        参数:
            sql (str): 待解析的 SQL 语句。
            question (str, 可选): 与 SQL 查询相关的问题描述，默认为 None。
            db_id (str, 可选): 数据库的 ID，默认为 None。
            output_mode (str, 可选): 输出模式，支持以下三种：
                - "full_output": 按原来的方式全部输出和记录解析结果。
                - "pass_basic_fail_full": 仅输出和记录 validate_cypher_query 不通过的全量信息，
                                          对于通过的只输出和记录基本信息。
                - "pass_silent_fail_full": 通过的不输出和记录信息，对于不通过的输出和记录全量信息。
        """
        try:
            # 提取 SQL 语句中的实体和关系信息
            entities, relationships = self.extract_entities_and_relationships(sql)

            # 定义函数用于输出和记录基本信息
            def print_and_log_basic_info():
                """
                输出并记录基本信息，包括数据库 ID、问题描述和 SQL 语句。
                """
                if question:
                    print(f"Database: {db_id}")
                if db_id:
                    print(f"Question: {question}")
                print(f"SQL: {sql}\n")

                # 构建基本信息的日志内容
                basic_info_log = ""
                if question:
                    basic_info_log += f"Database: {db_id}\n"
                if db_id:
                    basic_info_log += f"Question: {question}\n"
                basic_info_log += f"SQL: {sql}\n"

                # 调用日志记录函数
                self.log(basic_info_log)

            # 定义函数用于输出和记录全量信息
            def print_and_log_full_info():
                """
                输出并记录全量信息，包括基本信息、实体信息、关系信息、
                格式化的实体信息和子图查询语句。
                """
                # 输出并记录基本信息
                print_and_log_basic_info()

                # 输出实体信息
                print("\nEntities (Tables and Columns):")
                print(entities)
                self.log("Entities (Tables and Columns): " + str(entities))

                # 输出关系信息
                print("\nRelationships (Joins and Conditions):")
                print(relationships)
                self.log("Relationships (Joins and Conditions): " + str(relationships))

                # 输出格式化的实体信息
                formated_entities = self.format_entities_by_table(entities)
                print("\n" + formated_entities)
                self.log(formated_entities)

                # 输出子图查询语句
                print("\n对应子图查询语句：")
                cypher_query = self.sql2subgraph(entities, relationships)
                print(cypher_query)
                self.log("对应子图查询语句：\n" + cypher_query)

            # 生成 Cypher 查询语句
            cypher_query = self.sql2subgraph(entities, relationships)
            # 验证 Cypher 查询语句
            is_valid = self.validate_cypher_query(cypher_query)

            # 根据不同的输出模式进行相应的输出和记录操作
            if output_mode == "full_output":
                # 全量输出模式：输出并记录所有信息
                print_and_log_full_info()
            elif output_mode == "pass_basic_fail_full":
                if is_valid:
                    # 验证通过，只输出和记录基本信息
                    print_and_log_basic_info()
                else:
                    # 验证不通过，输出和记录全量信息
                    print_and_log_full_info()
            elif output_mode == "pass_silent_fail_full":
                if not is_valid:
                    # 验证不通过，输出和记录全量信息
                    print_and_log_full_info()
            return is_valid
        except Exception as e:
            info = question + "\n" + sql + "\n"
            self.log(info)
            print(info)
            message = f"在解析 SQL 语句时发生异常❌: {e}"
            self.log(message)
            print(message)
            raise


if __name__ == '__main__':
    # 实例化 SqlParserTool 类
    tool = SqlParserTool("bird", "books", name_correction=False)
    try:
        # 示例 SQL 查询
        sql = """SELECT T2.weight FROM truck AS T1 INNER JOIN shipment AS T2 ON T1.truck_id = T2.truck_id WHERE make = 'Peterbilt'
        """
        sql = """WITH MatchDetails AS (
            SELECT
                b.name AS titles,
                m.duration AS match_duration,
                w1.name || ' vs ' || w2.name AS matches,
                m.win_type AS win_type,
                l.name AS location,
                e.name AS event,
                ROW_NUMBER() OVER (PARTITION BY b.name ORDER BY m.duration ASC) AS rank
            FROM
                Belts b
            INNER JOIN Matches m ON m.title_id = b.id
            INNER JOIN Wrestlers w1 ON w1.id = m.winner_id
            INNER JOIN Wrestlers w2 ON w2.id = m.loser_id
            INNER JOIN Cards c ON c.id = m.card_id
            INNER JOIN Locations l ON l.id = c.location_id
            INNER JOIN Events e ON e.id = c.event_id
            INNER JOIN Promotions p ON p.id = c.promotion_id
            WHERE
                p.name = 'NXT'
                AND m.duration <> ''
                AND b.name <> ''
                AND b.name NOT IN (
                    SELECT name
                    FROM Belts
                    WHERE name LIKE '%title change%'
                )
        ),
        Rank1 AS (
        SELECT
            titles,
            match_duration,
            matches,
            win_type,
            location,
            event
        FROM
            MatchDetails
        WHERE
            rank = 1
        )
        SELECT
            SUBSTR(matches, 1, INSTR(matches, ' vs ') - 1) AS wrestler1,
            SUBSTR(matches, INSTR(matches, ' vs ') + 4) AS wrestler2
        FROM
        Rank1
        ORDER BY match_duration
        LIMIT 1
        """
        # 解析并展示结果，使用不同的输出模式
        # tool.display_parsing_result(sql, output_mode="full_output")
        tool.display_parsing_result(sql, output_mode="full_output")
        # tool.display_parsing_result(sql, output_mode="pass_silent_fail_full")

    finally:
        tool.close_neo4j_connection()