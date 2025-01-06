import sqlglot
from sqlglot.expressions import Table, Column, Join, Where


# 解析SQL查询，返回解析后的表达式对象
def parse_sql(sql):
    return sqlglot.parse_one(sql)


# 从解析后的表达式中提取表信息，返回表名与别名的映射字典以及表定义集合
def extract_table_info(expression):
    alias_to_table = {}
    tables = set()
    for table in expression.find_all(Table):
        table_name = table.name
        alias = None
        if "alias" in table.args:
            alias_node = table.args.get("alias")
            if alias_node and hasattr(alias_node, "this"):
                alias = str(alias_node.this)
        if alias:
            alias_to_table[alias] = table_name
        tables.add((table_name, str(alias) if alias else None))

    unique_tables = set()
    for table, alias in tables:
        if alias is None and table in alias_to_table.values():
            continue
        unique_tables.add((table, alias))
    return alias_to_table, unique_tables


# 从解析后的表达式中提取列信息，基于表名与别名的映射字典，返回列信息集合
def extract_column_info(expression, alias_to_table):
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


# 从解析后的表达式中提取JOIN关系信息，基于表名与别名的映射字典，返回JOIN关系列表
def extract_join_relationships(expression, alias_to_table):
    joins = []
    for join in expression.find_all(Join):
        left_table = alias_to_table.get(join.this.name, join.this.name)
        right_table_expr = join.args.get("this")
        right_table = alias_to_table.get(right_table_expr.name, right_table_expr.name)
        on_condition = join.args.get("on")
        joins.append({
            "left_table": left_table,
            "right_table": right_table,
            "on": format_condition(on_condition) if on_condition else None
        })
    return joins


# 辅助函数，用于格式化JOIN中的条件，使其可读性更好
def format_condition(condition):
    if isinstance(condition, sqlglot.expressions.Expression):
        return str(condition)
    return condition


# 从解析后的表达式中提取WHERE条件信息，返回WHERE条件列表
def extract_where_conditions(expression):
    conditions = []
    where_clause = expression.find(Where)
    if where_clause:
        conditions.append(format_condition(where_clause.this))
    return conditions


# 主函数，整合各部分信息提取功能，返回表和列信息以及关系信息
def extract_entities_and_relationships(sql):
    expression = parse_sql(sql)
    alias_to_table, tables = extract_table_info(expression)
    columns = extract_column_info(expression, alias_to_table)
    joins = extract_join_relationships(expression, alias_to_table)
    conditions = extract_where_conditions(expression)

    entities = {"tables": tables, "columns": columns}
    relationships = {"joins": joins, "conditions": conditions}

    return entities, relationships


def print_entities_by_table(entities):
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


# 示例 SQL 查询
sql = """
SELECT DISTINCT T3.language_name, T2.title 
FROM order_line AS T1 
INNER JOIN book AS T2 ON T1.book_id = T2.book_id 
INNER JOIN book_language AS T3 ON T3.language_id = T2.language_id 
WHERE T1.price * 100 < (SELECT AVG(price) FROM order_line) * 20
"""

entities, relationships = extract_entities_and_relationships(sql)
print(sql)
print("Entities (Tables and Columns):")
print(entities)
print("\nRelationships (Joins and Conditions):")
print(relationships)
print_entities_by_table(entities)