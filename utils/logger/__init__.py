import logging
#from flask import has_request_context, request
#from flask.logging import default_handler

#logging.basicConfig(filename='error.log',level=logging.DEBUG)


class RequestFormatter(logging.Formatter):
    def format(self, record):
        if has_request_context():
            record.url = request.url
            record.remote_addr = request.remote_addr
        else:
            record.url = '-'
            record.remote_addr = '-'

        return super().format(record)

def get_logger(module_name):
    # create logger
    logger = logging.getLogger(module_name)
    logger.setLevel(logging.INFO)

    # create console handler and set level to debug
    ch = logging.StreamHandler()
    #ch.addFilter(RequestFormatter())
    ch.setLevel(logging.INFO)

    # create formatter
    #formatter = RequestFormatter('%(remote_addr)s %(asctime)s %(levelname)s %(name)s - %(message)s')

    # add formatter to ch
    #ch.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(ch)
    return logger