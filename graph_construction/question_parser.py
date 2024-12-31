from nltk import pos_tag, word_tokenize
from nltk.corpus import wordnet as wn
from neo4j import GraphDatabase
import spacy


class QuestionGraphCreator:
    def __init__(self, uri, user, password):
        """
        初始化函数，建立与Neo4j数据库的连接。
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        # 先下载：在终端 python -m spacy download en_core_web_sm
        self.nlp = spacy.load("en_core_web_sm")  # 提前加载 spaCy 模型，其包含命名实体识别功能

    def close(self):
        """
        关闭与Neo4j数据库的连接。
        """
        self.driver.close()

    def tokenize_and_tag(self, question):
        """
        对问题进行分词、词性标注以及命名实体识别。
        """
        doc = self.nlp(question)
        # tokens 包含分词结果和对应的词性标注
        tokens = [(token.text, token.tag_, token.ent_type_) for token in doc]
        # dependencies 表示依存关系，结构为 (支配词, 关系类型, 从属词)
        dependencies = [(token.head.text, token.dep_, token.text) for token in doc if token.dep_ != "ROOT"]
        return tokens, dependencies

    def enrich_node_attributes(self, word, pos, entity_type):
        """
        使用 WordNet 为单词查找语义类别，并结合命名实体类型生成丰富的属性。
        """
        # 获取词性类别（仅支持名词、动词、形容词、副词）
        wordnet_pos = {'NN': wn.NOUN, 'VB': wn.VERB, 'JJ': wn.ADJ, 'RB': wn.ADV}.get(pos[:2], None)
        synsets = wn.synsets(word, pos=wordnet_pos) if wordnet_pos else []
        if synsets:
            semantic_category = synsets[0].lexname()  # 语义类别
        else:
            semantic_category = "unknown"  # 如果未找到，默认为“未知”

        return {"word": word, "pos": pos, "semantic_category": semantic_category, "entity_type": entity_type}

    def create_nodes_and_edges(self, tagged_tokens, dependencies):
        """
        在 Neo4j 中创建节点和语义关系，并添加命名实体类型属性到节点。
        """
        with self.driver.session(database="question") as session:
            try:
                session.run("RETURN 1")
            except:
                session.run("CREATE DATABASE question")

            # 先清空数据库中之前创建的所有Word节点以及相关关系
            session.run("MATCH (n:Word) DETACH DELETE n")

            # 创建节点，添加命名实体类型属性
            for idx, (word, pos, entity_type) in enumerate(tagged_tokens):
                attributes = self.enrich_node_attributes(word, pos, entity_type)
                session.run(
                    """
                    MERGE (node:Word {word: $word})  // 创建一个表示单词的节点
                    SET node.pos = $pos,            // 设置节点的词性
                        node.semantic_category = $semantic_category, // 设置语义类别
                        node.entity_type = $entity_type,          // 设置命名实体类型
                        node.index = $index         // 设置节点的索引
                    """,
                    word=attributes["word"],
                    pos=attributes["pos"],
                    semantic_category=attributes["semantic_category"],
                    entity_type=attributes["entity_type"],
                    index=idx
                )

            # 创建依存关系边，并添加语义关系
            for (governor, dep, dependent) in dependencies:
                session.run(
                    """
                    MATCH (from:Word {word: $governor}),  // 查找支配词节点
                          (to:Word {word: $dependent})   // 查找从属词节点
                    MERGE (from)-[r:DEPENDS_ON {relation: $dep}]->(to) // 创建依存关系边
                    // DEPENDS_ON 表示“依存关系”
                    """,
                    governor=governor,
                    dependent=dependent,
                    dep=dep  # dep 表示具体的依存关系类型，例如“主语关系”、“宾语关系”等
                )

            # 按顺序为分词结果创建顺序关系边
            for i in range(len(tagged_tokens) - 1):
                session.run(
                    """
                    MATCH (from:Word {word: $from_word}),  // 当前单词节点
                          (to:Word {word: $to_word})     // 下一个单词节点
                    MERGE (from)-[r:NEXT]->(to)         // 创建顺序关系边
                    SET r.sequence = $sequence          // 设置边的顺序属性
                    // NEXT 表示“在句子中下一个单词”
                    """,
                    from_word=tagged_tokens[i][0],
                    to_word=tagged_tokens[i + 1][0],
                    sequence=i
                )

    def build_question_graph(self, question):
        """
        将输入问题转化为丰富的图结构，包含命名实体类型属性。
        """
        tagged_tokens, dependencies = self.tokenize_and_tag(question)
        self.create_nodes_and_edges(tagged_tokens, dependencies)


# 示例代码
if __name__ == "__main__":
    neo4j_uri = "bolt://localhost:7687"
    neo4j_user = "neo4j"
    neo4j_password = "12345678"

    question_graph_creator = QuestionGraphCreator(neo4j_uri, neo4j_user, neo4j_password)
    question = "Write down the author's name of the book most recently published."
    question_graph_creator.build_question_graph(question)
    question_graph_creator.close()
