"""
计算token数量的工具模块
本模块提供了计算文本字符串中token数量的功能。
主要功能:
- `num_tokens_from_string(string: str, encoding_name: str) -> int`: 计算字符串中的token数量。
使用示例:
```python
from token_counter import num_tokens_from_string
text = "这是一个示例文本。"
encoding_name = "cl100k_base"
token_count = num_tokens_from_string(text, encoding_name)
"""
import tiktoken


def num_tokens_from_string(string: str, encoding_name: str) -> int:
    """
    计算字符串中的token数量
    """
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens


# 定义不同模型的编码名称和上下文长度
model_info = {
    "gpt-3.5-turbo": {"encoding": "cl100k_base", "context_length": 4096},
    "gpt-3.5-turbo-16k": {"encoding": "cl100k_base", "context_length": 16384},
    "gpt-4": {"encoding": "cl100k_base", "context_length": 8192},
    "gpt-4-32k": {"encoding": "cl100k_base", "context_length": 32768},
    "gpt-4o": {"encoding": "cl100k_base", "context_length": 8192},
    "text-davinci-003": {"encoding": "p50k_base", "context_length": 4097},
    "text-curie-001": {"encoding": "r50k_base", "context_length": 2049},
    "text-babbage-001": {"encoding": "r50k_base", "context_length": 2049},
    "text-ada-001": {"encoding": "r50k_base", "context_length": 2049},
    "doubao": {"encoding": "cl100k_base", "context_length": 8192},  # 假设豆包编码和GPT一致，仅作示例
    "deepseek-7b": {"encoding": "cl100k_base", "context_length": 8192},  # 模拟DeepSeek编码
    "deepseek-67b": {"encoding": "cl100k_base", "context_length": 32768}  # 模拟DeepSeek编码
}

