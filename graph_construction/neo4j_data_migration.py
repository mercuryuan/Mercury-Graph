import json
import os

from config import GRAPHS_REPO
from graph_construction.schema_parser import SchemaParser
from src.neo4j_connector import get_driver

driver = get_driver()


def export_all(exp_path=None):
    # 确保文件夹存在，如果不存在则创建
    if not os.path.exists(exp_path):
        os.makedirs(exp_path)

    # 导出节点（记录id和labels）
    with driver.session() as session:
        nodes = []
        result = session.run("MATCH (n) RETURN id(n) AS node_id, labels(n) AS labels, properties(n) AS props")
        for record in result:
            nodes.append({
                "old_id": record["node_id"],  # 使用旧数据库的节点ID
                "labels": record["labels"],
                "properties": record["props"]
            })
        # 拼接节点文件的完整路径
        nodes_file_path = os.path.join(exp_path, "nodes.json")
        with open(nodes_file_path, "w", encoding="utf-8") as f:
            json.dump(nodes, f, indent=4)

    # 导出关系（记录旧节点ID）
    with driver.session() as session:
        relationships = []
        result = session.run(
            "MATCH (a)-[r]->(b) RETURN id(r) AS rel_id, type(r) AS type, id(a) AS start_id, id(b) AS end_id, properties(r) AS props")
        for record in result:
            relationships.append({
                "type": record["type"],
                "start_old_id": record["start_id"],
                "end_old_id": record["end_id"],
                "properties": record["props"]
            })
        # 拼接关系文件的完整路径
        relationships_file_path = os.path.join(exp_path, "relationships.json")
        with open(relationships_file_path, "w", encoding="utf-8") as f:
            json.dump(relationships, f, indent=4)


def import_all(imp_path=None):
    # 导入节点并建立 ID 映射,加载到Neo4j中
    id_map = {}  # {旧ID: 新ID}
    with driver.session() as session:
        # 清空Neo4j数据库中的所有节点和关系。
        session.run("MATCH (n) DETACH DELETE n")
        # 导入节点
        nodes_file_path = os.path.join(imp_path, "nodes.json")
        with open(nodes_file_path, "r", encoding="utf-8") as f:
            nodes = json.load(f)
            for node in nodes:
                labels = ":".join(node["labels"])
                query = f"CREATE (n:{labels}) SET n = $props RETURN id(n) AS new_id"
                result = session.run(query, props=node["properties"])
                new_id = result.single()["new_id"]
                id_map[node["old_id"]] = new_id  # 记录旧ID到新ID的映射

        # 导入关系
        # 拼接关系文件的完整路径
        relationships_file_path = os.path.join(imp_path, "relationships.json")

        with open(relationships_file_path, "r", encoding="utf-8") as f:
            relationships = json.load(f)
            for rel in relationships:
                start_new_id = id_map.get(rel["start_old_id"])
                end_new_id = id_map.get(rel["end_old_id"])
                if not start_new_id or not end_new_id:
                    print(f"跳过关系 {rel['type']}（节点不存在）")
                    continue

                query = (
                    "MATCH (a), (b) "
                    f"WHERE id(a) = {start_new_id} AND id(b) = {end_new_id} "
                    f"CREATE (a)-[r:{rel['type']}]->(b) "
                    "SET r = $props"
                )
                session.run(query, props=rel["properties"])
        print(f"成功加载 {os.path.basename(imp_path)}到Neo4j数据库")


def load_graph_to_neo4j(dataset_name, db_name):
    # 根据全局变量 GRAPHS_REPO、数据集名称和数据库名称构造数据路径，
    # 该路径指向包含当前数据库图数据（节点和关系）的目录
    path = os.path.join(GRAPHS_REPO, dataset_name, db_name)

    # 调用 import_all 函数，将指定路径下的数据加载并导入到 Neo4j 中，
    # 以便在 Neo4j 上进行后续验证和查询
    import_all(path)


if __name__ == '__main__':
    # 定义导入路径，指向要导入的图数据所在的目录
    db_path = "../graphs_repo/spider/bike_1"
    # 导出图数据
    export_all(db_path)

    # 创建一个 SchemaParser 类的实例，传入 Neo4j 驱动程序
    parser = SchemaParser(driver)

    # 调用 SchemaParser 实例的 clear_neo4j_database 方法，清空 Neo4j 数据库中的所有数据
    parser.clear_neo4j_database()
    # 调用 import_all 函数，将指定路径下的图数据导入到 Neo4j 数据库中

    import_all(db_path)

    # 关闭 Neo4j 驱动程序，释放资源
    driver.close()
