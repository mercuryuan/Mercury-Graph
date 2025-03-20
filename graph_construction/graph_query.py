import json
import os
from collections import defaultdict

import config


class GraphQuery:
    def __init__(self, dataset, dataname):
        self.dataset = dataset
        self.dataname = dataname
        self.db_path = os.path.join(config.GRAPHS_REPO, dataset, dataname)
        self.nodes = []
        self.relationships = []
        self.tables = {}  # 表名到表节点的映射
        self.columns = {}  # 列ID到列节点的映射
        self.table_columns_map = defaultdict(dict)  # 表名到列名->列节点的映射

        self._load_data()
        self._process_nodes()
        self._process_relationships()
        self._build_table_columns()

    def _load_data(self):
        """加载nodes和relationships的JSON数据"""
        base_dir = self.db_path
        try:
            with open(os.path.join(base_dir, 'nodes.json'), 'r') as f:
                self.nodes = json.load(f)
            with open(os.path.join(base_dir, 'relationships.json'), 'r') as f:
                self.relationships = json.load(f)
        except Exception as e:
            raise FileNotFoundError(f"加载数据失败: {str(e)}")

    def _process_nodes(self):
        """预处理节点数据，分类表和列"""
        for node in self.nodes:
            labels = node.get('labels', [])
            if 'Table' in labels:
                self.tables[node['properties']['name']] = node
            elif 'Column' in labels:
                self.columns[node['old_id']] = node

    def _process_relationships(self):
        """处理关系数据，建立表-列关联"""
        self.relation_map = defaultdict(list)
        for rel in self.relationships:
            if rel['type'] == 'HAS_COLUMN':
                self.relation_map[rel['start_old_id']].append(rel['end_old_id'])

    def _build_table_columns(self):
        """为每个表建立列名到列属性的映射"""
        for table_name, table_node in self.tables.items():
            table_id = table_node['old_id']
            for col_id in self.relation_map.get(table_id, []):
                col_node = self.columns.get(col_id)
                if col_node:
                    col_name = col_node['properties']['name']
                    self.table_columns_map[table_name][col_name] = col_node['properties']

    def get_column_info(self, table_name, column_name):
        """查询指定表的列详细信息"""
        if table_name not in self.tables:
            return None
        return self.table_columns_map.get(table_name, {}).get(column_name)

    def get_table_info(self, table_name):
        """查询表节点信息"""
        table_node = self.tables.get(table_name)
        return table_node['properties'] if table_node else None
    def col_infos_for_fk(self):
        """
        查询所有表的列详细信息，并返回信息字典的列表。
        每个字典包含表名、列名、数据类型、是否为空、描述和采样值。
        """
        result = []
        # 遍历每个表及其对应的列信息
        for table_name, columns in self.table_columns_map.items():
            # 遍历每个列及其对应的属性信息
            for col_name, col_info in columns.items():
                # 构建包含列详细信息的字典
                col_info_dict = {
                    "table_name": table_name,
                    "column_name": col_name,
                    "data_type": col_info.get('data_type'),
                    "is_nullable": col_info.get('is_nullable'),
                    "description": col_info.get('description'),
                    "samples": col_info.get('samples')
                }
                # 将字典添加到结果列表中
                result.append(col_info_dict)
        return result



if __name__ == '__main__':
    # 初始化查询器
    query = GraphQuery("spider", "bike_1")

    # # 查询表信息
    # table_info = query.get_table_info("station")
    # print(table_info)
    # print("表信息:", table_info['description'])
    #
    # # 查询列信息
    # column_info = query.get_column_info("station", "installation_date")
    # print(column_info)
    # print(column_info['name'])
    # print(column_info['data_type'])
    # print(column_info['samples'])
    # print(column_info['is_nullable'])
    # print(column_info['description'])

    # 查询所有列信息
    all_columns_info = query.col_infos_for_fk()
    print(all_columns_info)
    for info in all_columns_info:
        print(info)