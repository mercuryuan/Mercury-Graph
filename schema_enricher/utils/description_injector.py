import os
import json
from config import GRAPHS_REPO, GENERATED_DESCRIPTIONS, PROJECT_ROOT
from graph_construction.neo4j_data_migration import import_all, load_graph_to_neo4j


def build_table_column_mapping(node_file, relationship_file):
    """
    构建表-列映射，确保列归属于正确的表。

    :param node_file: node.json 文件路径
    :param relationship_file: relationship.json 文件路径
    :return: table_column_mapping 字典 {table_name: [column_node1, column_node2, ...]}
    """
    # 读取 node.json
    with open(node_file, "r", encoding="utf-8") as f:
        nodes = json.load(f)

    # 读取 relationship.json
    with open(relationship_file, "r", encoding="utf-8") as f:
        relationships = json.load(f)

    # 分离 Table 和 Column 节点
    table_nodes = {node["old_id"]: node for node in nodes if "Table" in node["labels"]}
    column_nodes = {node["old_id"]: node for node in nodes if "Column" in node["labels"]}

    # 构建 Table -> Column 映射
    table_column_mapping = {table["properties"]["name"]: [] for table in table_nodes.values()}

    # 遍历 relationships 建立映射
    for rel in relationships:
        if rel["type"] == "HAS_COLUMN":
            table_id = rel["start_old_id"]
            column_id = rel["end_old_id"]
            if table_id in table_nodes and column_id in column_nodes:
                table_name = table_nodes[table_id]["properties"]["name"]
                table_column_mapping.setdefault(table_name, []).append(column_nodes[column_id])

    # 确保所有表都有 key，即便它们没有列
    for table_name in table_nodes.values():
        table_column_mapping.setdefault(table_name["properties"]["name"], [])

    return table_column_mapping


def build_table_column_mapping_from_nodes(nodes, relationship_file):
    """
    根据已加载的 nodes 数据和 relationship.json 文件，构建表-列映射，
    确保列归属于正确的表。

    :param nodes: 已加载的 node.json 数据（列表）
    :param relationship_file: relationships.json 文件路径
    :return: table_column_mapping 字典 {table_name: [column_node1, column_node2, ...]}
    """
    # 分离 Table 和 Column 节点
    table_nodes = {node["old_id"]: node for node in nodes if "Table" in node["labels"]}
    column_nodes = {node["old_id"]: node for node in nodes if "Column" in node["labels"]}

    # 初始化映射（即使某些表没有列，也保证有 key）
    table_column_mapping = {table["properties"]["name"]: [] for table in table_nodes.values()}

    # 读取 relationships.json
    with open(relationship_file, "r", encoding="utf-8") as f:
        relationships = json.load(f)

    # 遍历 relationships 建立映射
    for rel in relationships:
        if rel["type"] == "HAS_COLUMN":
            table_id = rel["start_old_id"]
            column_id = rel["end_old_id"]
            if table_id in table_nodes and column_id in column_nodes:
                table_name = table_nodes[table_id]["properties"]["name"]
                table_column_mapping.setdefault(table_name, []).append(column_nodes[column_id])

    # 确保所有表都有 key，即便它们没有列
    for table in table_nodes.values():
        table_column_mapping.setdefault(table["properties"]["name"], [])

    return table_column_mapping


def get_paths(dataset_name, db_name):
    """
    根据数据集名称和数据库名称，自动构建文件路径。

    :param dataset_name: 数据集名称 (spider / bird)
    :param db_name: 数据库名称
    :return: node.json、relationship.json、description.json 的路径
    """
    base_path = os.path.join(GRAPHS_REPO, dataset_name, db_name)
    node_file = os.path.join(base_path, "nodes.json")
    relationship_file = os.path.join(base_path, "relationships.json")
    description_file = os.path.join(GENERATED_DESCRIPTIONS, dataset_name, f"{db_name}.json")

    return node_file, relationship_file, description_file


