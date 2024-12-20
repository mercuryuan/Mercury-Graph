from nltk import pos_tag, word_tokenize
from nltk.corpus import wordnet as wn
from nltk.parse.corenlp import CoreNLPDependencyParser
from neo4j import GraphDatabase


class QuestionGraphCreator:
    def __init__(self, uri, user, password):
        """
        初始化函数，建立与Neo4j数据库的连接。
        """
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        """
        关闭与Neo4j数据库的连接。
        """
        self.driver.close()

    def tokenize_and_tag(self, question):
        """
        对自然语言问题进行分词，并进行词性标注和依存解析。
        """
        tokens = word_tokenize(question.lower())
        tagged_tokens = pos_tag(tokens)
        dep_parser = CoreNLPDependencyParser(url="http://localhost:9000")  # 依存解析器
        parse = next(dep_parser.raw_parse(question))
        dependencies = list(parse.triples())
        return tagged_tokens, dependencies

    def enrich_node_attributes(self, word, pos):
        """
        使用 WordNet 为单词查找语义类别，并生成丰富的属性。
        """
        # 获取词性类别（仅支持名词、动词、形容词、副词）
        wordnet_pos = {'NN': wn.NOUN, 'VB': wn.VERB, 'JJ': wn.ADJ, 'RB': wn.ADV}.get(pos[:2], None)
        synsets = wn.synsets(word, pos=wordnet_pos) if wordnet_pos else []
        if synsets:
            semantic_category = synsets[0].lexname()  # 语义类别
        else:
            semantic_category = "unknown"
        return {"word": word, "pos": pos, "semantic_category": semantic_category}

    def create_nodes_and_edges(self, tagged_tokens, dependencies):
        """
        在 Neo4j 中创建节点和语义关系。
        """
        with self.driver.session(database="question") as session:
            try:
                session.run("RETURN 1")
            except:
                session.run("CREATE DATABASE question")

            # 先清空数据库中之前创建的所有Word节点以及相关关系
            session.run("MATCH (n:Word) DETACH DELETE n")

            # 创建节点
            for idx, (word, pos) in enumerate(tagged_tokens):
                attributes = self.enrich_node_attributes(word, pos)
                session.run(
                    """
                    MERGE (node:Word {word: $word})
                    SET node.pos = $pos,
                        node.semantic_category = $semantic_category,
                        node.index = $index
                    """,
                    word=attributes["word"],
                    pos=attributes["pos"],
                    semantic_category=attributes["semantic_category"],
                    index=idx
                )

            # 创建边并丰富语义关系
            for (governor, dep, dependent) in dependencies:
                session.run(
                    """
                    MATCH (from:Word {word: $governor}),
                          (to:Word {word: $dependent})
                    MERGE (from)-[r:DEPENDS_ON {relation: $dep}]->(to)
                    """,
                    governor=governor[0],
                    dependent=dependent[0],
                    dep=dep
                )

            # 按顺序为分词结果创建 NEXT 关系
            for i in range(len(tagged_tokens) - 1):
                session.run(
                    """
                    MATCH (from:Word {word: $from_word}),
                          (to:Word {word: $to_word})
                    MERGE (from)-[r:NEXT]->(to)
                    SET r.sequence = $sequence
                    """,
                    from_word=tagged_tokens[i][0],
                    to_word=tagged_tokens[i + 1][0],
                    sequence=i
                )

    def build_question_graph(self, question):
        """
        将输入问题转化为丰富的图结构。
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
