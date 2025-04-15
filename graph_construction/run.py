import os
import time

from graph_construction.neo4j_data_migration import export_all
from graph_construction.schema_parser import SchemaParser
from src.neo4j_connector import get_driver
import config

from tqdm import tqdm


def traverse_folders(root_folder):
    # 存储所有数据库文件夹名的列表
    db_folder_names = []

    # 先获取所有目录列表
    dir_list = [d for d in os.listdir(root_folder)
                if os.path.isdir(os.path.join(root_folder, d))]

    # 使用tqdm添加进度条
    for dir_name in tqdm(dir_list, desc="Processing databases", unit="db"):
        dir_path = os.path.join(root_folder, dir_name)
        db_folder_names.append(dir_name)

        sqlite_path = os.path.join(root_folder, dir_name, dir_name + '.sqlite')
        print(f"\n当前处理: {dir_name}")  # 保留单独打印当前处理的数据库名

        # 调用 run 函数处理 sqlite 路径
        run(sqlite_path)

    return db_folder_names


def run(sqlite_path):
    parser = SchemaParser(neo4j_driver, sqlite_path)
    max_attempts = 5
    attempt = 0
    success = False

    while attempt < max_attempts and not success:
        attempt += 1
        try:
            parser.parse_and_store_schema()
            print("Schema parsing and storing completed successfully.")

            # 导出存储schema graph
            exp_path = os.path.join(config.GRAPHS_REPO,
                                    os.path.join(parser.extract_dataset_name(sqlite_path),
                                                 parser.extract_database_name(sqlite_path)))
            print(exp_path)
            export_all(exp_path)
            print("✅ 成功导出！")
            success = True

        except Exception as e:
            print(f"第 {attempt} 次尝试失败，错误信息: {str(e)}")
            if attempt < max_attempts:
                retry_delay = min(2 ** attempt, 10)  # 指数退避，最大10秒
                print(f"将在 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                print("⛔ 所有尝试均失败！最后错误信息:", str(e))
                print("⛔ 失败！！！！！！！！！！！！！！！！！！！！！！！！！！")
        finally:
            if not success and attempt == max_attempts:
                parser.close_connections()
            elif success:
                parser.close_connections()


if __name__ == "__main__":
    # 创建 Neo4j 驱动连接
    neo4j_driver = get_driver()

    # 请将 'root_folder' 替换为你想要遍历的文件夹的实际路径

    # BIRD 开发集路径
    root_folder = config.BIRD_DEV_DATABASES_PATH
    traverse_folders(root_folder)

    # # BIRD 训练集路径
    # root_folder = config.BIRD_TRAIN_DATABASES_PATH
    # traverse_folders(root_folder)

    # # SPIDER 训练集路径
    # root_folder = config.SPIDER_DATABASES_PATH
    # traverse_folders(root_folder)
