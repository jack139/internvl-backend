# 模型设置
model_path = '../../LLMs/lm_model/InternVL2_5-1B'

# dispatcher 中 最大线程数
MAX_DISPATCHER_WORKERS = 1

############# 消息中间件设置

REDIS_CONFIG = {
    'SERVER' : '127.0.0.1',
    'PORT'   : '7480',
    'PASSWD' : 'e18ffb7484f4d69c2acb40008471a71c',
    'REQUEST-QUEUE' : 'InternVL-synchronous-asynchronous-queue',
    'REQUEST-QUEUE-NUM' : 1,
    'MESSAGE_TIMEOUT' : 60, # 结果返回消息超时，单位：秒
}
