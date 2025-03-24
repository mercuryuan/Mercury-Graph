from neo4j import GraphDatabase

from src.neo4j_connector import get_driver


class Neo4jExplorer:
    def __init__(self, driver):
        self.driver = driver

    def get_all_nodes(self):
        query = """
        MATCH (n)
        RETURN labels(n) AS labels, properties(n) AS properties
        """
        with self.driver.session() as session:
            result = session.run(query)
            nodes = [record for record in result]
        return nodes

    def get_all_relationships(self):
        query = """
        MATCH ()-[r]->()
        RETURN type(r) AS type, properties(r) AS properties
        """
        with self.driver.session() as session:
            result = session.run(query)
            relationships = [record for record in result]
        return relationships

    def get_all_tables(self):
        query = """
        MATCH (t:Table)
        RETURN properties(t) AS properties
        """
        with self.driver.session() as session:
            result = session.run(query)
            tables = [record["properties"] for record in result]
        return tables

    def get_all_foreign_keys(self):
        query = """
        MATCH ()-[r:FOREIGN_KEY]->()
        RETURN properties(r) AS properties
        """
        with self.driver.session() as session:
            result = session.run(query)
            foreign_keys = [record["properties"] for record in result]
        return foreign_keys

    def get_columns_for_table(self, table_name):
        query = """
        MATCH (t:Table {name: $table_name})-[:HAS_COLUMN]->(c:Column)
        RETURN properties(c) AS properties
        """
        with self.driver.session() as session:
            result = session.run(query, table_name=table_name)
            columns = [record["properties"] for record in result]

        if not columns:
            print(f"[WARNING] 没有找到表 '{table_name}' 的列信息，请检查表名是否正确或数据库是否正确存储了列数据。")

        return columns

    def get_neighbor_tables(self, table_name, n_hop):
        query = """
        MATCH (t:Table {name: $table_name})
        CALL apoc.path.expandConfig(t, {relationshipFilter: "FOREIGN_KEY", minLevel: $n_hop, maxLevel: $n_hop, labelFilter: "+Table"}) 
        YIELD path
        RETURN DISTINCT last(nodes(path)).name AS neighbor_table
        """
        with self.driver.session() as session:
            result = session.run(query, table_name=table_name, n_hop=n_hop)
            neighbor_tables = [record["neighbor_table"] for record in result]

        if not neighbor_tables:
            print(f"[WARNING] 没有找到 {n_hop}-hop 的相关表，请检查表名或数据库连接。")

        return neighbor_tables

    def bfs(self, start_table):
        all_tables = set(record["name"] for record in self.get_all_tables())
        if start_table not in all_tables:
            print(f"[ERROR] 起始表 {start_table} 不存在于数据库中。")
            return []

        visited = set()
        queue = [(start_table, 0)]  # (table_name, hop_level)
        result = []

        while queue:
            level_size = len(queue)
            level_tables = []

            for _ in range(level_size):
                current_table, level = queue.pop(0)
                if current_table in visited:
                    continue

                visited.add(current_table)
                level_tables.append(current_table)

                neighbors = self.get_neighbor_tables(current_table, 1)
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append((neighbor, level + 1))

            if level_tables:
                result.append(level_tables)

        unvisited_tables = all_tables - visited
        if unvisited_tables:
            print(f"[DEBUG] 存在未被访问的表: {unvisited_tables}")

        return result

    def is_subgraph_connected(self, selected_tables):
        if not selected_tables:
            return False

        visited = set()
        queue = [selected_tables[0]]  # 从任意一个表开始 BFS

        while queue:
            current_table = queue.pop(0)
            if current_table in visited:
                continue

            visited.add(current_table)
            neighbors = self.get_neighbor_tables(current_table, 1)
            for neighbor in neighbors:
                if neighbor in selected_tables and neighbor not in visited:
                    queue.append(neighbor)

        return len(visited) == len(selected_tables)

    def bfs_subgraph(self, selected_tables):
        all_tables = set(record["name"] for record in self.get_all_tables())
        invalid_tables = [table for table in selected_tables if table not in all_tables]

        if invalid_tables:
            print(f"[ERROR] 以下表不存在于数据库中: {invalid_tables}")
            return []

        if not self.is_subgraph_connected(selected_tables):
            print("[ERROR] 选定的子图不是连通的，请检查输入的表。")
            return []

        visited = set(selected_tables)  # 已选择的子图中的表都算已访问
        queue = [(table, 0) for table in selected_tables]  # 初始化队列
        result = []

        while queue:
            level_size = len(queue)
            level_tables = []

            for _ in range(level_size):
                current_table, level = queue.pop(0)

                # 记录当前层的表
                level_tables.append(current_table)

                # 获取 1-hop 邻居
                neighbors = self.get_neighbor_tables(current_table, 1)
                for neighbor in neighbors:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, level + 1))

            if level_tables:
                result.append(level_tables)

        unvisited_tables = all_tables - visited
        if unvisited_tables:
            print(f"[DEBUG] 存在未被访问的表: {unvisited_tables}")

        return result


