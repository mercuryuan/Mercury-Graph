import json
import os.path


def generate_numeric_column_schema(column_node):
    properties = column_node['properties']
    column_name = properties['name']
    data_type = properties['data_type']
    prop_type = data_type.upper()

    key_info = []
    if 'key_type' in properties:
        if 'primary_key' in properties['key_type']:
            key_info.append('Primary Key')
        if 'foreign_key' in properties['key_type']:
            key_info.append('Foreign Key')
    key_info_str = ', '.join(key_info)

    samples = properties.get('samples', [])
    examples_str = ', '.join(map(str, samples))

    is_nullable = properties.get('is_nullable', False)
    nullable_str = "Nullable" if is_nullable else "Not Nullable"

    additional_info = []
    if is_nullable:
        data_integrity = properties.get('data_integrity')
        null_count = properties.get('null_count')
        if data_integrity is not None:
            additional_info.append(f"data integrity: {data_integrity}")
            if null_count and null_count != 0:
                additional_info.append(f"null count: {null_count}")
    if 'numeric_range' in properties:
        additional_info.append(f"numeric range: {properties['numeric_range']}")
    if 'referenced_by' in properties:
        additional_info.append(f"referenced by: {', '.join(properties['referenced_by'])}")
    if 'numeric_mean' in properties:
        additional_info.append(f"numeric mean: {properties['numeric_mean']}")
    if 'numeric_mode' in properties:
        additional_info.append(f"numeric mode: {properties['numeric_mode']}")

    additional_info_str = ', '.join(additional_info)

    column_desc = properties.get('column_description')
    schema_str = f"({column_name}:{prop_type}"
    if column_desc:
        schema_str += f", {column_desc}"
    if key_info_str:
        schema_str += f", {key_info_str}"
    schema_str += f", Examples: [{examples_str}]"
    schema_str += f", {nullable_str}"
    if additional_info_str:
        schema_str += f", {additional_info_str}"
    schema_str += ")"

    value_desc = properties.get('value_description')
    return schema_str, value_desc




def generate_text_column_schema(column_node):
    """
    生成文本类型列的 M - Schema
    :param column_node: 列节点信息
    :return: M - Schema 格式的字符串和 value description
    """
    properties = column_node['properties']
    column_name = properties['name']
    data_type = properties['data_type']
    prop_type = data_type.upper()
    column_desc = properties.get('column_description')

    # 基本信息
    schema_str = f"({column_name}:{prop_type}"
    if column_desc:
        schema_str += f", {column_desc}"

    # 键信息
    key_info = []
    if 'key_type' in properties:
        if 'primary_key' in properties['key_type']:
            key_info.append('Primary Key')
        if 'foreign_key' in properties['key_type']:
            key_info.append('Foreign Key')
    key_info_str = ', '.join(key_info)
    if key_info_str:
        schema_str += f", {key_info_str}"

    # 示例值
    samples = properties.get('samples', [])
    examples_str = ', '.join(map(str, samples))
    schema_str += f", Examples: [{examples_str}]"

    # 可空性
    is_nullable = properties.get('is_nullable', False)
    nullable_str = "Nullable" if is_nullable else "Not Nullable"
    schema_str += f", {nullable_str}"

    # 统计信息（当可空时）
    if is_nullable:
        data_integrity = properties.get('data_integrity')
        null_count = properties.get('null_count')
        if data_integrity is not None:
            schema_str += f", data integrity: {data_integrity}"
            if data_integrity != 1.0 and null_count is not None and null_count != 0:
                schema_str += f", null count: {null_count}"

    # 其他统计信息
    additional_info = []
    if 'referenced_to' in properties:
        additional_info.append(f"referenced to: {', '.join(properties['referenced_to'])}")
    if 'word_frequency' in properties:
        word_freq = json.loads(properties['word_frequency'])
        additional_info.append(f"word frequency: {word_freq}")
    if 'average_char_length' in properties:
        additional_info.append(f"average char length: {properties['average_char_length']}")
    if 'category_categories' in properties:
        additional_info.append(f"category categories: {properties['category_categories']}")

    additional_info_str = ', '.join(additional_info)
    if additional_info_str:
        schema_str += f", {additional_info_str}"

    schema_str += ")"

    value_desc = properties.get('value_description')
    return schema_str, value_desc


def generate_time_column_schema(column_node):
    """
    生成时间类型列的 M - Schema
    :param column_node: 列节点信息
    :return: M - Schema 格式的字符串和 value description
    """
    properties = column_node['properties']
    column_name = properties['name']
    data_type = properties['data_type']
    prop_type = data_type.upper()

    # 基本信息
    schema_str = f"({column_name}:{prop_type}"

    # 列描述信息
    column_desc = properties.get('column_description')
    if column_desc:
        schema_str += f", {column_desc}"

    # 键信息
    key_info = []
    if 'key_type' in properties:
        if 'primary_key' in properties['key_type']:
            key_info.append('Primary Key')
        if 'foreign_key' in properties['key_type']:
            key_info.append('Foreign Key')
    key_info_str = ', '.join(key_info)
    if key_info_str:
        schema_str += f", {key_info_str}"

    # 示例值
    samples = properties.get('samples', [])
    examples_str = ', '.join(map(str, samples))
    schema_str += f", Examples: [{examples_str}]"

    # 可空性
    is_nullable = properties.get('is_nullable', False)
    nullable_str = "Nullable" if is_nullable else "Not Nullable"
    schema_str += f", {nullable_str}"

    # 统计信息（当可空时）
    if is_nullable:
        data_integrity = properties.get('data_integrity')
        null_count = properties.get('null_count')
        if data_integrity is not None:
            schema_str += f", data integrity: {data_integrity}"
            if data_integrity != 1.0 and null_count is not None and null_count != 0:
                schema_str += f", null count: {null_count}"

    # 其他统计信息
    additional_info = []
    # 可添加时间类型列特有的属性处理逻辑，如 time_span、earliest_time、latest_time 等
    if 'time_span' in properties:
        additional_info.append(f"time span: {properties['time_span']}")
    if 'earliest_time' in properties:
        additional_info.append(f"earliest time: {properties['earliest_time']}")
    if 'latest_time' in properties:
        additional_info.append(f"latest time: {properties['latest_time']}")

    additional_info_str = ', '.join(additional_info)
    if additional_info_str:
        schema_str += f", {additional_info_str}"

    schema_str += ")"

    # 获取 value description
    value_desc = properties.get('value_description')
    return schema_str, value_desc


