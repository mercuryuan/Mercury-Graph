from utils.sql_parse_tools import SqlParserTool


sql = """
    SELECT T2.publisher_name FROM book AS T1 INNER JOIN publisher AS T2 ON T1.publisher_id = T2.publisher_id GROUP BY T2.publisher_name ORDER BY COUNT(T1.book_id) DESC LIMIT 1
    """


def sql2subgraph(entities):
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


tool = SqlParserTool()
entities, rel = tool.extract_entities_and_relationships(sql)
print(entities)
query = sql2subgraph(entities)
print(query)