class SchemaGenerator:
    def __init__(self):
        pass

    def generate_table_description(self, table_info, mode="full"):
        """
        根据提供的表信息，智能生成结构化文字描述。

        :param table_info: 字典，包含表的相关信息
        :param mode: "full"（完整）, "brief"（简略）, "minimal"（极简）
        :return: 结构化文字描述
        """
        table_name = table_info.get("name", "未知表名")
        columns = table_info.get("columns", [])
        primary_key = table_info.get("primary_key")
        foreign_keys = table_info.get("foreign_key")
        row_count = table_info.get("row_count")
        column_count = table_info.get("column_count", len(columns))
        referenced_by = table_info.get("referenced_by", [])
        reference_to = table_info.get("reference_to", [])

        description_lines = [f"# Table: {table_name}", f"Columns: {', '.join(columns)}"]

        if mode == "full":
            if column_count:
                description_lines.append(f"Column Count: {column_count}")
            if primary_key:
                description_lines.append(f"Primary Key: {primary_key}")

            if foreign_keys:
                if isinstance(foreign_keys, list):
                    foreign_key_str = ", ".join(foreign_keys)
                else:
                    foreign_key_str = str(foreign_keys)
                description_lines.append(f"Foreign Key: {foreign_key_str}")

            if row_count:
                description_lines.append(f"Row Count: {row_count}")

            if referenced_by:
                description_lines.append(f"Referenced By: {', '.join(referenced_by)}")

            if reference_to:
                description_lines.append(f"Reference To: {', '.join(reference_to)}")

        elif mode == "brief":  # 有待开发
            description_lines = [
                f"# Table: {table_name}",
                f"Columns: {', '.join(columns)}",
                f"Primary Key: {primary_key}" if primary_key else "",
                f"Row Count: {row_count}" if row_count else "",
            ]

        elif mode == "minimal":
            description_lines = [f"# Table: {table_name}", f"Column: {columns}"]

        return "\n".join(filter(None, description_lines))  # 过滤掉空字符串

    numeric_types = [
        "INTEGER", "INT", "SMALLINT", "BIGINT", "TINYINT", "MEDIUMINT",
        "REAL", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BOOLEAN"
    ]

    text_types = [
        "TEXT", "VARCHAR", "CHAR", "NCHAR", "NVARCHAR", "NTEXT",
        "CLOB", "TINYTEXT", "MEDIUMTEXT", "LONGTEXT", "JSON", "XML"
    ]

    datetime_types = ["DATE", "DATETIME", "TIMESTAMP"]

    def generate_column_description(self, column_info, mode="full"):
        """
        根据 column_info 动态构造输出描述，只有存在的属性才会输出。
        输出顺序：
          1. 基本属性: name, data_type, column_description, samples
          2. 完整性属性: null_count, data_integrity, sample_count, is_nullable
          3. 键类型属性: key_type（格式化为 Primary Key / Foreign Key）
          4. 语义属性: value_description
          5. 数值型属性（仅针对 numeric 类型）：numeric_range, numeric_mean, numeric_mode
          6. 文本型属性（仅针对 text 类型）：text_categories, average_char_length, word_frequency
          7. 时间型属性（仅针对 datetime 类型）：earliest_time, latest_time, time_span
        """
        # 基本属性
        name = column_info.get("name", "未知列")
        data_type = column_info.get("data_type", "未知类型")
        base_data_type = data_type.split("(")[0].upper()
        column_description = column_info.get("column_description", None)
        samples = column_info.get("samples", [])
        # 限制最多6个样本
        samples = samples[:6] if samples else None
        samples_str = f"examples: [{', '.join(map(str, samples))}]" if samples else None

        # 完整性属性
        is_nullable = column_info.get("is_nullable", None)
        if is_nullable is not None:
            nullable_str = "Nullable" if is_nullable else "Not Nullable"
        else:
            nullable_str = None

        # 根据参考逻辑，仅在 is_nullable 为 True 时输出 data_integrity 与 null_count（当 null_count 非 0 时）
        integrity_info = []
        if is_nullable:
            data_integrity = column_info.get("data_integrity")
            null_count = column_info.get("null_count")
            if data_integrity is not None:
                integrity_info.append(f"DataIntegrity: {data_integrity}")
                if null_count and null_count != 0:
                    integrity_info.append(f"NullCount: {null_count}")

        # 键类型属性
        key_type = column_info.get("key_type", [])
        key_info = []
        if "primary_key" in key_type:
            key_info.append("Primary Key")
        if "foreign_key" in key_type:
            key_info.append("Foreign Key")
        key_info_str = ", ".join(key_info) if key_info else None

        # 语义属性
        value_description = column_info.get("value_description", None)
        # 如果需要可以取消注释下行以输出值域说明
        # value_description_str = f"ValueDescription: {value_description}" if value_description else None

        # 构造描述列表，只有属性存在时才添加
        details = [f"({name}:{base_data_type}"]
        if column_description:
            details.append(column_description)
        if key_info_str:
            details.append(key_info_str)
        if samples_str:
            details.append(samples_str)
        if nullable_str:
            details.append(nullable_str)
        # 添加完整性信息，仅在 is_nullable 为 True 时输出
        if integrity_info:
            details.extend(integrity_info)
        # 如果需要输出 sample_count，可按如下逻辑添加（目前未采纳参考代码逻辑）：\n
        # if "sample_count" in column_info:\n
        #     details.append(f"SampleCount: {column_info['sample_count']}")\n
        # 语义属性（如果需要）：\n
        # if value_description:\n
        #     details.append(f"ValueDescription: {value_description}")

        # 数值型特有属性
        if base_data_type in self.numeric_types:
            if "numeric_range" in column_info:
                details.append(f"Range: {column_info['numeric_range']}")
            if "numeric_mean" in column_info:
                details.append(f"NumericMean: {column_info['numeric_mean']}")
            if "numeric_mode" in column_info:
                details.append(f"NumericMode: {column_info['numeric_mode']}")

        # 文本型特有属性
        if base_data_type in self.text_types:
            if "text_categories" in column_info:
                details.append(f"TextCategories: {column_info['text_categories']}")
            if "average_char_length" in column_info:
                details.append(f"AverageCharLength: {column_info['average_char_length']}")
            if "word_frequency" in column_info:
                details.append(f"WordFrequency: {column_info['word_frequency']}")

        # 时间型特有属性
        if base_data_type in self.datetime_types:
            if "earliest_time" in column_info:
                details.append(f"EarliestTime: {column_info['earliest_time']}")
            if "latest_time" in column_info:
                details.append(f"LatestTime: {column_info['latest_time']}")
            if "time_span" in column_info:
                details.append(f"TimeSpan: {column_info['time_span']}")

        return ",".join(details) + ")"


