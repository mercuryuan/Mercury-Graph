def align_case(tables, columns, joins, schema):
    """
    对齐 SQL 解析出的表、列以及 join 条件中的表名和列名，
    使其大小写与数据库 schema 中的名称一致，同时返回一个标识是否进行了修改的布尔值。

    :param tables: set(tuple(str, str))
                   例如 {('book', 'T1'), ('publisher', 'T2')}
    :param columns: set(tuple(str, str))
                   例如 {('book', 'title'), ('publisher', 'publisher_name'), ...}
    :param joins: list(dict)
                   例如 [{'join_type': 'INNER', 'on': 'book.publisher_id = publisher.publisher_id'}]
    :param schema: dict  数据库模式，如
         {
             'publisher': ['publisher_id', 'publisher_name'],
             'book': ['book_id', 'title', 'isbn13', 'language_id', 'num_pages', 'publication_date', 'publisher_id'],
             ...
         }
    :return: (aligned_tables, aligned_columns, aligned_joins, modified)
             aligned_tables: 对齐后的表集合
             aligned_columns: 对齐后的列集合
             aligned_joins: 对齐后的 join 关系列表
             modified: 布尔值，True 表示至少有一处进行了大小写的修改，False 表示无修改。
    """

    # 构建表名映射：小写表名 -> 正确大小写表名
    table_name_map = {tbl.lower(): tbl for tbl in schema}

    # 构建列名映射： (小写表名, 小写列名) -> 正确大小写列名
    column_name_map = {
        (tbl.lower(), col.lower()): col
        for tbl, cols in schema.items()
        for col in cols
    }

    # 1. 过滤掉 schema 中不存在的表，并对齐大小写，同时去除无别名的原名表
    table_alias_map = {}
    for tbl, alias in tables:
        correct_tbl = table_name_map.get(tbl.lower())
        if correct_tbl:
            if alias != correct_tbl:
                table_alias_map[correct_tbl] = alias  # 记录别名
            elif correct_tbl not in table_alias_map:  # 只有当没有别名时才添加原名
                table_alias_map[correct_tbl] = correct_tbl

    aligned_tables = {(tbl, alias) for tbl, alias in table_alias_map.items()}

    # 2. 过滤掉 schema 中不存在的列，并对齐大小写
    aligned_columns = {
        (table_name_map[tbl.lower()], column_name_map[(tbl.lower(), col.lower())])
        for tbl, col in columns
        if tbl and col and (tbl.lower(), col.lower()) in column_name_map  # 确保表和列都存在
    }

    # 3. 对齐 join 条件中的表名和列名
    def align_join_condition(condition):
        parts = condition.split('=')
        aligned_parts = []
        for part in parts:
            part = part.strip()
            if '.' in part:
                table_part, col_part = part.split('.', 1)
                table_part = table_part.strip(" '")
                col_part = col_part.strip(" '")
                correct_table = table_name_map.get(table_part.lower())
                correct_col = column_name_map.get((table_part.lower(), col_part.lower()))
                if correct_table and correct_col:
                    aligned_parts.append(f"{correct_table}.{correct_col}")
                else:
                    return None  # 如果 join 语句有错误的表或列，则丢弃
            else:
                aligned_parts.append(part)
        return " = ".join(aligned_parts)

    aligned_joins = []
    for j in joins:
        aligned_on = align_join_condition(j["on"])
        if aligned_on:  # 只有当 join 语句有效时才加入
            aligned_joins.append({"join_type": j["join_type"], "on": aligned_on})

    # 4. 判断是否有修改
    modified = (aligned_tables != tables) or (aligned_columns != columns) or (aligned_joins != joins)

    return aligned_tables, aligned_columns, aligned_joins, modified


if __name__ == '__main__':
    # 实际调用
    from sql_parser import SqlParserTool
    from schema_extractor import SQLiteSchemaExtractor

    dataset_name = "spider"
    db_name = "tracking_grants_for_research"
    tool = SqlParserTool(dataset_name, db_name, False)
    sql = """SELECT T1.grant_amount FROM Grants AS T1 JOIN Documents AS T2 ON T1.grant_id  =  T2.grant_id WHERE T2.sent_date  <  '1986-08-26 20:49:27' INTERSECT SELECT grant_amount FROM grants WHERE grant_end_date  >  '1989-03-16 18:27:16'
"""
    entities, relationships = tool.extract_entities_and_relationships(sql)
    # 提取表和列信息
    tables = entities['tables']
    columns = entities['columns']
    joins = relationships['joins']
    # 数据库模式获取
    schema_extractor = SQLiteSchemaExtractor(dataset_name)
    schema = schema_extractor.extract_schema(db_name)

    print(tables)

    # 是否进行表名和列名的修正
    aligned_tables, aligned_columns, aligned_joins, modified = align_case(tables, columns, joins, schema)
    print(modified)
    print(aligned_tables)