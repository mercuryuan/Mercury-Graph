import json
from neo4j import GraphDatabase
from utils.call import ChatGPTAPIWrapper  # 根据实际情况调整导入路径和内容
import os

# 定义用于存储关系描述的json文件路径，可根据实际需求调整
RELATION_DESCRIPTION_FILE = "relation_descriptions.json"

class GraphEnricher:
    def __init__(self, neo4j_uri, neo4j_user, neo4j_password,api_key):
        """
        初始化GraphEnricher类，建立与Neo4j数据库的连接，并创建ChatGPT API包装类的实例。

        :param neo4j_uri: Neo4j数据库的连接地址
        :param neo4j_user: Neo4j数据库的用户名
        :param neo4j_password: Neo4j数据库的密码
        :param api_key: 从OpenAI平台获取的API密钥
        """
        self.neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        self.chat_gpt_api = ChatGPTAPIWrapper()

    def close_connections(self):
        """
        关闭与Neo4j数据库的连接。
        """
        self.neo4j_driver.close()

    def get_relation_description(self, node1_label, node1_properties, node2_label, node2_properties):
        """
        调用ChatGPT获取两个节点之间的关系描述，若已存在对应描述的json文件则直接读取使用。

        :param node1_label: 第一个节点的标签（字符串形式）
        :param node1_properties: 第一个节点的属性（字典形式）
        :param node2_label: 第二个节点的标签（字符串形式）
        :param node2_properties: 第二个节点的属性（字典形式）
        :return: 两节点之间关系描述（字符串形式），优先从json文件获取，若不存在则调用ChatGPT获取并保存到json文件
        """
        node_pair_key = self._generate_node_pair_key(node1_label, node1_properties, node2_label, node2_properties)
        print(node_pair_key)
        relation_description = self._load_relation_description_from_json(node_pair_key)
        if relation_description:
            print(f"从JSON文件中读取节点 {node1_label} 与 {node2_label} 之间的关系描述: {relation_description}")
            return relation_description

        print(f"正在调用ChatGPT获取节点 {node1_label} 与 {node2_label} 之间的关系描述...")
        node1_info = f"标签: {node1_label}, 属性: {json.dumps(node1_properties)}"
        node2_info = f"标签: {node2_label}, 属性: {json.dumps(node2_properties)}"
        messages = [
            {"role": "user", "content": f"请描述节点 {node1_info} 和节点 {node2_info} 之间的关系。"}
        ]
        relation_description = self.chat_gpt_api.generate_response(messages)
        if relation_description:
            self._save_relation_description_to_json(node_pair_key, relation_description)
            print(f"成功调用ChatGPT获取节点 {node1_label} 与 {node2_label} 之间的关系描述，并保存到JSON文件: {relation_description}")
        else:
            print(f"调用ChatGPT获取节点 {node1_label} 与 {node2_label} 之间的关系描述失败")
        return relation_description

    def enrich_schema_graph(self):
        """
        利用ChatGPT生成的关系描述（优先从json文件获取）来丰富Neo4j中的schema graph。

        遍历图中的节点对，获取它们之间的关系描述，并将描述添加到对应的节点关系上作为属性。

        :return: 无，直接在Neo4j数据库中更新图结构，丰富节点间关系描述
        """
        with self.neo4j_driver.session() as session:
            # 查询所有节点
            result = session.run("MATCH (n) RETURN n")
            nodes = [record['n'] for record in result]
            print(f"共获取到 {len(nodes)} 个节点用于丰富图结构")

            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    node1 = nodes[i]
                    node2 = nodes[j]
                    # 将frozenset转换为set，再获取其中唯一的标签元素
                    node1_label = set(node1.labels).pop()
                    node2_label = set(node2.labels).pop()
                    node1_properties = dict(node1)
                    node2_properties = dict(node2)

                    relation_description = self.get_relation_description(node1_label, node1_properties, node2_label,
                                                                         node2_properties)
                    if relation_description:
                        print(f"正在为节点 {node1_label} 和 {node2_label} 的关系添加描述: {relation_description}")
                        # 在Neo4j中查找或创建两节点间的关系，并添加关系描述属性
                        query = """
                        MATCH (n1 {name: $node1_name})-[r]-(n2 {name: $node2_name})
                        SET r.relation_description = $relation_description
                        RETURN r
                        """
                        session.run(query, node1_name=node1_properties.get('name'),
                                    node2_name=node2_properties.get('name'),
                                    relation_description=relation_description)
                    else:
                        print(f"无法获取节点 {node1_label} 和 {node2_label} 之间的关系描述，跳过此对节点")

    def _generate_node_pair_key(self, node1_label, node1_properties, node2_label, node2_properties):
        """
        生成用于标识节点对的唯一键，用于在json文件中存储和读取关系描述。

        :param node1_label: 第一个节点的标签
        :param node1_properties: 第一个节点的属性
        :param node2_label: 第二个节点的标签
        :param node2_properties: 第二个节点的属性
        :return: 节点对的唯一键（字符串形式）
        """
        node1_key = f"{node1_label}_{json.dumps(node1_properties)}"
        node2_key = f"{node2_label}_{json.dumps(node2_properties)}"
        return sorted([node1_key, node2_key])[0] + "_" + sorted([node1_key, node2_key])[1]

    def _load_relation_description_from_json(self, node_pair_key):
        """
        从json文件中加载指定节点对的关系描述。

        :param node_pair_key: 节点对的唯一键
        :return: 关系描述（字符串形式），如果文件不存在或节点对描述不存在则返回None
        """
        if os.path.exists(RELATION_DESCRIPTION_FILE):
            with open(RELATION_DESCRIPTION_FILE, 'r',encoding="UTF-8") as file:
                relation_descriptions = json.load(file)
                return relation_descriptions.get(node_pair_key)
        return None

    def _save_relation_description_to_json(self, node_pair_key, relation_description):
        """
        将节点对的关系描述保存到json文件中。

        :param node_pair_key: 节点对的唯一键
        :param relation_description: 关系描述（字符串形式）
        """
        relation_descriptions = {}
        if os.path.exists(RELATION_DESCRIPTION_FILE):
            with open(RELATION_DESCRIPTION_FILE, 'r',encoding="UTF-8") as file:
                relation_descriptions = json.load(file)

        relation_descriptions[node_pair_key] = relation_description

        with open(RELATION_DESCRIPTION_FILE, 'w') as file:
            json.dump(relation_descriptions, file, indent=4)

if __name__ == "__main__":
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "12345678"
    api_key = "YOUR_API_KEY"  # 替换为真实的OpenAI API密钥

    graph_enricher = GraphEnricher(neo4j_uri, neo4j_user, neo4j_password, api_key)
    graph_enricher.enrich_schema_graph()
    graph_enricher.close_connections()