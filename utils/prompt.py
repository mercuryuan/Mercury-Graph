from neo4j import GraphDatabase

from utils import attributes_retriever


class TableInfoProcessor:
    """
    TableInfoProcessor 类用于处理表的相关信息，将表的各项属性整合为一个字典格式。

    Attributes:
        table_name (str): 表名。
        primary_key (str/list): 表的主键，可以是单个字符串或字符串列表。
        foreign_key (str/list): 表的外键，可以是单个字符串或字符串列表。
        row_count (int): 表的数据行数。
        column_count (int): 表的列数量。
        referenced_by (list): 表被其他表引用的关系列表。
        reference_to (list): 表引用其他表的关系列表。
        columns (list): 表的列信息列表。
    """
    def __init__(self, table_name, primary_key, foreign_key, row_count, column_count, referenced_by, reference_to, columns):
        self.table_name = table_name
        self.primary_key = primary_key
        self.foreign_key = foreign_key
        self.row_count = row_count
        self.column_count = column_count
        self.referenced_by = referenced_by
        self.reference_to = reference_to
        self.columns = columns

    def process_table_info(self):
        """
        将表信息整合成一个字典，包含列信息。

        Returns:
            dict: 包含表各项信息的字典。
        """
        table_info = {
            "table_name": self.table_name,
            "primary_key": self.primary_key,
            "foreign_key": self.foreign_key,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "referenced_by": self.referenced_by,
            "reference_to": self.reference_to,
            "columns": self.columns,
        }
        return table_info


class ColumnInfoProcessor:
    def __init__(self, column_name, data_type, data_count, key_type, samples, referenced_by):
        self.column_name = column_name
        self.data_type = data_type
        self.data_count = data_count
        self.key_type = key_type
        self.samples = samples
        self.referenced_by = referenced_by

    def process_column_info(self):
        """
        将列信息整合成一个字典。

        Returns:
            dict: 包含列各项信息的字典。
        """
        column_info = {
            "name": self.column_name,
            "data_type": self.data_type,
            "data_count": self.data_count,
            "key_type": self.key_type,
            "samples": self.samples,
            "referenced_by": self.referenced_by,
        }
        return column_info


class PromptContentFiller:
    def __init__(self, table_info, columns_info):
        # 直接使用字典取值的方式传递参数给TableInfoProcessor，确保参数名匹配
        self.table_info_processor = TableInfoProcessor(
            table_name=table_info["name"],
            primary_key=table_info["primary_key"],
            foreign_key=table_info["foreign_key"],
            row_count=table_info["row_count"],
            column_count=table_info["column_count"],
            referenced_by=table_info.get("referenced_by", []),
            reference_to=table_info.get("reference_to", []),
            columns=table_info["columns"]
        )
        self.column_info_processors = [ColumnInfoProcessor(**col_info) for col_info in columns_info]

    def generate_prompt_template(self):
        """
        生成表和列信息的描述性提示模板。

        Returns:
            str: 格式化后的提示模板。
        """
        prompt_template = f"""
        Generate a brief description of the table based on the provided structure, its columns, and associated metadata. Include details about its primary key, foreign key relationships, the number of rows, column count, and any relevant constraints or references to other tables.

        Here is the table and column information:

        Table:
        - Name: {self.table_info["table_name"]}
        - Primary Key: {self.table_info["primary_key"]}
        - Foreign Key(s): {self.table_info["foreign_key"]}
        - Row Count: {self.table_info["row_count"]}
        - Column Count: {self.table_info["column_count"]}
        - Referenced by: {self.table_info["referenced_by"]}
        - Reference to: {self.table_info["reference_to"]}

        Columns:
        """

        for column_info in self.columns_info:
            prompt_template += f"""
            - {column_info['name']}: Data Type: {column_info['data_type']}, Data Count: {column_info['data_count']}, Key Type(s): {column_info['key_type']}, Samples: {column_info['samples']}, Referenced by: {column_info['referenced_by']}
            """

        return prompt_template


class PromptContentFiller:
    def __init__(self, table_info, columns_info):
        self.table_info_processor = TableInfoProcessor(**table_info)
        self.column_info_processors = [ColumnInfoProcessor(**col_info) for col_info in columns_info]

    def fill_prompt_template(self):
        """
        填充表和列信息到提示模板中。

        Returns:
            str: 生成的完整提示模板。
        """
        table_info = self.table_info_processor.process_table_info()
        columns_info = [processor.process_column_info() for processor in self.column_info_processors]
        generator = PromptTemplateGenerator(table_info, columns_info)
        return generator.generate_prompt_template()

if __name__ == '__main__':
    # 创建 Neo4j 驱动连接
    uri = "bolt://localhost:7689"
    username = "neo4j"
    password = "12345678"
    driver = GraphDatabase.driver(uri, auth=(username, password))

    # 使用 DatabaseGraphHandler 类
    handler = attributes_retriever.DatabaseGraphHandler(driver)
    info = handler.get_table_and_all_column_nodes_by_table_name("League")
    print(info)
    if info:
        table_info = info[0]  # 提取表节点信息字典
        columns_info = info[1:]  # 提取列节点信息字典列表
        prompt_filler = PromptContentFiller(table_info, columns_info)
        final_prompt = prompt_filler.fill_prompt_template()
        print(final_prompt)
    else:
        print("未获取到有效的表和列节点信息，请检查表名或数据库连接情况。")
