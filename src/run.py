import os

from graph_construction.neo4j_data_migration import export_all
from graph_construction.schema_parser import SchemaParser
from src.neo4j_connector import get_driver


def traverse_folders(root_folder):
    # 存储所有数据库文件夹名的列表
    db_folder_names = []
    for dir_name in os.listdir(root_folder):
        dir_path = os.path.join(root_folder, dir_name)
        if os.path.isdir(dir_path):
            db_folder_names.append(dir_name)
            sqlite_path = os.path.join(root_folder, dir_name, dir_name + '.sqlite')
            print(dir_name)
            # print(sqlite_path)
            # 调用 run 函数处理 sqlite 路径
            run(sqlite_path)
    return db_folder_names


def run(sqlite_path):
    parser = SchemaParser(neo4j_driver, sqlite_path)
    try:
        parser.parse_and_store_schema()
        print("Schema parsing and storing completed successfully.")
        # 导出存储schema graph
        exp_path = os.path.join("..\graphs_repo", os.path.join(parser.extract_dataset_name(sqlite_path),
                                                               parser.extract_database_name(sqlite_path)))
        export_all(exp_path)
        print("成功导出！")
    except Exception as e:
        print("Error occurred during schema parsing and storing:", e)
        print("失败！！！！！！！！！！！！！！！！！！！！！！！！！！")
    parser.close_connections()


if __name__ == "__main__":
        # 创建 Neo4j 驱动连接
        neo4j_driver = get_driver()

        # 请将 'root_folder' 替换为你想要遍历的文件夹的实际路径
        # BIRD 训练集路径
        root_folder = 'E:/BIRD_train/train/train_databases'
        # SPIDER 训练集路径
        # root_folder = 'E:/spider/database'
        traverse_folders(root_folder)
