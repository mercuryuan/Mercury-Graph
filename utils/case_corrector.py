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

    # 1. 过滤掉 schema 中不存在的表，并对齐大小写
    aligned_tables = {
        (table_name_map[tbl.lower()], alias)
        for tbl, alias in tables
        if tbl and tbl.lower() in table_name_map  # 确保 tbl 不是 None 且在 schema 中
    }

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
                table_part = table_part.strip(" '\"")
                col_part = col_part.strip(" '\"")
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
    # tables = {("BOok", "T1"), ("PUBlisher", "T2")}
    # columns = {("BOok", "title"), ("publisher", "publisher_name"), ("boOK", "publisher_id"),
    #            ("publisher", "publisher_id")}
    # joins = [{"join_type": "INNER", "on": "BOOK.publisher_id = publisher.Publisher_id"}]
    #
    # schema = {
    #     "address_status": ["status_id", "address_status"],
    #     "author": ["author_id", "author_name"],
    #     "book_language": ["language_id", "language_code", "language_name"],
    #     "country": ["country_id", "country_name"],
    #     "address": ["address_id", "street_number", "street_name", "city", "country_id"],
    #     "customer": ["customer_id", "first_name", "last_name", "email"],
    #     "customer_address": ["customer_id", "address_id", "status_id"],
    #     "order_status": ["status_id", "status_value"],
    #     "publisher": ["publisher_id", "publisher_name"],
    #     "book": ["book_id", "title", "isbn13", "language_id", "num_pages", "publication_date", "publisher_id"],
    #     "book_author": ["book_id", "author_id"],
    #     "shipping_method": ["method_id", "method_name", "cost"],
    #     "cust_order": ["order_id", "order_date", "customer_id", "shipping_method_id", "dest_address_id"],
    #     "order_history": ["history_id", "order_id", "status_id", "status_date"],
    #     "order_line": ["line_id", "order_id", "book_id", "price"]
    # }
    #
    # aligned_tables, aligned_columns, aligned_joins, modified = align_case(tables, columns, joins, schema)

    # 实际调用
    from sql_parser import SqlParserTool
    from schema_extractor import SQLiteSchemaExtractor
    dataset_name = "bird"
    db_name = "superstore"
    tool  = SqlParserTool(dataset_name, db_name,False)
    sql = """SELECT CAST(SUM(CASE  WHEN T2.Discount = 0 THEN 1 ELSE 0 END) AS REAL) * 100 / COUNT(*) FROM people AS T1 INNER JOIN central_superstore AS T2 ON T1.`Customer ID` = T2.`Customer ID` WHERE T2.Region = 'Central' AND T1.State = 'Indiana'
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
    print(columns)
    print(joins)
    print(schema)

    # 是否进行表名和列名的修正
    aligned_tables, aligned_columns, aligned_joins, modified = align_case(tables, columns, joins, schema)
    print(modified)
    print(aligned_tables)
    print(aligned_columns)
    print(aligned_joins)


    # print("Aligned Tables:", aligned_tables)
    # print("Aligned Columns:", aligned_columns)
    # print("Aligned Joins:", aligned_joins)
    # print("是否经历了修改:", modified)