# 根据列的数据类型调用相应的处理函数生成 M - Schema
def generate_column_schema(column_node):
    data_type = column_node['properties']['data_type'].upper()
    if data_type in ['INTEGER', 'INT', 'SMALLINT', 'BIGINT', 'TINYINT', 'MEDIUMINT', 'REAL', 'FLOAT', 'DOUBLE', 'DECIMAL', 'NUMERIC', 'BOOLEAN']:
        return generate_numeric_column_schema(column_node)
    elif data_type in ['TEXT', 'VARCHAR', 'CHAR', 'NCHAR', 'NVARCHAR', 'NTEXT', 'CLOB', 'TINYTEXT', 'MEDIUMTEXT', 'LONGTEXT', 'JSON', 'XML']:
        return generate_text_column_schema(column_node)
    elif data_type in ['DATE', 'DATETIME', 'TIMESTAMP']:
        return generate_time_column_schema(column_node)
    else:
        return generate_text_column_schema(column_node)

# 生成表节点 Schema 的函数
def generate_table_schema(nodes, relationships):
    table_nodes = [node for node in nodes if 'Table' in node['labels']]
    column_nodes = [node for node in nodes if 'Column' in node['labels']]

    # 构建表和列的映射关系
    table_column_mapping = {}
    for rel in relationships:
        if rel['type'] == 'HAS_COLUMN':
            start_id = rel['start_old_id']
            end_id = rel['end_old_id']
            start_node = next((node for node in table_nodes if node['old_id'] == start_id), None)
            end_node = next((node for node in column_nodes if node['old_id'] == end_id), None)
            if start_node and end_node:
                table_name = start_node['properties']['name']
                if table_name not in table_column_mapping:
                    table_column_mapping[table_name] = []
                table_column_mapping[table_name].append(end_node)

    m_schema = ""
    for table_node in table_nodes:
        table_name = table_node['properties']['name']
        properties = table_node['properties']

        m_schema += f"# Table: {table_name}\n"

        # 展示表节点的属性
        prop_strs = []
        if 'database_name' in properties:
            prop_strs.append(f"Database Name: {properties['database_name']}")
        if 'primary_key' in properties:
            primary_key = properties['primary_key']
            if isinstance(primary_key, list):
                primary_key_str = ', '.join(primary_key)
            else:
                primary_key_str = primary_key
            prop_strs.append(f"Primary Key: {primary_key_str}")
        if 'foreign_key' in properties:
            foreign_key = properties['foreign_key']
            if isinstance(foreign_key, list):
                foreign_key_str = ', '.join(foreign_key)
            else:
                foreign_key_str = foreign_key
            prop_strs.append(f"Foreign Key: {foreign_key_str}")
        if 'columns' in properties:
            columns = properties['columns']
            columns_str = ', '.join(columns)
            prop_strs.append(f"Columns: {columns_str}")
        if 'row_count' in properties:
            prop_strs.append(f"Row Count: {properties['row_count']}")
        if 'column_count' in properties:
            prop_strs.append(f"Column Count: {properties['column_count']}")
        if 'referenced_by' in properties:
            referenced_by = properties['referenced_by']
            referenced_by_str = ', '.join(referenced_by)
            prop_strs.append(f"Referenced By: {referenced_by_str}")
        if 'reference_to' in properties:
            reference_to = properties['reference_to']
            reference_to_str = ', '.join(reference_to)
            prop_strs.append(f"Reference To: {reference_to_str}")

        for prop_str in prop_strs:
            m_schema += f"{prop_str}\n"

        # 收集所有列的 value description
        value_descriptions = {}
        column_schemas = []
        columns = table_column_mapping.get(table_name, [])
        for column in columns:
            column_schema, value_desc = generate_column_schema(column)
            column_schemas.append(column_schema)
            if value_desc:
                column_name = column['properties']['name']
                value_descriptions[column_name] = value_desc

        # 展示列值描述说明板块
        if value_descriptions:
            m_schema += "\n列值描述说明:\n"
            for column_name, value_desc in value_descriptions.items():
                m_schema += f"- {column_name}: {value_desc}\n"

        m_schema += "\n[\n"
        for column_schema in column_schemas:
            m_schema += f"  {column_schema},\n"
        m_schema = m_schema.rstrip(',\n') + "\n]\n"

    return m_schema

db_path = "../graphs_repo/BIRD/books"
# 读取 node.json 和 relationship.json 文件
with open(os.path.join(db_path, 'nodes.json'), 'r') as f:
    nodes = json.load(f)
with open(os.path.join(db_path, 'relationships.json'), 'r') as f:
    relationships = json.load(f)

# 生成 M - Schema
m_schema = generate_table_schema(nodes, relationships)
print(m_schema)
