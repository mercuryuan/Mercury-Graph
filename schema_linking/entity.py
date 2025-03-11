import spacy  # 用于自然语言处理
from neo4j import GraphDatabase  # 用于连接Neo4j数据库

# 示例LLM实体提取函数
def llm_entity_extraction(question):
    # 这里简单返回示例结果，实际应调用LLM API
    return {'tables': ['book', 'publisher'], 'columns': ['title', 'publisher_name', 'publisher_id']}

# 示例自然语言工具包实体提取函数
def nlp_entity_extraction(question):
    nlp = spacy.load("en_core_web_sm")
    doc = nlp(question)
    # 简单示例，实际需要更复杂的实体识别逻辑
    tables = []
    columns = []
    for ent in doc.ents:
        if ent.label_ == "ORG" or ent.label_ == "PRODUCT":
            tables.append(ent.text)
        elif ent.label_ == "PERSON" or ent.label_ == "WORK_OF_ART":
            columns.append(ent.text)
    return {'tables': tables, 'columns': columns}

# 取两个实体提取结果的交集
def get_entity_intersection(llm_entities, nlp_entities):
    tables_intersection = list(set(llm_entities['tables']) & set(nlp_entities['tables']))
    columns_intersection = list(set(llm_entities['columns']) & set(nlp_entities['columns']))
    return {'tables': tables_intersection, 'columns': columns_intersection}

# 在Neo4j中查找表节点
def find_table_nodes(driver, table_names):
    with driver.session() as session:
        # 示例查询，根据表名查找表节点
        query = f"MATCH (t:Table) WHERE t.name IN {table_names} RETURN t"
        result = session.run(query)
        table_nodes = [record["t"] for record in result]
        return table_nodes

# 从表节点出发，迭代搜索列节点和外键关系，构建子图
def build_subgraph(driver, table_nodes, column_names):
    subgraph_nodes = []
    subgraph_relationships = []
    for table_node in table_nodes:
        table_name = table_node["name"]
        # 查找该表的列节点
        with driver.session() as session:
            column_query = f"MATCH (t:Table {{name: '{table_name}'}})-[:HAS_COLUMN]->(c:Column) WHERE c.name IN {column_names} RETURN c"
            column_result = session.run(column_query)
            column_nodes = [record["c"] for record in column_result]
            subgraph_nodes.extend(column_nodes)

            # 查找外键关系，继续扩展子图
            foreign_key_query = f"MATCH (t:Table {{name: '{table_name}'}})-[r:FOREIGN_KEY]-(other:Table) RETURN other, r"
            foreign_key_result = session.run(foreign_key_query)
            for record in foreign_key_result:
                other_table_node = record["other"]
                relationship = record["r"]
                subgraph_nodes.append(other_table_node)
                subgraph_relationships.append(relationship)
    return subgraph_nodes, subgraph_relationships

# 主函数
def main(question):
    # 步骤1：实体提取
    llm_entities = llm_entity_extraction(question)
    nlp_entities = nlp_entity_extraction(question)
    entities = get_entity_intersection(llm_entities, nlp_entities)

    # 步骤2：连接Neo4j数据库
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))

    # 步骤3：查找表节点
    table_nodes = find_table_nodes(driver, entities['tables'])

    # 步骤4：构建子图
    subgraph_nodes, subgraph_relationships = build_subgraph(driver, table_nodes, entities['columns'])

    # 关闭数据库连接
    driver.close()

    return subgraph_nodes, subgraph_relationships

if __name__ == "__main__":
    question = "What is the name of the publisher of the book \"The Illuminati\"?"
    subgraph_nodes, subgraph_relationships = main(question)
    print("Subgraph Nodes:", subgraph_nodes)
    print("Subgraph Relationships:", subgraph_relationships)