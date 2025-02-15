import json
from utils.sql_parser import SqlParserTool
from neo4j import GraphDatabase


def read_json_file(json_file_path):
    """
    读取指定路径的JSON文件内容。

    :param json_file_path: JSON文件的路径
    :return: 解析后的JSON数据（通常是字典或列表形式）
    """
    with open(json_file_path, 'r', encoding='utf-8') as file:
        return json.load(file)


def analyze_sql_query(sql, driver,question=None,db_id=None):
    """
    使用SqlParserTool对单个SQL语句进行解析并展示相关信息。

    :param sql: SQL语句字符串
    """
    tool = SqlParserTool(driver)
    tool.parse_and_display(sql, question, db_id)


def analyze_single_sql_in_entry(entry, session, driver):
    """
    分析单个JSON条目中的SQL语句，包括解析、生成Cypher查询语句以及在Neo4j中进行验证。

    参数:
        entry (dict): JSON文件中的单个数据条目，预期包含'SQL'键对应的SQL语句。
        session (neo4j.Session): Neo4j数据库会话对象，用于执行Cypher查询语句验证。
        driver (GraphDatabase.driver): Neo4j数据库的驱动对象，用于初始化SqlParserTool类。

    返回:
        bool: 如果Cypher查询语句验证通过返回True，否则返回False。
    """
    question = entry.get('question')
    db_id = entry.get('db_id')
    sql = entry.get('SQL')
    if sql:
        tool = SqlParserTool(driver)
        entities, relationships = tool.extract_entities_and_relationships(sql)
        analyze_sql_query(sql,driver,question,db_id)
        cypher_query = tool.sql2subgraph(entities,relationships)
        try:
            session.run(cypher_query)
            return True
        except Exception as e:
            print(f"第 {entry.get('id', '未知')} 条记录对应的Cypher查询语句验证失败，无法在Neo4j中执行，错误信息如下：\n{e}")
            return False
    return False


def analyze_json_sql_data(json_file_path, driver):
    """
    处理指定的JSON文件，逐一对其中包含的SQL语句进行分析展示，并统计通过Neo4j验证的语句条数。

    :param json_file_path: 包含SQL语句的JSON文件的路径
    :param driver (GraphDatabase.driver): Neo4j数据库的驱动对象
    """
    print(f"开始读取JSON文件: {json_file_path}")
    data = read_json_file(json_file_path)
    print(f"JSON文件读取完成，共包含 {len(data)} 条数据记录。")
    print('-' * 80)

    passed_count = 0
    try:
        with driver.session() as session:
            for index, entry in enumerate(data, start=1):
                print(f"开始处理第 {index} /{len(data)}条记录...")
                if analyze_single_sql_in_entry(entry, session, driver):
                    passed_count += 1
                print('-' * 120)
    finally:
        print(f"通过Neo4j验证的SQL语句条数为: {passed_count}/{len(data)}")


if __name__ == "__main__":
    # Neo4j数据库连接配置，根据实际情况修改
    neo4j_uri = "bolt://localhost:7689"
    neo4j_user = "neo4j"
    neo4j_password = "12345678"
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    # 这里可以替换成任意你想要分析的包含SQL语句的JSON文件路径
    # json_file_path = '../data/bird/books.json'
    json_file_path = '../data/bird/shakespeare.json'
    analyze_json_sql_data(json_file_path, driver)
    driver.close()