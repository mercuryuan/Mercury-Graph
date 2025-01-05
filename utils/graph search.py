from neo4j import GraphDatabase


class GraphSearch:
    def __init__(self, neo4j_uri, neo4j_user, neo4j_password):
        """
        初始化GraphSearch类，建立与Neo4j数据库的连接。

        :param neo4j_uri: Neo4j数据库的连接地址
        :param neo4j_user: Neo4j数据库的用户名
        :param neo4j_password: Neo4j数据库的密码
        """
        self.neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))

    def close_connections(self):
        """
        关闭与Neo4j数据库的连接。
        """
        self.neo4j_driver.close()

    def find_shortest_path_between_nodes(self, node1_name, node2_name):
        """
        查找两个节点之间的最短路径，并输出清晰的英文描述。

        :param node1_name: 第一个节点的名称
        :param node2_name: 第二个节点的名称
        :return: 路径的详细英文描述
        """
        with self.neo4j_driver.session() as session:
            # 先通过节点名称获取节点id，用于后续基于id查找最短路径
            node1_id = self._get_node_id(node1_name)
            node2_id = self._get_node_id(node2_name)

            if node1_id is None or node2_id is None:
                print(f"节点 {node1_name} 或 {node2_name} 不存在，请检查输入的节点名称是否正确。")
                return None

            result = session.run("""
                MATCH p = shortestPath((n) -[*]-(m))
                WHERE elementId(n) = $node1_id AND elementId(m) = $node2_id
                RETURN p
            """, node1_id=node1_id, node2_id=node2_id)

            path = result.single()
            if path:
                nodes = path["p"].nodes
                relationships = path["p"].relationships
                readable_path = self._parse_path(nodes, relationships)
                return readable_path
            else:
                print(f"未找到 {node1_name} 和 {node2_name} 之间的路径。")
                return None

    def _get_node_id(self, node_name):
        """
        根据节点名称获取节点的id。

        :param node_name: 节点名称，可以是表节点名称（如'table_name'）或者列节点名称（如'table_name.column_name'形式）
        :return: 节点的id，如果节点不存在则返回None
        """
        with self.neo4j_driver.session() as session:
            if '.' in node_name:  # 判断是否为列节点名称（包含表名和列名）
                table_name, column_name = node_name.split('.')
                result = session.run("""
                    MATCH (t:Table {name: $table_name}) -[:HAS_COLUMN]-> (c:Column {name: $column_name})
                    RETURN elementId(c)
                """, table_name=table_name, column_name=column_name)
            else:  # 表节点名称
                result = session.run("""
                    MATCH (n:Table {name: $node_name})
                    RETURN elementId(n)
                """, node_name=node_name)

            node_info = result.single()
            if node_info:
                return node_info[0]
            return None

    def _parse_path(self, nodes, relationships):
        """
        解析路径中的节点和关系，生成结构化的英文描述。

        :param nodes: 路径中的节点列表
        :param relationships: 路径中的关系列表
        :return: 路径的英文描述
        """
        path_details = []
        path_nodes = []
        for i in range(len(relationships)):
            current_node = nodes[i]
            next_node = nodes[i + 1]
            relationship = relationships[i]

            current_id = current_node.element_id
            next_id = next_node.element_id

            # 获取当前节点和下一个节点的类型（表或列）
            current_type = "Table" if "Table" in current_node.labels else "Column"
            next_type = "Table" if "Table" in next_node.labels else "Column"

            # 处理表与表之间的关系
            if current_type == "Table" and next_type == "Table":
                from_column = relationship.get("from_column", "")
                to_column = relationship.get("to_column", "")
                path_details.append(
                    f"{i + 1}. 表 '{current_node['name']}'（{current_type}）通过外键 '{from_column}' 指向列 '{to_column}' 来引用表 '{next_node['name']}'（{next_type}）。"
                )
            # 处理列与列之间的关系
            elif current_type == "Column" and next_type == "Column":
                relationship_type = relationship.type
                path_details.append(
                    f"{i + 1}. 列 '{current_node['name']}'（{current_type}）通过类型为 '{relationship_type}' 的关系与列 '{next_node['name']}'（{next_type}）相关联。"
                )
            # 处理表与列之间的关系（表包含列的情况）
            elif current_type == "Table" and next_type == "Column":
                path_details.append(
                    f"{i + 1}. 表 '{current_node['name']}'（{current_type}）包含列 '{next_node['name']}'（{next_type}）。"
                )
            # 处理列与表之间的关系（列属于表的情况）
            elif current_type == "Column" and next_type == "Table":
                path_details.append(
                    f"{i + 1}. 列 '{current_node['name']}'（{current_type}）属于表 '{next_node['name']}'（{next_type}）。"
                )

            path_nodes.append(f"{current_node['name']}（{current_type}）")

        # 添加最后一个节点（列节点）到路径节点列表和详细描述中
        last_node = nodes[-1]
        last_type = "Column" if "Column" in last_node.labels else "Table"
        path_nodes.append(f"{last_node['name']}（{last_type}）")
        if last_type == "Column":
            path_details.append(f"{len(relationships) + 1}. 表 '{next_node['name']}'（{next_type}）包含列 '{last_node['name']}'（{last_type}）。")

        # 组合所有的路径描述信息
        detailed_description = "\n".join(path_details)
        overall_path = " -> ".join(path_nodes)
        return f"Overall Path: {overall_path}\n\nDetailed analysis:\n{detailed_description}"


if __name__ == "__main__":
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "12345678"

    graph_search = GraphSearch(neo4j_uri, neo4j_user, neo4j_password)

    node1_name = "book_language.language_id"
    node2_name = "customer.customer_id"

    shortest_path = graph_search.find_shortest_path_between_nodes(node1_name, node2_name)
    if shortest_path:
        print(f"{node1_name} 和 {node2_name} 之间的路径：")
        print(shortest_path)
    else:
        print(f"未找到 {node1_name} 和 {node2_name} 之间的路径。")

    graph_search.close_connections()