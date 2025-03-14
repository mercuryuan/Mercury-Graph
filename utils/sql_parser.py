import os.path
import time

import sqlglot
from neo4j.graph import Relationship, Node
from sqlglot.expressions import Table, Column, Join, Where
from src.neo4j_connector import get_driver
from utils.SchemaExtractor import SQLiteSchemaExtractor
from utils.case_corrector import align_case
import config


class SqlParserTool:
    """
    SqlParserTool类用于解析SQL语句，并提取其中的表、列、连接关系等相关信息，同时提供了展示这些信息的功能。
    """

    def __init__(self, dataset_name, db_name):
        """
        初始化SqlParserTool类，传入已建立的Neo4j数据库连接对象。

        参数:
            neo4j_driver (GraphDatabase.driver): Neo4j数据库的驱动对象。
        """
        self.neo4j_driver = get_driver()
        self.dataset_name = dataset_name
        self.db_name = db_name
        extractor = SQLiteSchemaExtractor(dataset_name)
        self.schema = extractor.extract_schema(db_name)
        self.log_file = os.path.join(config.PROJECT_ROOT, "sql_parser", f"{dataset_name}_analysis/{db_name}.log")

    def close_neo4j_connection(self):
        """
        关闭与Neo4j数据库的连接。
        """
        self.neo4j_driver.close()

    def parse_sql(self, sql):
        """
        解析SQL查询，返回解析后的表达式对象。
        参数:
            sql (str): 要解析的SQL语句字符串。
        返回:
            sqlglot.Expression: 解析后的SQL表达式对象。
        """
        # sql处理双引号为单引号
        sql = sql.replace('"', "'")
        return sqlglot.parse_one(sql)

    def extract_table_info(self, expression):
        """
        从解析后的表达式中提取表信息，返回表名与别名的映射字典以及表定义集合。
        确保unique_tables中每个表记录唯一，遵循有别名则用别名，无别名则用表名自身的原则。
        参数:
            expression (sqlglot.Expression): 解析后的SQL表达式对象。
        返回:
            tuple: 包含表名与别名的映射字典和表定义集合的元组。
        """
        alias_to_table = {}
        tables = set()
        for table in expression.find_all(Table):
            table_name = table.name
            alias = table.alias_or_name  # 直接使用alias_or_name获取别名，如果没有别名则返回表名本身
            if alias != table_name:  # 只有当别名和表名不同的时候，才记录别名与表名的映射关系
                alias_to_table[alias] = table_name
            tables.add((table_name, alias))

        unique_tables = {}
        for table, alias in tables:
            # 如果表还没记录过或者当前记录的是表名（无别名情况）但新出现了别名，则更新记录
            if table not in unique_tables or (unique_tables[table] == table and alias != table):
                if alias is not None:
                    unique_tables[table] = alias
                else:
                    unique_tables[table] = table
        return alias_to_table, set(unique_tables.items())

    def extract_column_info(self, expression, alias_to_table):
        """
        从解析后的表达式中提取列信息，基于表名与别名的映射字典，返回列信息集合。
        参数:
            expression (sqlglot.Expression): 解析后的SQL表达式对象。
            alias_to_table (dict): 表名与别名的映射字典。
        返回:
            set: 包含列信息（表名，列名）元组的集合。
        """
        columns = set()
        for column in expression.find_all(Column):
            table_name = None
            if column.table:
                table_name = alias_to_table.get(column.table, column.table)
            else:
                from_clause = expression.find(sqlglot.expressions.From)
                if from_clause:
                    table_expr = from_clause.this
                    if isinstance(table_expr, Table):
                        table_name = table_expr.name
            column_name = column.name
            columns.add((table_name, column_name))
        return columns

    def extract_join_relationships(self, expression, alias_to_table):
        """
        从解析后的表达式中提取JOIN关系信息，基于表名与别名的映射字典，返回JOIN关系列表。
        重点获取连接类型，并将JOIN关系中的on条件里的别名替换为对应的表名。
        参数:
            expression (sqlglot.Expression): 解析后的SQL表达式对象。
            alias_to_table (dict): 表名与别名的映射字典。
        返回:
            list: 包含JOIN关系信息字典的列表，每个字典包含连接类型、连接条件等信息。
        """
        joins = []
        for join in expression.find_all(Join):
            join_type = join.kind  # 获取连接类型，例如INNER、LEFT等
            on_condition = join.args.get("on")
            if on_condition:
                # 将on条件中的别名替换为表名
                on_condition_str = self.format_condition(on_condition)
                for alias, table_name in alias_to_table.items():
                    on_condition_str = on_condition_str.replace(alias, table_name)
                on_condition = on_condition_str
            joins.append({
                "join_type": join_type,
                "on": on_condition
            })
        return joins

    def format_condition(self, condition):
        """
        辅助函数，用于格式化JOIN中的条件，使其可读性更好。
        参数:
            condition (sqlglot.expressions.Expression 或其他类型): JOIN条件表达式或者其他类型的条件值。
        返回:
            str: 格式化后的条件字符串，如果传入的不是Expression类型则直接返回原条件值。
        """
        if isinstance(condition, sqlglot.expressions.Expression):
            return str(condition)
        return condition

    def extract_where_conditions(self, expression):
        """
        从解析后的表达式中提取WHERE条件信息，返回WHERE条件列表。
        将WHERE条件字符串里的别名都替换为对应的表名。
        参数:
            expression (sqlglot.Expression): 解析后的SQL表达式对象。
        返回:
            list: 包含WHERE条件字符串的列表。
        """
        conditions = []
        where_clause = expression.find(Where)
        if where_clause:
            condition_str = self.format_condition(where_clause.this)
            alias_to_table, _ = self.extract_table_info(expression)
            for alias, table_name in alias_to_table.items():
                condition_str = condition_str.replace(alias, table_name)
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
        expression = self.parse_sql(sql)
        alias_to_table, tables = self.extract_table_info(expression)
        columns = self.extract_column_info(expression, alias_to_table)
        joins = self.extract_join_relationships(expression, alias_to_table)
        conditions = self.extract_where_conditions(expression)

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

    def parse_and_display(self, sql, question=None, db_id=None):
        """
        解析输入的SQL语句，并展示解析后的表、列等相关信息以及它们之间的关系信息。
        同时，根据解析结果生成对应的Neo4j子图查询语句，并对该查询语句进行验证。

        参数:
            sql (str): 要解析和展示信息的SQL语句字符串。
            question (str, optional): 与SQL查询相关的问题描述，默认为None。
            db_id (str, optional): 数据库的ID，默认为None。

        输出:
            1. 打印数据库ID和问题描述（如果提供）。
            2. 打印原始的SQL语句。
            3. 打印解析后的实体信息（表和列）。
            4. 打印解析后的关系信息（连接和条件）。
            5. 按表为单位格式化输出实体信息。
            6. 打印生成的Neo4j子图查询语句。
            7. 验证并输出Cypher查询语句的验证结果。
        """
        entities, relationships = self.extract_entities_and_relationships(sql)
        if question:
            print(f"Database:{db_id}")
        if db_id:
            print(f"Question:{question}")
        print(sql)
        print("\nEntities (Tables and Columns):")
        print(entities)
        print("\nRelationships (Joins and Conditions):")
        print(relationships)
        print()
        formated_entities = self.format_entities_by_table(entities)
        print(formated_entities)
        print("\n对应子图查询语句：")
        cypher_query = self.sql2subgraph(entities, relationships)
        print(cypher_query)
        print()
        self.validate_cypher_query(cypher_query)  # 验证Cypher查询语句

    def sql2subgraph(self, entities, relationships, name_correction=True):
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
        if name_correction:
            tables, columns, joins = align_case(tables, columns, joins, self.schema)

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
            table_column_counters[table_alias] = 1  # 初始化该表的列计数器啊？

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
                    return False

                # 记录成功日志
                message = (f"Cypher查询验证通过✅ | 总节点数: {node_count} | 总关系数: {relationship_count} | "
                           f"表节点数: {table_count} | 列节点数: {column_count} | "
                           f"HAS_COLUMN数: {column_relationship_count} | FOREIGN_KEY数: {foreign_key_relationship_count}")
                self.log(message)
                return True
        except Exception as e:
            message = f"Cypher查询验证失败❌，错误信息：{e}"
            self.log(message)
            return False

    def log(self, message: str, log_file=None):
        """ 记录日志信息到指定文件并打印到控制台 """
        if log_file is None:
            log_file = self.log_file
        # 创建日志文件所在的目录
        log_dir = os.path.dirname(log_file)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_msg = f"[{timestamp}] {message}"
        with open(log_file, "a", encoding="utf-8") as log:
            log.write(log_msg + "\n")
        print(log_msg)



if __name__ == '__main__':
    # 实例化 SqlParserTool 类
    tool = SqlParserTool("bird", "books")
    try:
        # 示例 SQL 查询
        sql = """
        SELECT T2.publisher_name FROM book AS T1 INNER JOIN publisher AS T2 ON T1.publisher_id = T2.publisher_id WHERE T1.title = 'The Illuminati'"""
        # 解析并展示结果
        tool.parse_and_display(sql)

        # 仅返回子图查询的cypher语句的用法
        # e,r = tool.extract_entities_and_relationships(sql)
        # print(tool.sql2subgraph(e,r))

    finally:
        tool.neo4j_driver.close()
