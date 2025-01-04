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

    # def create_graph_projection(self, projection_name, node_labels, relationship_types):
    #     """
    #     创建指定名称、包含特定节点标签和关系类型的图投影。
    #
    #     :param projection_name: 图投影的名称（字符串形式）
    #     :param node_labels: 节点标签列表（字符串列表形式）
    #     :param relationship_types: 关系类型列表（字符串列表形式）
    #     """
    #     with self.neo4j_driver.session() as session:
    #         session.run("""
    #             CALL gds.graph.project(
    #                 $projection_name,
    #                 $node_labels,
    #                 $relationship_types
    #             )
    #         """, projection_name=projection_name, node_labels=node_labels, relationship_types=relationship_types)
    #     with self.neo4j_driver.session() as session:
    #         result = session.run(
    #             "CALL gds.graph.list() YIELD graphName, nodeCount, relationshipCount WHERE graphName = $projection_name RETURN graphName, nodeCount, relationshipCount",
    #             projection_name=projection_name)
    #         for record in result:
    #             print(
    #                 f"Graph Name: {record['graphName']}, Node Count: {record['nodeCount']}, Relationship Count: {record['relationshipCount']}")

    def find_shortest_path_between_nodes(self, node1_name, node2_name):
        """
        在Neo4j图中使用最短路径算法查找给定两个节点之间的最短连通子图（路径）。

        :param node1_name: 第一个节点的名字（字符串形式）
        :param node2_name: 第二个节点的名字（字符串形式）
        :return: 最短路径信息（以节点列表形式，如果不存在路径则返回None）
        """
        with self.neo4j_driver.session() as session:
            # 使用最短路径算法查询
            result = session.run("""
                MATCH p = shortestPath((n {name: $node1_name})-[*]-(m {name: $node2_name}))
                RETURN p
            """, node1_name=node1_name, node2_name=node2_name)
            path = result.single()
            if path:
                # 提取路径中的节点信息
                path_nodes = [node for node in path["p"].nodes]
                return path_nodes
            print(f"未找到节点 {node1_name} 和 {node2_name} 之间的路径")
            return None

    # def delete_graph_projection(self, projection_name):
    #     """
    #     删除指定名称的图投影。
    #
    #     :param projection_name: 图投影的名称（字符串形式）
    #     """
    #     with self.neo4j_driver.session() as session:
    #         session.run("""
    #             CALL gds.graph.drop($projection_name)
    #         """, projection_name=projection_name)

if __name__ == "__main__":
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "12345678"

    graph_search = GraphSearch(neo4j_uri, neo4j_user, neo4j_password)
    # graph_search.delete_graph_projection('myGraph')


    # 创建投影图，假设节点标签有['Table']，关系类型有['FOREIGN_KEY']，投影图名称为'myGraph'
    # graph_search.create_graph_projection('myGraph', ['Table'], ['FOREIGN_KEY'])

    node1_name = "book_language"  # 替换为实际的节点1名字
    node2_name = "book_author"  # 替换为实际的节点2名字

    shortest_path = graph_search.find_shortest_path_between_nodes(node1_name, node2_name)
    if shortest_path:
        print(f"找到节点 {node1_name} 和 {node2_name} 之间的最短路径:")
        for node in shortest_path:
            print(node)
    else:
        print(f"未找到节点 {node1_name} 和 {node2_name} 之间的路径")

    # 删除投影图
    # graph_search.delete_graph_projection('myGraph')
    # graph_search.close_connections()