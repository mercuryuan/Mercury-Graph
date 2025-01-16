from neo4j import GraphDatabase

# 全局变量用于存储驱动实例
_driver = None

def get_driver():
    global _driver
    if _driver is None:
        uri = "bolt://localhost:7689"
        username = "neo4j"
        password = "12345678"
        _driver = GraphDatabase.driver(uri, auth=(username, password))
    return _driver