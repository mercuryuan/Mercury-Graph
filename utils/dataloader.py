import json
from typing import Optional, List

from config import SPIDER_TRAIN_JSON, SPIDER_DEV_JSON, SPIDER_TRAIN_OTHER_JSON, BIRD_TRAIN_JSON, SPIDER, BIRD_DEV_JSON


class DataLoader:
    """通用数据加载器，支持 SPIDER 和 BIRD 数据集"""

    DATASETS = {
        "spider_dev": SPIDER_DEV_JSON,
        "spider": SPIDER,
        "spider_train": SPIDER_TRAIN_JSON,
        "spider_other": SPIDER_TRAIN_OTHER_JSON,
        "bird": BIRD_TRAIN_JSON,
        "bird_dev": BIRD_DEV_JSON,
    }

    def __init__(self, dataset_name):
        """初始化时加载指定数据集
            (spider,spider_dev,spider_train，spider_other，bird，bird_dev)
        """
        if dataset_name not in self.DATASETS:
            raise ValueError(f"未知数据集: {dataset_name}，支持的选项: {list(self.DATASETS.keys())}")

        self.dataset_name = dataset_name
        if self.dataset_name == "spider":
            self.data = self.merge_json_files(SPIDER_TRAIN_JSON,SPIDER_TRAIN_OTHER_JSON)
        else:
            self.data = self._load_data(self.DATASETS[dataset_name])

    def _load_data(self, file_path):
        """从 JSON 文件加载数据"""
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def merge_json_files(self, file_path1, file_path2):
        """
        合并两个结构相同的 JSON 文件。

        参数:
            file_path1 (str): 第一个 JSON 文件的路径。
            file_path2 (str): 第二个 JSON 文件的路径。

        返回:
            list: 合并后的 JSON 数据列表。
        """
        data1 = self._load_data(file_path1)
        data2 = self._load_data(file_path2)
        return data1 + data2

    def filter_data(self, db_id: Optional[str] = None, fields: Optional[List[str]] = None, show_count: bool = False):
        """
        过滤数据，支持按数据库筛选，并提取指定字段 (值得注意的是，函数统一了不同数据集的 SQL 字段名为 "sql")
        :param db_id: 需要查询的数据库名（可选，默认全部）
        :param fields: 需要提取的字段列表（可选，默认全部）
        :param show_count: 是否显示筛选后数据条数（默认 False）
        :return: 过滤后的数据
        """
        # 统一不同数据集的 SQL 相关字段名
        sql_aliases = {"query", "sql", "SQL"}  # Spider: "query"，Bird: "SQL"

        # 过滤数据库 ID
        if db_id:
            filtered = [item for item in self.data if item["db_id"] == db_id]
        else:
            filtered = self.data  # 默认返回所有数据

        if show_count:
            print(f"筛选出的数据条数: {len(filtered)}")

        # 处理 fields 参数，使其匹配不同数据集的 SQL 字段
        normalized_fields = set(fields) if fields else None
        if normalized_fields and "sql" in normalized_fields:
            normalized_fields.update(sql_aliases)  # 如果用户请求 "sql"，那么 "query" 和 "SQL" 也要被包含
            normalized_fields.remove("sql")  # 只用于匹配，不影响最终 key 命名

        processed_data = []
        for item in filtered:
            new_item = {}
            for k, v in item.items():
                # 统一 SQL 相关字段名
                new_key = "sql" if k in sql_aliases else k

                # 只保留用户指定的字段
                if not normalized_fields or k in normalized_fields:
                    new_item[new_key] = v

            processed_data.append(new_item)

        return processed_data

    def show_json_structure(self):
        """展示 JSON 结构"""
        if not self.data:
            print("数据为空！")
            return

        sample = self.data[0]  # 取第一条数据作为示例
        print(f"数据集: {self.dataset_name} 的 JSON 结构如下：")
        self._print_structure(sample)

    def _print_structure(self, item, indent=0):
        """递归解析 JSON 结构"""
        for key, value in item.items():
            prefix = " " * indent
            if isinstance(value, dict):
                print(f"{prefix}- {key}: dict")
                self._print_structure(value, indent + 4)
            elif isinstance(value, list):
                if len(value) > 0 and isinstance(value[0], dict):
                    print(f"{prefix}- {key}: list of dict")
                    self._print_structure(value[0], indent + 4)
                else:
                    print(f"{prefix}- {key}: list ({type(value[0]).__name__ if value else 'empty'})")
            else:
                print(f"{prefix}- {key}: {type(value).__name__}")

    def list_dbname(self,show = True):
        """获取数据集中所有唯一的 db_id"""
        db_list = {d.get("db_id") for d in self.filter_data(fields=["db_id"]) if "db_id" in d}

        db_list = sorted(db_list)  # 排序，方便查看
        if show:
            print(f"数据库列表 ({len(db_list)} 个): " + "\n".join(db_list))

        return db_list  # 返回数据库名列表


if __name__ == '__main__':
    # 加载 SPIDER 训练集
    spider_loader = DataLoader("spider")

    # 显示 JSON 结构
    # loader.show_json_structure()

    # 过滤查询并显示条数
    # filtered_queries = spider_loader.filter_data(fields=["db_id", "sql", "question"],
    #                                              show_count=True)
    # print(filtered_queries[:10])

    # 读取 BIRD 数据集
    bird_loader = DataLoader("bird")
    all_bird_data = bird_loader.filter_data(db_id="superstore",fields=["db_id", "sql", "question"],show_count=True)
    print(all_bird_data)

    # spider_loader.list_dbname()
    # bird_loader.list_dbname()