def update_node_descriptions(nodes, descriptions, table_column_mapping):
    """
    将 descriptions 注入到 nodes 中。

    :param nodes: 读取的 node.json 数据（列表）
    :param descriptions: 读取的 description.json 数据（字典）
    :param table_column_mapping: {table_name: [column_node1, column_node2, ...]}
    :return: 更新后的 nodes
    """
    for table_name, table_info in descriptions.items():
        if table_name in table_column_mapping:
            # 更新表的描述
            for node in nodes:
                if "Table" in node["labels"] and node["properties"]["name"] == table_name:
                    node["properties"]["description"] = table_info[0].get("table_description",
                                                                          "No description available")

            # 更新列的描述
            for column_name, column_desc in table_info[0]["columns"].items():
                updated = False
                for column_node in table_column_mapping[table_name]:
                    if column_node["properties"]["name"] == column_name:
                        column_node["properties"]["column_description"] = column_desc
                        updated = True
                if not updated:
                    print(f"[Warning] 在表 {table_name} 中未找到列 '{column_name}' 的对应节点。")
    return nodes


import os
import json
import datetime
from config import GRAPHS_REPO, GENERATED_DESCRIPTIONS


def log_msg(message):
    """
    输出带有时间戳的日志信息。
    """
    timestamp = datetime.datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    print(f"{timestamp} {message}")


def inject_descriptions(dataset_name, db_name):
    """
    读取 description.json，将描述信息注入到 node.json 中，并将更新后的数据覆盖写回原文件。

    :param dataset_name: 数据集名称（例如 "spider" 或 "bird"）
    :param db_name: 数据库名称
    """
    # 根据数据集名称和数据库名称获取各个文件的路径
    node_file, relationship_file, description_file = get_paths(dataset_name, db_name)
    log_msg(
        f"开始处理 {dataset_name}/{db_name}。节点文件：{node_file}，关系文件：{relationship_file}，描述文件：{description_file}")

    # 检查 node.json、relationships.json 和 description.json 文件是否都存在
    for file in [node_file, relationship_file, description_file]:
        if not os.path.exists(file):
            log_msg(f"❌ 文件不存在: {file}")
            return

    # 仅加载一次 node.json 数据，避免多次加载导致对象不一致
    with open(node_file, "r", encoding="utf-8") as f:
        nodes = json.load(f)
    log_msg("成功加载节点数据。")

    # 加载描述信息文件 description.json
    with open(description_file, "r", encoding="utf-8") as f:
        descriptions = json.load(f)
    log_msg("成功加载描述信息。")

    # 使用已加载的 nodes 数据构建表-列映射关系，
    # 这样映射中的列节点与 nodes 对象为同一引用，后续更新才会反映到 nodes 中
    table_column_mapping = build_table_column_mapping_from_nodes(nodes, relationship_file)
    log_msg("构建表-列映射关系完成。")

    # 将 descriptions 中的描述信息注入到 nodes 数据中
    nodes = update_node_descriptions(nodes, descriptions, table_column_mapping)
    log_msg("描述信息已成功注入节点数据。")

    # 将更新后的 nodes 数据写回 node.json 文件，覆盖原有内容
    with open(node_file, "w", encoding="utf-8") as f:
        json.dump(nodes, f, indent=4, ensure_ascii=False)
    log_msg(f"✅ {dataset_name}/{db_name} 的描述注入完成，结果已保存至 {node_file}")


if __name__ == '__main__':
    # 设置数据集名称和数据库名称
    dataset_name = "spider"
    db_name = "bike_1"

    # 调用 inject_descriptions 函数，将 description.json 中的描述信息注入到 node.json 中
    # 并将更新后的 node.json 文件保存，确保后续数据加载使用的是最新数据
    inject_descriptions(dataset_name, db_name)

    # 加载更新后的数据并导入到 Neo4j 进行验证
    # 这里使用 load_graph_to_neo4j 函数，传入构建好的路径，用于将节点和关系数据导入到 Neo4j 数据库中
    load_graph_to_neo4j(dataset_name, db_name)
