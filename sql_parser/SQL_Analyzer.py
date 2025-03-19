import time

from src.neo4j_connector import get_driver
from utils.dataloader import DataLoader
from utils.graphloader import GraphLoader
from utils.sql_parser import SqlParserTool


class SQLAnalyzer:
    def \
            __init__(self, dataset_name, db_name, name_correction=True):
        self.driver = get_driver()
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.tool = SqlParserTool(dataset_name, db_name, name_correction)  # 传递 name_correction 参数
        # 切换neo4j到当前数据库，已进行对照验证
        self.gloader = GraphLoader()
        self.gloader.load_graph(self.dataset_name, self.db_name)
        if name_correction:
            self.summary_log = "./analysis_summaries.log"
        else:
            self.summary_log = "./analysis_summaries_without_correction.log"

    def analyze_sql_query(self, entry, output_mode="pass_basic_fail_full"):
        """ 分析单个 SQL 条目，并在 Neo4j 中验证 """
        question = entry.get('question')
        db_id = entry.get('db_id')
        sql = entry.get('sql')

        if not sql:
            return False
        """ 使用 SqlParserTool 解析 SQL 语句 """
        is_valid_in_neo4j = self.tool.display_parsing_result(sql, question, db_id, output_mode)  # 移除 name_correction 参数
        return is_valid_in_neo4j

    def analyze_sql_data(self, data_list, output_mode):
        """ 处理 SQL 数据列表，并统计通过 Neo4j 验证的数量 """
        print(f"开始处理 SQL 数据，共 {len(data_list)} 条记录。")
        print('-' * 80)
        self.tool.log(f"开始处理 SQL 数据，共 {len(data_list)} 条记录。")
        self.tool.log('-' * 80)

        passed_count = 0
        try:
            for index, entry in enumerate(data_list, start=1):
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                print(f"开始处理第 {index}/{len(data_list)} 条记录...")
                self.tool.log(f"[{timestamp}]")
                self.tool.log(f"开始处理第 {index}/{len(data_list)} 条记录...")
                try:
                    if self.analyze_sql_query(entry, output_mode):  # 移除 name_correction 参数
                        passed_count += 1
                except Exception as e:
                    print(f"第 {index} 条记录处理失败: {e}")
                print('-' * 120)
                self.tool.log('-' * 120)
        finally:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            summary = f"[{timestamp}]通过 Neo4j 验证的 SQL 语句数: \t{passed_count}/{len(data_list)}\t{self.dataset_name}\t{self.db_name}"
            print(summary)
            self.tool.log(summary)
            self.tool.log(summary, self.summary_log)

    def analyze_sql_by_database(self, output_mode):
        """
        通过数据库名称筛选数据并分析 SQL。
        output_mode (str, 可选): 输出模式，支持以下三种：
                - "full_output": 按原来的方式全部输出和记录解析结果。
                - "pass_basic_fail_full": 仅输出和记录 validate_cypher_query 不通过的全量信息，
                                          对于通过的只输出和记录基本信息。
                - "pass_silent_fail_full": 通过的不输出和记录信息，对于不通过的输出和记录全量信息。
        """
        # 1. 创建 DataLoader 实例并加载指定数据集数据，可以通过loader获取数据
        loader = DataLoader(self.dataset_name)
        # 2. 通过loader获取 指定database_name下的字段["db_id", "sql", "question"]，存至data中
        data = loader.filter_data(db_id=self.db_name, fields=["db_id", "sql", "question"])
        # 3.对data进行分析sql语句分析，获得实体关系分析、neo4j对应子图的查询语句，进行neo4j验证
        self.analyze_sql_data(data, output_mode)  # 移除 name_correction 参数


if __name__ == "__main__":
    # # 分析单个数据库
    # analyzer = SQLAnalyzer("spider", "music_2")
    # analyzer.analyze_sql_by_database(output_mode="full_output")
    # # 分析单个数据库,不开启名称矫正
    # analyzer = SQLAnalyzer("bird", "shipping",False)
    # analyzer.analyze_sql_by_database(output_mode="full_output")

    # 遍历分析spider所有数据库
    dataset = "spider"
    for database in DataLoader(dataset).list_dbname(show=False):
        analyzer = SQLAnalyzer(dataset, database, name_correction=True)  # 传递 name_correction 参数
        # "full_output": 全部输出和记录解析结果。
        # "pass_basic_fail_full": 仅对通过的全量输出和记录
        # "pass_silent_fail_full": 仅对于不通过的输出和记录全量信息。
        analyzer.analyze_sql_by_database(output_mode="full_output")

    # 遍历分析 bird 所有数据库
    dataset = "bird"
    for database in DataLoader(dataset).list_dbname(show=False):
        analyzer = SQLAnalyzer(dataset, database, name_correction=True)  # 传递 name_correction 参数
        analyzer.analyze_sql_by_database(output_mode="full_output")