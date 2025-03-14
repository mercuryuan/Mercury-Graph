import os

# 获取当前 config.py 所在目录的绝对路径，即项目根目录
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))

# 统一定义路径

GRAPHS_REPO = os.path.join(PROJECT_ROOT, "graphs_repo")
GENERATED_DESCRIPTIONS = os.path.join(PROJECT_ROOT, "schema_enricher", "generated_descriptions")
BIRD_TRAIN_DATABASES_PATH = "E:/BIRD_train/train/train_databases/"
BIRD_TRAIN_JSON = "E:/BIRD_train/train/train.json"
BIRD_DEV_JSON = "E:/BIRD/dev_20240627/dev.json"
SPIDER = "your combination of train and other"
SPIDER_DEV_JSON = "E:/spider/dev.json"
SPIDER_DATABASES_PATH = "E:/spider/test_database/"
SPIDER_TRAIN_JSON = "E:/spider/train_spider.json"
SPIDER_TRAIN_OTHER_JSON = "E:/spider/train_others.json"




if __name__ == '__main__':

    print(__file__)
    print(f"📌 项目根路径: {PROJECT_ROOT}")
    print(f"📌 图存储路径: {GRAPHS_REPO}")
    print(f"📌 描述文件路径: {GENERATED_DESCRIPTIONS}")
