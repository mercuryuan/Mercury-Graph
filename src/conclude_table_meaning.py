from src.llm import collect_response
from src.neo4j_connector import get_driver
from utils.attributes_retriever import DatabaseGraphHandler


def generate_table_description_prompt(data):
    """
    根据给定的数据结构生成用于请求大语言模型生成表描述的Prompt。

    参数:
    data (list): 包含表节点信息和列节点信息的字典列表，格式如示例所示。

    返回:
    str: 生成的Prompt文本，用于请求大语言模型生成表描述。
    """
    table_info = None
    columns_info = []
    for item in data:
        if 'name' in item and item.get('labels') == 'Table':
            table_info = item
        else:
            columns_info.append(item)

    if table_info is None:
        raise ValueError("未找到有效的表节点信息，请检查输入数据格式。")

    # 提取表的基本信息
    table_name = table_info['name']
    database_name = table_info['database_name']
    primary_key = table_info['primary_key']
    foreign_key = table_info['foreign_key']
    row_count = table_info['row_count']
    column_count = table_info['column_count']

    # 构建表基本信息部分的Prompt内容
    table_prompt = f"""
    所属数据库名: {database_name}
    表名: {table_name}
    主键: {primary_key}
    外键: {foreign_key}
    数据行数: {row_count}
    列数: {column_count}
    """

    # 构建列信息部分的Prompt内容
    columns_prompt = ""
    for column in columns_info:
        column_name = column['name']
        data_type = column['data_type']
        data_count = column['data_count']
        key_type = column.get('key_type', [])  # 若不存在'key_type'，默认为空列表
        samples = column.get('samples', [])  # 若不存在'samples'，默认为空列表

        column_prompt = f"""
        - 列名: {column_name}
          数据类型: {data_type}
          数据量: {data_count}
          是否为主键或外键: {key_type}
        """
        if samples:
            column_prompt += f"          示例数据: {samples}\n"
        columns_prompt += column_prompt

    # 整体的Prompt内容，告知大语言模型要做的任务
    prompt = f"""
    请根据以下提供的表和列的相关信息，生成一段详细且清晰的表描述。此表来自Spider数据集，该数据集没有自带的列描述，所以你需要基于给出的这些信息来综合描述表的用途、各个列之间的关系以及在整个数据库中的作用等内容。
{table_prompt}

    列信息:
    {columns_prompt}
    """

    return prompt

def generate_table_description_prompt_v2(data):
    """
    Generate an optimized prompt for creating concise and meaningful table descriptions in English, utilizing advanced prompt engineering techniques.

    Parameters:
    data (list): A list of dictionaries containing table node and column node information.

    Returns:
    str: The generated prompt for requesting table descriptions from a large language model.
    """
    table_info = None
    columns_info = []
    for item in data:
        if 'name' in item and item.get('labels') == 'Table':
            table_info = item
        else:
            columns_info.append(item)

    if table_info is None:
        raise ValueError("No valid table node information found. Please check the input data format.")

    # Extract table basic information
    table_name = table_info['name']
    database_name = table_info['database_name']
    primary_key = table_info['primary_key']
    foreign_key = table_info['foreign_key']
    row_count = table_info['row_count']
    column_count = table_info['column_count']

    # Construct the prompt header
    table_prompt = f"""
    Database: {database_name}
    Table Name: {table_name}
    Primary Key: {primary_key}
    Foreign Key: {foreign_key}
    Row Count: {row_count}
    Column Count: {column_count}
    """

    # Construct column information part
    columns_prompt = ""
    for column in columns_info:
        column_name = column['name']
        data_type = column['data_type']
        data_count = column['data_count']
        key_type = column.get('key_type', [])
        samples = column.get('samples', [])

        column_prompt = f"""
        - Column Name: {column_name}
          Data Type: {data_type}
          Data Count: {data_count}
          Key Type: {key_type}
        """
        if samples:
            column_prompt += f"          Sample Values: {samples}\n"
        columns_prompt += column_prompt

    # Construct the main prompt with examples
    prompt = f"""
    You are an expert in database schema and business logic. 
    Based on the given table and column information, generate a concise, clear, and meaningful single-sentence description of the table. The description should include the table's definition, its business relevance, and key data characteristics in less than 100 words. Format the response strictly as: "Table Description: [Generated Description]".

    Example 1:
    Input:
    Database: RetailDB
    Table Name: Customers
    Primary Key: customer_id
    Foreign Key: []
    Row Count: 5000
    Column Count: 6

    Column Details:
    - Column Name: customer_id
      Data Type: INTEGER
      Data Count: 5000
      Key Type: Primary Key
      Sample Values: [101, 102, 103]

    - Column Name: customer_name
      Data Type: TEXT
      Data Count: 5000
      Key Type: []
      Sample Values: ["Alice", "Bob", "Charlie"]

    Output:
    Table Description: The "Customers" table stores information about customers, including unique identifiers (customer_id) and their names, enabling customer management in the retail business.

    Example 2:
    Input:
    Database: SportsDB
    Table Name: Matches
    Primary Key: match_id
    Foreign Key: league_id
    Row Count: 2000
    Column Count: 5

    Column Details:
    - Column Name: match_id
      Data Type: INTEGER
      Data Count: 2000
      Key Type: Primary Key
      Sample Values: [1, 2, 3]

    - Column Name: league_id
      Data Type: INTEGER
      Data Count: 2000
      Key Type: Foreign Key
      Sample Values: [10, 20, 30]

    Output:
    Table Description: The "Matches" table contains records of sports matches, linking to leagues via league_id and uniquely identifying matches with match_id, crucial for organizing sports event data.

    Your Task:
    Input:
    {table_prompt}

    Column Details:
    {columns_prompt}

    Output:
    """
    return prompt



if __name__ == '__main__':
    # 创建 Neo4j 驱动连接
    driver = get_driver()

    # 使用 DatabaseGraphHandler 类
    handler = DatabaseGraphHandler(driver)
    data = handler.get_table_and_all_column_nodes_by_table_name('League')
    print(data)
    # prompt = generate_table_description_prompt_v2(data)
    # print(prompt)
    # print(collect_response(prompt))