if __name__ == "__main__":
    import logging

    logging.getLogger("neo4j").setLevel(logging.ERROR)  # 屏蔽警告

    driver = get_driver()
    explorer = Neo4jExplorer(driver)

    try:
        # for hop in explorer.bfs("Faculty"):
        #     print(hop)
        # print()
        # for hop in explorer.bfs_subgraph(["Faculty", "Faculty_Participates_in", "Activity"]):
        #     print(hop)

        tables = explorer.get_all_tables()
        # for table in tables:
        #     print(table)
        # print("表名:", table.get("name", "未知"))
        # print("数据库名:", table.get("database_name", "未知"))
        # print("列:", table.get("columns", []))
        # print("主键:", table.get("primary_key", []))
        # print("行数:", table.get("row_count", 0))
        # print("外键:", table.get("foreign_key", []))
        # print("被引用关系:", table.get("referenced_by", []))
        # print("引用关系:", table.get("reference_to", []))
        # print("=" * 50)
        sg = SchemaGenerator()
        # print(sg.generate_table_description(tables[1]))
        # print(sg.generate_table_description(tables[12], "minimal"))

        col = explorer.get_columns_for_table("customer")
        for record in col:
            # print(record)
            print(sg.generate_column_description(record))
    finally:
        driver.close()
