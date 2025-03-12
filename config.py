import os

# 获取当前 config.py 所在目录的绝对路径，即项目根目录
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# 统一定义路径
DS_ROOT = os.path.join(PROJECT_ROOT, "graphs_repo")
GRAPHS_REPO = os.path.join(PROJECT_ROOT, "graphs_repo")
GENERATED_DESCRIPTIONS = os.path.join(PROJECT_ROOT, "schema_enricher", "generated_descriptions")


if __name__ == '__main__':

    print(__file__)
    print(f"📌 项目根路径: {PROJECT_ROOT}")
    print(f"📌 数据集路径: {DS_ROOT}")
    print(f"📌 图存储路径: {GRAPHS_REPO}")
    print(f"📌 描述文件路径: {GENERATED_DESCRIPTIONS}")
