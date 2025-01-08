import sqlglot
from sqlglot.expressions import Table, Column, Join, Where
from neo4j import GraphDatabase


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
            if alias!= table_name:  # 只有当别名和表名不同的时候，才记录别名与表名的映射关系
                alias_to_table[alias] = table_name
            tables.add((table_name, alias))

        unique_tables = set()
        for table, alias in tables:
            if alias == table_name:  # 如果别名和表名相同，说明是没有额外别名的表，直接添加到unique_tables
                unique_tables.add((table, alias))
            elif alias is None and table in alias_to_table.values():
                continue
            else:
                unique_tables.add((table, alias))
        return alias_to_table, unique_tables

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
        参数:
            expression (sqlglot.Expression): 解析后的SQL表达式对象。
            alias_to_table (dict): 表名与别名的映射字典。
        返回:
            list: 包含JOIN关系信息字典的列表，每个字典包含左表、右表和连接条件等信息。
        """
        joins = []
        for join in expression.find_all(Join):
            left_table = alias_to_table.get(join.this.name, join.this.name)
            right_table_expr = join.args.get("this")
            right_table = alias_to_table.get(right_table_expr.name, right_table_expr.name)
            on_condition = join.args.get("on")
            joins.append({
                "left_table": left_table,
                "right_table": right_table,
                "on": self.format_condition(on_condition) if on_condition else None
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
        参数:
            expression (sqlglot.Expression): 解析后的SQL表达式对象。
        返回:
            list: 包含WHERE条件字符串的列表。
        """
        conditions = []
        where_clause = expression.find(Where)
        if where_clause:
            conditions.append(self.format_condition(where_clause.this))
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
        参数:
            sql (str): 要解析和展示信息的SQL语句字符串。
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
        cypher_query = self.sql2subgraph(entities)
        # self.validate_cypher_query(cypher_query)  # 验证Cypher查询语句，仅做测试，不在正式版本中使用
        print(cypher_query)

    def sql2subgraph(self, entities):
        """
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

    def validate_cypher_query(self, cypher_query):
        """
        验证Cypher查询语句是否可以在Neo4j中执行，输出相应的调试信息。
        参数:
            cypher_query (str): 要验证的Cypher查询语句字符串。
        """
        try:
            with self.neo4j_driver.session() as session:
                session.run(cypher_query)
            print("Cypher查询语句验证通过，可以在Neo4j中正常执行。")
        except Exception as e:
            print(f"Cypher查询语句验证失败，无法在Neo4j中执行，错误信息如下：\n{e}")




if __name__ == '__main__':
    # Neo4j数据库连接配置
    neo4j_uri = "bolt://localhost:7687"  # 根据实际情况修改
    neo4j_user = "neo4j"  # 根据实际情况修改
    neo4j_password = "12345678"  # 根据实际情况修改

    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
    try:
        # 示例 SQL 查询
        sql = """
        SELECT DISTINCT T3.language_name, T2.title 
        FROM order_line AS T1 
        INNER JOIN book AS T2 ON T1.book_id = T2.book_id 
        INNER JOIN book_language AS T3 ON T3.language_id = T2.language_id 
        WHERE T1.price * 100 < (SELECT AVG(price) FROM order_line) * 20
        """
        tool = SqlParserTool(driver)
        entities, relationships = tool.extract_entities_and_relationships(sql)
        cypher_query = tool.sql2subgraph(entities)
        tool.parse_and_display(sql)
    finally:
        tool.close_neo4j_connection()
        driver.close()