from neo4j import GraphDatabase
from src.neo4j_connector import get_driver


class DatabaseGraphHandler:
    def __init__(self, neo4j_driver):
        """
        初始化数据库图处理器。

        :param neo4j_driver: Neo4j驱动器实例
        """
        self.neo4j_driver = neo4j_driver

    def get_table_node_properties_by_name(self, table_name):
        """
        根据表名获取表节点的所有属性以及节点的ID，将ID归入属性并返回，并添加节点标签。
        仅在查询失败时发出提示。

        :param table_name: 表名
        :return: 包含表节点所有属性和标签的字典，ID被归为属性的一部分，如果表节点不存在则返回None
        """
        query = """
        MATCH (t:Table {name: $table_name})
        RETURN  properties(t) AS props, labels(t) AS labels
        """
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query, table_name=table_name).single()
                if result:
                    labels = result["labels"]
                    if labels:
                        # 将 labels 合并到属性字典中，添加验证逻辑
                        result["props"]["labels"] = labels[0]
                    return result["props"]
                else:
                    print(f"Warning: No node found for table name '{table_name}'.")
                    return None
        except Exception as e:
            print(f"Error: Failed to execute query for table '{table_name}'. Error: {str(e)}")
            return None

    def get_node_properties_by_id(self, node_id):
        """
        根据节点的ID查询并返回节点的所有属性，并添加节点标签。
        仅在查询失败时发出提示。

        :param node_id: 节点ID
        :return: 包含节点所有属性和标签的字典，ID被归为属性的一部分，如果节点不存在则返回None
        """
        query = """
        MATCH (t)
        WHERE ID(t) = $node_id
        RETURN id(t) AS id, properties(t) AS props, labels(t) AS labels
        """
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query, node_id=node_id).single()
                if result:
                    labels = result["labels"]
                    if labels:
                        # 将 id 和 labels 合并到属性字典中，添加验证逻辑
                        result["props"]["id"] = result["id"]
                        result["props"]["labels"] = labels[0]
                    return result["props"]
                else:
                    print(f"Warning: No node found with ID '{node_id}'.")
                    return None
        except Exception as e:
            print(f"Error: Failed to execute query for node ID '{node_id}'. Error: {str(e)}")
            return None

    def get_column_node_properties_by_name(self, table_name, column_name):
        """
        根据表名和列名获取列节点的所有属性，并添加节点标签。
        仅在查询失败时发出提示。

        :param table_name: 表名
        :param column_name: 列名
        :return: 包含列节点所有属性和标签的字典，ID被归为属性的一部分，如果列节点不存在则返回None
        """
        query = """
        MATCH (t:Table {name: $table_name})-[:HAS_COLUMN]->(c:Column {name: $column_name})
        RETURN  properties(c) AS props, labels(c) AS labels
        """
        try:
            with self.neo4j_driver.session() as session:
                result = session.run(query, table_name=table_name, column_name=column_name).single()
                if result:
                    labels = result["labels"]
                    if labels:
                        # 将labels 合并到属性字典中，添加验证逻辑
                        result["props"]["labels"] = labels[0]
                    return result["props"]
                else:
                    print(f"Warning: No column node found for table '{table_name}' and column '{column_name}'.")
                    return None
        except Exception as e:
            print(f"Error: Failed to execute query for column '{column_name}' in table '{table_name}'. Error: {str(e)}")
            return None

    def get_table_and_all_column_nodes_by_table_name(self, table_name):
        """
        根据表名查找表节点以及其所有的列节点，返回包含表节点属性和所有列节点属性的字典列表。

        :param table_name: 表名
        :return: 字典列表，第一个字典是表节点的属性（包含标签和ID等），后续字典是对应的列节点的属性（包含标签和ID等），
                 如果表节点不存在则返回空列表，如果表节点存在但没有列节点则只返回表节点属性字典
        """
        table_node_props = self.get_table_node_properties_by_name(table_name)
        if table_node_props is None:
            return []
        result_list = [table_node_props]
        columns = table_node_props.get("columns", [])
        for column in columns:
            column_props = self.get_column_node_properties_by_name(table_name, column)
            if column_props:
                result_list.append(column_props)
        return result_list


if __name__ == '__main__':

    # 创建 Neo4j 驱动连接
    driver = get_driver()
    # 使用 DatabaseGraphHandler 类
    handler = DatabaseGraphHandler(driver)
    try:
        # 通过表名获取表节点及其所有列节点属性
        # result = handler.get_table_and_all_column_nodes_by_table_name("Orders")
        result = handler.get_table_and_all_column_nodes_by_table_name("hall_of_fame")
        if result:
            for node_props in result:
                print(node_props)

    finally:
        # 确保正确关闭驱动连接
        driver.close()