# 示例文本
text = """
(gk_positioning:INTEGER,The goalkeeper's placement in relation to the goal and players.,Examples: [9, 6, 20, 7, 14, 12],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 96],NumericMean: 16.001345557151033,NumericMode: [8])
(long_shots:INTEGER,The player's ability to score from distances beyond the penalty area.,Examples: [22, 25, 43, 70, 63, 71],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 95],NumericMean: 53.465291654533225,NumericMode: [25])
(marking:INTEGER,The player's effectiveness in keeping opponents under control defensively.,Examples: [17, 38, 62, 65, 21, 67],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 96],NumericMean: 46.903039553355356,NumericMode: [25])
(date:TEXT,The date on which the player attributes were recorded.,Examples: [2010-08-30 00:00:00, 2012-08-31 00:00:00, 2013-05-03 00:00:00, 2016-04-28 00:00:00, 2011-02-22 00:00:00, 2009-02-22 00:00:00],Nullable,DataIntegrity: 100%,AverageCharLength: 19.0,WordFrequency: {"2007-02-22 00:00:00": 6414, "2011-08-30 00:00:00": 3585, "2012-08-31 00:00:00": 3559, "2013-09-20 00:00:00": 3551, "2015-09-21 00:00:00": 3512, "2010-08-30 00:00:00": 3510, "2014-09-18 00:00:00": 3470, "2013-02-15 00:00:00": 3461, "2012-02-22 00:00:00": 3371, "2009-08-30 00:00:00": 3134})
(overall_rating:INTEGER,The overall performance rating of the player, combining various skill attributes.,Examples: [66, 66, 68, 70, 63, 69],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [33, 93],NumericMean: 68.6203721369255,NumericMode: [68])
(id:INTEGER,A unique identifier for each player attribute record.,Primary Key,Examples: [36302, 92990, 59207, 6547, 16246, 57253],Nullable,DataIntegrity: 100%,Range: [1, 100000])
(preferred_foot:TEXT,The player's dominant foot, indicating whether they play primarily with their left or right foot.,Examples: [right, right, right, right, right, right],Nullable,DataIntegrity: 100%,NullCount: 413,TextCategories: ['right', 'left'],AverageCharLength: 4.746954923835441,WordFrequency: {"right": 74387, "left": 25200})
(heading_accuracy:INTEGER,The player's ability to accurately head the ball during play.,Examples: [54, 18, 46, 76, 69, 61],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 95],NumericMean: 57.31945936718648,NumericMode: [68])
(curve:INTEGER,The player's proficiency in putting spin on the ball.,Examples: [66, 72, 60, 63, 77, 59],Nullable,DataIntegrity: 99%,NullCount: 1431,Range: [2, 94],NumericMean: 53.25441061591373,NumericMode: [25])
(free_kick_accuracy:INTEGER,The player's skill in successfully executing free kicks.,Examples: [34, 31, 46, 54, 59, 48],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [3, 97],NumericMean: 49.48926064646992,NumericMode: [25])
(long_passing:INTEGER,The player's ability in making long passes to teammates.,Examples: [57, 53, 52, 65, 67, 66],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [3, 97],NumericMean: 57.175073051703535,NumericMode: [64])
(ball_control:INTEGER,The player's ability to control the ball under various circumstances.,Examples: [34, 72, 21, 59, 73, 68],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [6, 96],NumericMean: 63.55911916213964,NumericMode: [68])
(player_fifa_api_id:INTEGER,An identifier linking to the corresponding player's FIFA API record.,Foreign Key,Examples: [186161, 222875, 206567, 183898, 135861, 190460],Nullable,DataIntegrity: 100%,Range: [2, 234141])
(player_api_id:INTEGER,An identifier linking to the corresponding player's API data record.,Foreign Key,Examples: [38060, 104406, 46246, 45865, 197515, 98058],Nullable,DataIntegrity: 100%,Range: [2752, 750584])
(aggression:INTEGER,The player's tendency to engage opponents aggressively.,Examples: [78, 69, 82, 63, 66, 85],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [6, 97],NumericMean: 61.132145761997045,NumericMode: [68])
(interceptions:INTEGER,The player's ability to intercept passes and disrupt opponent plays.,Examples: [69, 46, 51, 69, 64, 73],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [2, 96],NumericMean: 52.09679978310422,NumericMode: [25])
(positioning:INTEGER,The player's awareness and positioning in relation to the game.,Examples: [64, 65, 66, 25, 58, 45],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [2, 95],NumericMean: 56.03661120427365,NumericMode: [25])
(vision:INTEGER,The player's ability to see plays and anticipate teammate positions.,Examples: [75, 57, 59, 25, 49, 45],Nullable,DataIntegrity: 99%,NullCount: 1431,Range: [1, 96],NumericMean: 58.06853067394414,NumericMode: [68])
(penalties:INTEGER,The player's skill and accuracy in converting penalty kicks.,Examples: [53, 61, 46, 44, 73, 55],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [2, 95],NumericMean: 55.124172833803605,NumericMode: [58])
(sliding_tackle:INTEGER,The player's skill at executing tackles from a sliding position.,Examples: [30, 11, 63, 62, 57, 70],Nullable,DataIntegrity: 99%,NullCount: 1431,Range: [2, 92])
(standing_tackle:INTEGER,The player's ability to tackle opponents while standing.,Examples: [40, 60, 59, 58, 25, 70],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [2, 95],NumericMean: 50.47196923293201,NumericMode: [25])
(gk_diving:INTEGER,The goalkeeper's ability to dive and reach the ball.,Examples: [72, 11, 6, 64, 10, 2],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 94],NumericMean: 14.535441372869952,NumericMode: [8])
(gk_handling:INTEGER,The goalkeeper's proficiency in catching the ball.,Examples: [9, 54, 6, 12, 6, 11],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 93],NumericMean: 15.99377428780865,NumericMode: [14])
(gk_kicking:INTEGER,The goalkeeper's ability to kick the ball accurately over distances.,Examples: [10, 6, 52, 14, 8, 52],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 97],NumericMean: 20.94373763643849,NumericMode: [7])
(shot_power:INTEGER,The strength of the player's shot when attempting to score.,Examples: [66, 57, 70, 70, 12, 64],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [2, 97],NumericMean: 61.907698796027596,NumericMode: [68])
(potential:INTEGER,The player's potential rating, indicative of future performance capability.,Examples: [82, 85, 79, 69, 72, 77],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [42, 95],NumericMean: 73.46893670860655,NumericMode: [75])
(attacking_work_rate:TEXT,The player's attacking effort level, categorized as high, medium, or low.,Examples: [low, medium, medium, high, medium, medium],Nullable,DataIntegrity: 98%,NullCount: 1780,AverageCharLength: 5.314640602728568,WordFrequency: {"medium": 67113, "high": 24239, "low": 4765, "None": 1732, "norm": 199, "le": 77, "y": 61, "stoc": 34})
(defensive_work_rate:TEXT,The player's defensive effort level, categorized as high, medium, or low.,Examples: [medium, medium, high, high, high, high],Nullable,DataIntegrity: 100%,NullCount: 413,AverageCharLength: 5.236305943546848,WordFrequency: {"medium": 70839, "high": 14686, "low": 10557, "_0": 1367, "o": 755, "1": 209, "ormal": 199, "3": 149, "2": 133, "5": 115})
(crossing:INTEGER,The player's skill level in delivering accurate crosses to teammates.,Examples: [52, 36, 25, 70, 52, 60],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [2, 95],NumericMean: 55.410455179892956,NumericMode: [68])
(finishing:INTEGER,The player's proficiency in successfully converting scoring opportunities.,Examples: [13, 11, 37, 59, 50, 45],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 95],NumericMean: 50.04782752768936,NumericMode: [25])
(gk_reflexes:INTEGER,The goalkeeper's quickness and responsiveness to shots on goal.,Examples: [16, 9, 14, 5, 8, 12],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 96],NumericMean: 16.29261851446474,NumericMode: [7])
(short_passing:INTEGER,The player's effectiveness in making short passes to teammates.,Examples: [69, 59, 77, 64, 70, 60],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [3, 97],NumericMean: 62.53243897295832,NumericMode: [64])
(volleys:INTEGER,The player's skill level in executing volleys.,Examples: [35, 30, 31, 78, 63, 33],Nullable,DataIntegrity: 99%,NullCount: 1431,Range: [2, 91],NumericMean: 49.52915216751717,NumericMode: [25])
(dribbling:INTEGER,The player's ability to maneuver the ball past defenders.,Examples: [74, 72, 25, 50, 79, 14],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [1, 97],NumericMean: 59.394358701436936,NumericMode: [66])
(acceleration:INTEGER,The player's quickness in reaching top speed.,Examples: [65, 70, 62, 66, 75, 62],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [13, 97],NumericMean: 67.77598481729542,NumericMode: [68])
(agility:INTEGER,The player's ability to change direction quickly and effectively.,Examples: [59, 58, 76, 78, 81, 42],Nullable,DataIntegrity: 99%,NullCount: 1431,Range: [11, 96],NumericMean: 65.99295924682202,NumericMode: [72])
(stamina:INTEGER,The player's ability to sustain performance throughout the duration of a match.,Examples: [74, 56, 84, 65, 70, 57],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [14, 95],NumericMean: 67.17152841234298,NumericMode: [68])
(sprint_speed:INTEGER,The player's maximum running speed over short distances.,Examples: [57, 54, 54, 64, 68, 53],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [12, 97],NumericMean: 68.21548997359093,NumericMode: [68])
(reactions:INTEGER,The player's quickness in responding to in-game situations.,Examples: [65, 68, 59, 62, 69, 80],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [20, 96],NumericMean: 66.15002962234027,NumericMode: [68])
(balance:INTEGER,The player's stability while in motion, affecting their ability to stay upright.,Examples: [73, 62, 91, 72, 61, 64],Nullable,DataIntegrity: 99%,NullCount: 1431,Range: [12, 96],NumericMean: 65.2792967362964,NumericMode: [70])
(jumping:INTEGER,The player's ability to jump, often impacting heading and aerial duels.,Examples: [75, 75, 72, 60, 76, 64],Nullable,DataIntegrity: 99%,NullCount: 1431,Range: [14, 96],NumericMean: 66.92548367133683,NumericMode: [72])
(strength:INTEGER,The player's physical strength in challenges and duels.,Examples: [76, 67, 65, 47, 65, 68],Nullable,DataIntegrity: 100%,NullCount: 413,Range: [16, 96],NumericMean: 67.50593953025998,NumericMode: [74])

"""

# 计算每个模型的token数量和上下文长度
for model, info in model_info.items():
    encoding_name = info["encoding"]
    context_length = info["context_length"]
    token_count = num_tokens_from_string(text, encoding_name)
    print(f"模型: {model}")
    print(f"  Token 数量: {token_count}")
    print(f"  上下文长度: {context_length}")
    print(f"  是否超出上下文长度: {token_count > context_length}")
    print()
