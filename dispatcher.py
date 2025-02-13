# -*- coding: utf-8 -*-

# 后台调度程序，异步执行，使用redis作为消息队列

import sys, json, time
import concurrent.futures
from datetime import datetime
import binascii

from utils import helper
from utils import logger
from settings import REDIS_CONFIG, MAX_DISPATCHER_WORKERS, model_path

import vlchat

logger = logger.get_logger(__name__)

vlchat_model = None



def process_api(request_id, request_msg):
    request = request_msg
    try:
        if request['api']=='/api/internvl/chat': # 文本 OCR
            # base64 图片 转为 PIL.Image
            img = vlchat.load_image_b64(request['params']['image'])
            r1 = vlchat_model.chat_w_image(request['params']['text'], img)

            # 准备结果
            result = { 'code' : 0, 'msg':'success', 'result' : r1 }

        else: # 未知 api
            logger.error('Unknown api: '+request['api']) 
            result = { 'code' : 9900, 'msg' : '未知 api 调用' }

    except binascii.Error as e:
        logger.error("编码转换异常: %s" % e)
        result = { 'code' : 9901, 'msg' : 'base64编码异常: '+str(e) }

    except json.decoder.JSONDecodeError as e:
        logger.error("json转换异常: %s" % e)
        result = { 'code' : 9902, 'msg' : 'json编码异常: '+str(e) }

    except Exception as e:
        logger.error("未知异常: %s" % e, exc_info=True)
        result = { 'code' : 9998, 'msg' : '未知错误: '+str(e) }

    return result



def process_thread(msg_body):
    try:

        logger.info('{} Calling api: {}'.format(msg_body['request_id'], msg_body['data'].get('api', 'Unknown'))) 

        start_time = datetime.now()

        api_result = process_api(msg_body['request_id'], msg_body['data'])

        logger.info('1 ===> [Time taken: {!s}]'.format(datetime.now() - start_time))
        
        # 发布redis消息
        helper.redis_publish(msg_body['request_id'], api_result)
        
        logger.info('{} {} [Time taken: {!s}]'.format(msg_body['request_id'], msg_body['data']['api'], datetime.now() - start_time))

        sys.stdout.flush()

    except Exception as e:
        logger.error("process_thread异常: %s" % e, exc_info=True)



if __name__ == '__main__':
    if len(sys.argv)<4:
        print("usage: dispatcher.py <QUEUE_NO.> <gpu_num> <main_gpu>")
        sys.exit(2)

    queue_no = sys.argv[1]
    gpu_num = int(sys.argv[2])
    main_gpu = int(sys.argv[3])

    print('Request queue NO. ', queue_no)

    vlchat_model = vlchat.VLChat(model_path, gpu_num, main_gpu)

    sys.stdout.flush()

    while 1:
        try:
            # redis queue
            ps = helper.redis_subscribe(REDIS_CONFIG['REQUEST-QUEUE']+queue_no)

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_DISPATCHER_WORKERS) # 建议与cpu核数相同

            for item in ps.listen():        #监听状态：有消息发布了就拿过来
                logger.info('reveived: type=%s running=%d pending=%d'% \
                    (item['type'], len(executor._threads), executor._work_queue.qsize())) 
                if item['type'] == 'message':
                    #print(item)
                    msg_body = json.loads(item['data'].decode('utf-8'))

                    future = executor.submit(process_thread, msg_body)
                    logger.info('Thread future: '+str(future)) 

                sys.stdout.flush()

        except Exception as e:
            logger.info('Exception: '+str(e)) 
            time.sleep(20)
