from src.neo4j_connector import get_driver
from utils.dataloader import DataLoader
from utils.graphloader import GraphLoader
from utils.sql_parser import SqlParserTool


class SQLAnalyzer:
    def __init__(self,dataset_name, db_name):
        self.driver = get_driver()
        self.dataset_name = dataset_name
        self.db_name = db_name
        self.tool = SqlParserTool(dataset_name, db_name)
        # 切换neo4j到当前数据库，已进行对照验证
        self.gloader = GraphLoader()
        self.gloader.load_graph(self.dataset_name, self.db_name)

    def analyze_sql_query(self, sql, question=None, db_id=None):
        """ 使用 SqlParserTool 解析 SQL 语句 """
        self.tool.parse_and_display(sql, question, db_id)

    def analyze_single_sql_in_entry(self, entry, session):
        """ 分析单个 SQL 条目，并在 Neo4j 中验证 """
        question = entry.get('question')
        db_id = entry.get('db_id')
        sql = entry.get('sql')

        if not sql:
            return False

        try:
            self.analyze_sql_query(sql, question, db_id)
            # entities, relationships = self.tool.extract_entities_and_relationships(sql)
            # name correction默认为开，进行表列名修正
            # cypher_query = self.tool.sql2subgraph(entities, relationships,False)
            # session.run(cypher_query)
            return True
        except Exception as e:
            print(f"处理 {db_id or '未知'} 数据时的 Cypher 查询失败:\n{e}")
            return False

    def analyze_sql_data(self, data_list):
        """ 处理 SQL 数据列表，并统计通过 Neo4j 验证的数量 """
        print(f"开始处理 SQL 数据，共 {len(data_list)} 条记录。")
        print('-' * 80)

        passed_count = 0
        try:
            with self.driver.session() as session:
                for index, entry in enumerate(data_list, start=1):
                    print(f"开始处理第 {index}/{len(data_list)} 条记录...")
                    try:
                        if self.analyze_single_sql_in_entry(entry, session):
                            passed_count += 1
                    except Exception as e:
                        print(f"第 {index} 条记录处理失败: {e}")
                    print('-' * 120)
        finally:
            print(f"通过 Neo4j 验证的 SQL 语句数: {passed_count}/{len(data_list)}")

    def analyze_sql_by_database(self):
        """
        通过数据库名称筛选数据并分析 SQL。
        """
        # 1. 创建 DataLoader 实例并加载指定数据集数据，可以通过loader获取数据
        loader = DataLoader(self.dataset_name)
        # 2. 通过loader获取 指定database_name下的字段["db_id", "sql", "question"]，存至data中
        data = loader.filter_data(db_id=self.db_name, fields=["db_id", "sql", "question"])
        # 3.对data进行分析sql语句分析，获得实体关系分析、neo4j对应子图的查询语句，进行neo4j验证
        self.analyze_sql_data(data)


if __name__ == "__main__":
    analyzer = SQLAnalyzer("spider", "academic")
    analyzer.analyze_sql_by_database()
    # # 遍历分析spider所有数据库
    # dataset = "spider"
    # for database in DataLoader(dataset).list_dbname(show=False):
    #     analyzer = SQLAnalyzer(dataset, database)
    #     analyzer.analyze_sql_by_database()
