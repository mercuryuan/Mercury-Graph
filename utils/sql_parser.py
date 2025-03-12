import sqlglot
from neo4j.graph import Relationship, Node
from sqlglot.expressions import Table, Column, Join, Where
from neo4j import GraphDatabase

from src.neo4j_connector import get_driver


class SqlParserTool:
    """
    SqlParserTool类用于解析SQL语句，并提取其中的表、列、连接关系等相关信息，同时提供了展示这些信息的功能。
    """

    def __init__(self, neo4j_driver):
        """
        初始化SqlParserTool类，传入已建立的Neo4j数据库连接对象。

        参数:
            neo4j_driver (GraphDatabase.driver): Neo4j数据库的驱动对象。
        """
        self.neo4j_driver = neo4j_driver

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

    def print_entities_by_table(self, entities):
        """
        将提取到的实体信息按照表为单位进行格式化输出，展示每个表涉及的列信息。
        参数:
            entities (dict): 包含表和列信息的字典，格式如{"tables": [...], "columns": [...]}。
        """
        table_entities = {}
        for table_info in entities["tables"]:
            table_name = table_info[0]
            table_entities[table_name] = []

        for column_info in entities["columns"]:
            table_name = column_info[0]
            if table_name in table_entities:
                table_entities[table_name].append(column_info[1])

        print("涉及的数据库实体：")
        count = 1
        for table_name, columns in table_entities.items():
            print(f"{count}.表 {table_name}")
            for column in columns:
                print(f" - {column}")
            count += 1

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
        self.print_entities_by_table(entities)
        print("\n对应子图查询语句：")
        cypher_query = self.sql2subgraph(entities, relationships)
        print(cypher_query)
        print()
        self.validate_cypher_query(cypher_query)  # 验证Cypher查询语句，仅做测试，不在正式版本中使用

    def sql2subgraph_simple_version(self, entities):
        """
        简单通过entities生成子图查询语句
        效率高一点
        根据 SQL 解析的数据库实体生成对应的 Neo4j 子图查询语句。
        参数：
            entities (dict): 包含表和列的实体信息。
              - tables: Set[Tuple[str, Optional[str]]] 表名和别名。
              - columns: Set[Tuple[str, str]] 列所属表和列名。
        返回：
            str: Neo4j 子图查询语句。
        """
        # 提取表和列信息
        tables = entities['tables']
        columns = entities['columns']

        # 构造表和列的匹配部分
        match_clauses = []
        where_clauses = []

        # 为每个表生成 MATCH 和 WHERE 子句
        for table_name, alias in tables:
            table_alias = alias if alias else table_name  # 优先使用别名，若无别名则使用表名

            # MATCH 子句：匹配表和列
            match_clause = f"(t{table_alias}:Table {{name: '{table_name}'}})-[:HAS_COLUMN]->(c{table_alias}:Column)"
            match_clauses.append(match_clause)

            # WHERE 子句：筛选列名
            table_columns = [col_name for tbl_name, col_name in columns if tbl_name == table_name]
            where_clause = f"c{table_alias}.name IN {table_columns}"
            where_clauses.append(where_clause)

        # 组合 MATCH 和 WHERE 子句
        match_query = "MATCH " + ",\n      ".join(match_clauses)
        where_query = "WHERE " + " AND\n      ".join(where_clauses)

        # RETURN 子句：返回表和列
        return_query = "RETURN " + ", ".join(
            [f"t{table_alias}, c{table_alias}" for table_name, alias in tables for table_alias in
             [alias if alias else table_name]]
        )

        # 拼接完整的查询语句
        query = f"{match_query}\n{where_query}\n{return_query}"

        return query

    def sql2subgraph(self, entities, relationships):
        """
    将 SQL 查询解析的数据库实体和关系信息转化为 Neo4j 子图查询语句。

    此函数主要完成以下任务：
    1. 将数据库的表和列建模为图数据库的节点和关系。
    2. 使用 `HAS_COLUMN` 关系描述表和其列之间的从属关系。
    3. 使用 `FOREIGN_KEY` 关系描述表与表之间的外键关联。
    4. 自动为关系（从属关系和外键关系）命名唯一的别名，并在查询语句中返回所有节点和关系。

    参数：
        entities (dict): 包含表和列信息的实体描述。
          - tables: Set[Tuple[str, Optional[str]]]
            表信息集合，每个元素是一个元组，包含表名及其可选的别名。
          - columns: Set[Tuple[str, str]]
            列信息集合，每个元素是一个元组，表示列所属的表和列名。
        relationships (dict): 包含表间关系和查询条件的描述。
          - joins: List[Dict[str, str]]
            JOIN 关系的列表，每个元素是一个字典，描述表之间的连接条件。
          - conditions: List[str]
            条件列表，表示 SQL 查询中的筛选条件（未直接用于图查询）。

    返回：
        str: 生成的 Neo4j 子图查询语句，包括 MATCH 和 RETURN 子句。
          - MATCH 子句：定义了图数据库中需要匹配的节点和关系，包括表与列的从属关系以及表与表之间的外键关系。
          - RETURN 子句：返回所有表节点、列节点和关系，按照表节点、列节点、关系的顺序排列。

    实现细节：
    1. 表节点处理：
       - 每个表生成一个 `Table` 类型的节点，若有别名则优先使用别名作为标识。
       - 为每个表分配一个唯一的别名，并在 RETURN 子句中加入对应的表节点。
    2. 列节点处理：
       - 根据列的所属表生成 `Column` 类型的节点。
       - 使用 `HAS_COLUMN` 关系连接表和列，关系别名以 `r` 开头，按顺序递增。
       - 每个表的列节点编号独立递增，以避免重复命名或混淆。
    3. 外键关系处理：
       - 根据 JOIN 关系描述表之间的外键关联，生成 `FOREIGN_KEY` 类型的关系。
       - 关系别名以 `f` 开头，按顺序递增。
    4. 返回顺序规范：
       - RETURN 子句按照表节点、列节点、从属关系、外键关系的顺序输出，确保结构清晰，便于调试和理解。

    示例：
        输入：
            entities = {
                'tables': {('book', None), ('author', 'a')},
                'columns': {('book', 'book_id'), ('author', 'author_id')}
            }
            relationships = {
                'joins': [{'on': 'book.author_id = author.author_id'}],
                'conditions': []
            }
        输出：
            MATCH (tbook:Table {name: 'book'}),
                  (ta:Table {name: 'author'}),
                  (tbook)-[r1:HAS_COLUMN]->(cbook_1:Column {name: 'book_id'}),
                  (ta)-[r2:HAS_COLUMN]->(ca_1:Column {name: 'author_id'}),
                  (tbook)-[f1:FOREIGN_KEY]-(ta)
            RETURN tbook, ta, cbook_1, ca_1, r1, r2, f1
    """
        # 提取表和列信息
        tables = entities['tables']
        columns = entities['columns']
        joins = relationships['joins']

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
        验证Cypher查询语句是否可以在Neo4j中执行，输出相应的调试信息。
        参数:
            cypher_query (str): 要验证的Cypher查询语句字符串。
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
                        if isinstance(value, Node):  # 判断是否为节点
                            node_count += 1
                            labels = value.labels
                            if 'Table' in labels:
                                table_count += 1
                            if 'Column' in labels:
                                column_count += 1
                        elif isinstance(value, Relationship):  # 判断是否为关系
                            relationship_count += 1
                            if value.type == 'HAS_COLUMN':
                                column_relationship_count += 1
                            elif value.type == 'FOREIGN_KEY':
                                foreign_key_relationship_count += 1
                # 检查实体总数是否为 0
                if node_count == 0 or relationship_count == 0:
                    raise ValueError("查询到的实体总数为 0，请检查数据是否正确导入。")
                # 输出查询验证结果
                print(
                    f"Cypher查询验证结果：验证通过 | 总节点数: {node_count} | 总关系数: {relationship_count} | 表节点数: {table_count} | 列节点数: {column_count} | HAS_COLUMN数: {column_relationship_count} | FOREIGN_KEY数: {foreign_key_relationship_count}")
        except ValueError as ve:
            print(f"Cypher查询验证失败，错误信息：{ve}")
            raise  # 关键修改：重新抛出异常！
        except Exception as e:
            print(f"Cypher查询验证失败，错误信息：{e}")
            raise  # 关键修改：重新抛出异常！


if __name__ == '__main__':
    # Neo4j数据库连接配置
    driver = get_driver()
    try:
        # 示例 SQL 查询
        sql = """
        SELECT DISTINCT T3.language_name, T2.title 
        FROM order_line AS T1 
        INNER JOIN book AS T2 ON T1.book_id = T2.book_id 
        INNER JOIN book_language AS T3 ON T3.language_id = T2.language_id 
        WHERE T1.price * 100 < (SELECT AVG(price) FROM order_line) * 20
        """
        # 实例化 SqlParserTool 类
        tool = SqlParserTool(driver)
        # 解析并展示结果
        tool.parse_and_display(sql)

        # 仅返回子图查询的cypher语句的用法
        # e,r = tool.extract_entities_and_relationships(sql)
        # print(tool.sql2subgraph(e,r))

    finally:
        driver.close()
