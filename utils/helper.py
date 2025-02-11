# coding:utf-8

import sys, time, os, shutil
import json, random, hashlib
import redis
from pymongo import MongoClient

from settings import (
    REDIS_CONFIG,
)
from . import logger

logger = logger.get_logger(__name__)


# 返回指定长度的随机字符串
def ranstr(num):
    H = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    salt = ''
    for i in range(num):
        salt += random.choice(H)
    return salt


# 按格式输出时间字符串
ISOTIMEFORMAT=['%Y-%m-%d %X', '%Y-%m-%d', '%Y%m%d', '%Y%m%d%H%M%S']
def time_str(t=None, format=0):
    return time.strftime(ISOTIMEFORMAT[format], time.localtime(t))


# 生成request_id
def gen_request_id():
    return '%s%s'%(time_str(format=3)[2:],hashlib.md5(ranstr(10).encode('utf-8')).hexdigest())


########## 异步接口调用


# redis订阅
def redis_subscribe(queue_id):
    rc = redis.StrictRedis(host=REDIS_CONFIG['SERVER'], 
            port=REDIS_CONFIG['PORT'], db=1, password=REDIS_CONFIG['PASSWD'])
    ps = rc.pubsub()
    ps.subscribe(queue_id)  #从liao订阅消息
    logger.info('subscribe to : '+str((queue_id))) 
    return ps


# 从订阅接收, 值收一条
def redis_sub_receive(pubsub, queue_id):
    #for item in pubsub.listen():        #监听状态：有消息发布了就拿过来
    #    logger.debug('subscribe 2: '+str((queue_id, item))) 
    #    if item['type'] == 'message':
    #        #print(item)
    #        break

    start = time.time()
    while 1:
        item = pubsub.get_message()
        if item:
            logger.info('reveived: type='+item['type']) 
            if item['type'] == 'message':
                break

        # 检查超时
        if time.time()-start > REDIS_CONFIG['MESSAGE_TIMEOUT']:
            item = { 'data' : json.dumps({"code": 9997, 'data': {"msg": "消息队列超时"}}).encode('utf-8') }
            break

        # 释放cpu
        time.sleep(0.001)

    return item


# redis发布
def redis_publish(queue_id, data):
    logger.info('publish: '+queue_id) 
    msg_body = json.dumps(data)

    rc = redis.StrictRedis(host=REDIS_CONFIG['SERVER'], 
            port=REDIS_CONFIG['PORT'], db=1, password=REDIS_CONFIG['PASSWD'])
    return rc.publish(queue_id, msg_body)


# 返回　请求队列　随机id
def choose_queue_redis():
    # 随机返回
    return random.randint(0, REDIS_CONFIG['REQUEST-QUEUE-NUM']-1)

# redis发布到请求队列
def redis_publish_request(request_id, data):
    msg_body = {
        'request_id' : request_id, # request id
        'data' : data,
    }

    # 设置发送的queue
    queue = REDIS_CONFIG['REQUEST-QUEUE']+str(choose_queue_redis())
    print('queue:', queue)

    return redis_publish(queue, msg_body)
