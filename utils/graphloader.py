"""
Graph Loader Module 🚀

This module provides functionality to load a database schema graph into Neo4j.

Main Components:
- `GraphLoader`: A class responsible for connecting to Neo4j and loading the database schema graph.
- `get_driver()`: Establishes a connection to the Neo4j database.
- `load_graph_to_neo4j(dataset_name, db_name)`: Loads the specified dataset's schema into Neo4j.
"""
import os
from graph_construction.neo4j_data_migration import load_graph_to_neo4j
from src.neo4j_connector import get_driver
import logging


class GraphLoader:
    def __init__(self):
        """初始化 GraphLoader，获取 Neo4j 驱动"""
        try:
            self.driver = get_driver()  # 获取连接（每个进程会有独立的 driver）
            if self.driver:
                print("🚀 Successfully connected to Neo4j! 🎉")
            else:
                print("❌ Failed to establish Neo4j connection. ⚠️")
        except Exception as e:
            print(f"🚨 Error in GraphLoader initialization: {e} ❗")

    def load_graph(self, dataset_name, db_name):
        """加载指定数据集的数据库架构到 Neo4j（带重试机制）"""
        max_retries = 10
        for attempt in range(max_retries):
            try:
                print(f"⏳ Loading graph for dataset: {dataset_name}, database: {db_name}...")
                # 调用迁移函数，将架构加载到 Neo4j
                self.graph = load_graph_to_neo4j(dataset_name, db_name)
                print("Graph loaded successfully! 🏆")
                return  # 成功则退出函数
            except Exception as e:
                print(f"🚨 Attempt {attempt + 1}/{max_retries} failed: {e} ❗")
                if attempt == max_retries - 1:  # 最后一次尝试仍然失败
                    print("🚨 All retries exhausted. Failing permanently...")
                    raise  # 抛出异常，终止程序


if __name__ == '__main__':
    dataset_name = "bird"
    # dataset_name = "spider"

    # db_name = "activity_1"
    # db_name = "books"
    # db_name = "regional_sales"
    # db_name = "soccer_1"
    # db_name = "mondial_geo"
    # db_name = "geo"
    # db_name = "shakespeare"
    # db_name = "imdb"
    # db_name = "trains"
    # db_name = "synthea"
    # db_name = "baseball_1"  # 很多孤儿节点
    # db_name = "academic"  # 有孤儿节点
    # db_name = "activity_1"  # 无孤儿节点
    # db_name = "bike_1"  # 2孤儿节点
    # db_name = "disney"  #
    # db_name = "talkingdata"  #
    # db_name = "works_cycles"  #
    # db_name = "e_government"  #
    # db_name = "imdb"  #
    db_name = "college_2"  # 1孤儿节点
    # db_name = "company_1"  # 全是孤儿节点
    # db_name = "customers_card_transactions"  # 孤儿节点
    # db_name = "customers_card_transactions"  # 孤儿节点
    # db_name = "cookbook"
    # db_name = "hockey"
    # db_name = "formula_1"
    # db_name = "real_estate_properties"
    # db_name = "card_games"
    db_name = "california_schools"

    loader = GraphLoader()
    loader.load_graph(dataset_name, db_name)
