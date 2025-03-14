def align_case(tables, columns, joins, schema):
    """
    对齐 SQL 解析出的表、列以及 join 条件中的表名和列名，
    使其大小写与数据库 schema 中的名称一致。

    :param tables: set(tuple(str, str))  例如 {('book', 'T1'), ('publisher', 'T2')}
    :param columns: set(tuple(str, str))  例如 {('book', 'title'), ('publisher', 'publisher_name'), ...}
    :param joins: list(dict)  例如 [{'join_type': 'INNER', 'on': 'book.publisher_id = publisher.publisher_id'}]
    :param schema: dict  数据库模式，如
         {
             'publisher': ['publisher_id', 'publisher_name'],
             'book': ['book_id', 'title', 'isbn13', 'language_id', 'num_pages', 'publication_date', 'publisher_id'],
             ...
         }
    :return: (aligned_tables, aligned_columns, aligned_joins)
    """

    # 构建表名映射：小写表名 -> 正确大小写表名
    table_name_map = {tbl.lower(): tbl for tbl in schema}

    # 构建列名映射： (小写表名, 小写列名) -> 正确大小写列名
    column_name_map = {
        (tbl.lower(), col.lower()): col
        for tbl, cols in schema.items()
        for col in cols
    }

    # 1. 对齐表名（只对表名部分，不变动别名）
    aligned_tables = {(table_name_map.get(tbl.lower(), tbl), alias) for tbl, alias in tables}

    # 2. 对齐列名（同时替换表名和列名，确保 (表,列) 信息正确）
    aligned_columns = {
        (table_name_map.get(tbl.lower(), tbl), column_name_map.get((tbl.lower(), col.lower()), col))
        for tbl, col in columns
    }

    # 3. 对齐 join 条件中的表名和列名
    def align_join_condition(condition):
        # 假设 condition 总是标准格式 "table.column = table.column"
        # 先按 "=" 拆分为左右两侧，再分别处理
        parts = condition.split('=')
        aligned_parts = []
        for part in parts:
            part = part.strip()
            if '.' in part:
                table_part, col_part = part.split('.', 1)
                correct_table = table_name_map.get(table_part.lower(), table_part)
                correct_col = column_name_map.get((table_part.lower(), col_part.lower()), col_part)
                aligned_parts.append(f"{correct_table}.{correct_col}")
            else:
                aligned_parts.append(part)
        return " = ".join(aligned_parts)

    aligned_joins = []
    for j in joins:
        aligned_on = align_join_condition(j["on"])
        aligned_joins.append({
            "join_type": j["join_type"],
            "on": aligned_on
        })

    return aligned_tables, aligned_columns, aligned_joins

if __name__ == '__main__':

    tables = {("BOok", "T1"), ("PUBlisher", "T2")}
    columns = {("BOok", "title"), ("publisher", "publisher_name"), ("boOK", "publisher_id"), ("publisher", "publisher_id")}
    joins = [{"join_type": "INNER", "on": "BOOK.publisher_id = publisher.Publisher_id"}]

    schema = {
        "address_status": ["status_id", "address_status"],
        "author": ["author_id", "author_name"],
        "book_language": ["language_id", "language_code", "language_name"],
        "country": ["country_id", "country_name"],
        "address": ["address_id", "street_number", "street_name", "city", "country_id"],
        "customer": ["customer_id", "first_name", "last_name", "email"],
        "customer_address": ["customer_id", "address_id", "status_id"],
        "order_status": ["status_id", "status_value"],
        "publisher": ["publisher_id", "publisher_name"],
        "book": ["book_id", "title", "isbn13", "language_id", "num_pages", "publication_date", "publisher_id"],
        "book_author": ["book_id", "author_id"],
        "shipping_method": ["method_id", "method_name", "cost"],
        "cust_order": ["order_id", "order_date", "customer_id", "shipping_method_id", "dest_address_id"],
        "order_history": ["history_id", "order_id", "status_id", "status_date"],
        "order_line": ["line_id", "order_id", "book_id", "price"]
    }

    aligned_tables, aligned_columns, aligned_joins = align_case(tables, columns, joins, schema)

    print("Aligned Tables:", aligned_tables)
    print("Aligned Columns:", aligned_columns)
    print("Aligned Joins:", aligned_joins)
