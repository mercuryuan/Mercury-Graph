import json
import os

from neo4j import GraphDatabase
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
        with open(nodes_file_path, "w") as f:
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
        with open(relationships_file_path, "w") as f:
            json.dump(relationships, f, indent=4)


def import_all():
    # 导入节点并建立 ID 映射
    id_map = {}  # {旧ID: 新ID}

    with driver.session() as session:
        # 导入节点
        with open("nodes.json", "r") as f:
            nodes = json.load(f)
            for node in nodes:
                labels = ":".join(node["labels"])
                query = f"CREATE (n:{labels}) SET n = $props RETURN id(n) AS new_id"
                result = session.run(query, props=node["properties"])
                new_id = result.single()["new_id"]
                id_map[node["old_id"]] = new_id  # 记录旧ID到新ID的映射

        # 导入关系
        with open("relationships.json", "r") as f:
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


if __name__ == '__main__':
    # export_all()
    import_all()
    driver.close()
