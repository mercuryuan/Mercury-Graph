"""
Graph Loader Module 🚀

This module provides functionality to load a database schema graph into Neo4j.

Main Components:
- `GraphLoader`: A class responsible for connecting to Neo4j and loading the database schema graph.
- `get_driver()`: Establishes a connection to the Neo4j database.
- `load_graph_to_neo4j(dataset_name, db_name)`: Loads the specified dataset's schema into Neo4j.
"""
from graph_construction.neo4j_data_migration import load_graph_to_neo4j
from src.neo4j_connector import get_driver


class GraphLoader:
    def __init__(self):
        print("🚀 Initializing GraphLoader...")

        try:
            self.driver = get_driver()
            if self.driver:
                print("✅ Successfully connected to Neo4j! 🎉")
            else:
                print("❌ Failed to establish Neo4j connection. ⚠️")
        except Exception as e:
            print(f"🚨 Error in GraphLoader initialization: {e} ❗")

    def load_graph(self, dataset_name, db_name):
        """Loads the specified dataset's schema into Neo4j."""
        try:
            print(f"⏳ Loading graph for dataset: {dataset_name}, database: {db_name} ...")
            self.graph = load_graph_to_neo4j(dataset_name, db_name)
            print("✅ Graph loaded successfully! 🏆")
        except Exception as e:
            print(f"🚨 Error in loading graph: {e} ❗")


if __name__ == '__main__':
    dataset_name = "spider"
    db_name = "hr_1"
    loader = GraphLoader()
    loader.load_graph(dataset_name, db_name)
