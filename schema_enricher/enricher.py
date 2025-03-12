import os
import json
import time

from description_generator import TableSchemaDescriber

class Enricher:
    """
    Enricher 类用于增强数据库的元信息，包括：
    1. 为表和列生成描述信息。
    2. 在外键连接不全的情况下，基于业务逻辑推断可能的外键关系。
    """

    def __init__(self, ds_path: str, log_file: str = "./Enrich_Process.log"):
        """
        初始化 Enricher。

        :param ds_path: 数据集的根目录，包含多个数据库文件夹。
        :param log_file: 日志文件路径，记录 enrich 过程。
        """
        self.ds_path = ds_path
        self.log_file = log_file
        os.makedirs(os.path.dirname(log_file), exist_ok=True)  # 确保日志文件目录存在

    def enrich_description(self, db_path: str):
        """
        生成指定数据库的表描述，并记录日志。

        :param db_path: 数据库文件夹路径。
        """
        describer = TableSchemaDescriber(db_path)
        db_name = os.path.basename(db_path)  # 数据库名称
        description_file = f"./generated_descriptions/{db_name}.json"
        start_time = time.strftime("%Y-%m-%d %H:%M:%S")  # 记录开始时间

        with open(self.log_file, "a", encoding="utf-8") as log:  # 追加模式
            # 1. 检查是否已存在描述文件
            if os.path.exists(description_file):
                log.write(f"[{start_time}] ⏩ 跳过 {db_path}，描述文件已存在。\n")
                print(f"[{start_time}] ⏩ 跳过 {db_path}，描述文件已存在。")
                return

            log.write(f"[{start_time}] 🚀 开始处理数据库: {db_path}\n")
            print(f"[{start_time}] 🚀 开始处理数据库: {db_path}")

            try:
                describer.describe_database()
                end_time = time.strftime("%Y-%m-%d %H:%M:%S")  # 记录结束时间
                log.write(f"[{end_time}] ✅ {db_path} 处理完成！\n")
                print(f"[{end_time}] ✅ {db_path} 处理完成！")
            except Exception as e:
                error_msg = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ❌ 处理 {db_path} 时发生错误: {e}\n"
                log.write(error_msg)
                print(error_msg)

    def infer_foreign_keys(self):
        """
        （占位函数）用于推断数据库的外键关系，并补充到数据库模式中。
        """
        print("🔍 外键推断功能待实现...")

    def enrich_schema(self):
        """
        遍历数据集根目录，对每个数据库文件夹执行 enrich_description()。
        """
        if not os.path.exists(self.ds_path):
            print(f"❌ 数据集目录 {self.ds_path} 不存在！")
            return

        with open(self.log_file, "a", encoding="utf-8") as log:  # 追加模式
            log.write(f"📂 开始处理数据集目录: {self.ds_path}\n")

        for db_name in os.listdir(self.ds_path):
            db_path = os.path.join(self.ds_path, db_name)

            if os.path.isdir(db_path):  # 只处理文件夹（数据库目录）
                self.enrich_description(db_path)

        with open(self.log_file, "a", encoding="utf-8") as log:
            log.write("🏁 数据集处理完成！\n")
        print("🏁 数据集处理完成！")

if __name__ == '__main__':
    ds_path = '../graphs_repo/spider'
    # 遍历数据集目录，对每个数据库执行 enrich_description()
    enricher = Enricher(ds_path)
    enricher.enrich_schema()