import os
import time

from tqdm import tqdm

import config
from graph_construction.neo4j_data_migration import load_graph_to_neo4j
from schema_enricher.utils.description_generator import TableSchemaDescriber
from schema_enricher.utils.description_injector import inject_descriptions
from schema_enricher.utils.fk_filler import FKFiller


class Enricher:
    """
    Enricher 类用于增强数据库的元信息，包括：
    1. 为表和列生成描述信息。
    2. 在外键连接不全的情况下，基于业务逻辑推断可能的外键关系。
    """

    def __init__(self, dataset_name):
        """
        初始化 Enricher。

        :param ds_root: 数据集根目录
        :param log_file: 处理日志存储路径。
        """
        self.ds_root = config.GRAPHS_REPO
        self.log_file = os.path.join(config.SCHEMA_ENRICHER, "Enrich_Process.log")
        self.dataset_name = dataset_name
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)  # 确保日志文件夹存在

    def log(self, message: str):
        """ 记录日志信息到文件并打印到控制台 """
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_msg = f"[{timestamp}] {message}"
        with open(self.log_file, "a", encoding="utf-8") as log:
            log.write(log_msg + "\n")
        print(log_msg)

    def enrich_description(self, db_path: str):
        """
        生成指定数据库的表描述，并记录日志。

        :param db_path: 数据库文件夹路径。
        """
        db_name = os.path.basename(db_path)  # 数据库名称
        description_file = os.path.join(config.GENERATED_DESCRIPTIONS, self.dataset_name, f"{db_name}.json")

        # 1. 检查是否已存在描述文件
        if os.path.exists(description_file):
            self.log(f"⏩ 跳过 {db_name}，描述文件已存在。")
            return

        self.log(f"🚀 开始处理数据库: {db_name}")

        describer = TableSchemaDescriber(db_path)

        try:
            describer.describe_database()
            self.log(f"✅ {db_name} 处理完成！")
        except Exception as e:
            self.log(f"❌ 处理 {db_name} 时发生错误: {e}")

    def infer_foreign_keys(self, dataset_name, db_name):
        """
        （占位函数）用于推断数据库的外键关系，并补充到数据库模式中。
        """
        try:
            fk_filler = FKFiller(dataset_name, db_name)
            fk_filler.preprocess()
            self.log(f"✅ {db_name} 的外键关系推断完成！")
        except Exception as e:
            self.log(f"❌ 处理 {db_name} 的外键关系时发生错误: {e}")

    def enrich_schema(self):
        """
        遍历数据集目录，对所有数据库执行 enrich_description。

        :param dataset_name: 数据集名称，必须是 'spider' 或 'bird'。
        """
        dataset_name = self.dataset_name
        if dataset_name not in {"spider", "bird"}:
            raise ValueError("dataset_name 必须是 'spider' 或 'bird'")

        ds_path = os.path.join(self.ds_root, dataset_name)

        if not os.path.exists(ds_path):
            raise FileNotFoundError(f"❌ 数据集目录不存在: {ds_path}")

        self.log(f"📂 开始处理数据集: {dataset_name}，路径: {ds_path}")

        db_folders = [os.path.join(ds_path, db) for db in os.listdir(ds_path) if
                      os.path.isdir(os.path.join(ds_path, db))]

        for db_path in tqdm(db_folders, desc=f"Processing {dataset_name} databases"):
            db_name = os.path.basename(db_path)
            # # 1. 对每个数据库执行 description生成，已完成可注释
            # self.enrich_description(db_path)
            # 2. 对每个数据库执行 description注入
            # inject_descriptions(dataset_name, db_name)
            # 3. 为每个数据库缺失外键进行预处理
            self.infer_foreign_keys(dataset_name, db_name)
            pass

        self.log(f"🎉 数据集 {dataset_name} 处理完成！")


if __name__ == "__main__":
    """
    所有步骤写在enrich_schema函数中，调用一次就自动完成enrich的所有步骤,只需传入数据集名称即可。
    """
    # enricher = Enricher("spider")  # 处理 spider 数据集
    enricher = Enricher("bird")  # 处理 bird 数据集
    enricher.enrich_schema()

    # #查看neo4j。动态测试效果
    # load_graph_to_neo4j("spider", "academic")
